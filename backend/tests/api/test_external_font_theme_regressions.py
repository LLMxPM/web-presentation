"""文件功能：回归字体/主题审查发现的升级幂等、共享真值表、非法 null 与最后可用字体引用问题。"""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.api_idempotency_record import ApiIdempotencyRecord
from app.models.font import WorkspaceFontConfig
from app.models.workspace_theme import WorkspaceTheme
from app.schemas.theme import WorkspaceThemeCreateRequest, WorkspaceThemeUpdateRequest
from app.schemas.font import WorkspaceFontConfigUpdateRequest
from app.models.enums import RecordStatus
from app.core.exceptions import AppException
from app.services.idempotency_service import IdempotencyService
from app.services.workspace_font_service import WorkspaceFontService
from tests.api.test_external_fonts import _upload_font_asset
from tests.api.test_external_themes_config import _create_font_family_with_face, _setup_external_context

CASES = json.loads((Path(__file__).resolve().parents[3] / "tests/fixtures/cli-font-theme/font-theme-contract-cases.json").read_text(encoding="utf-8"))


async def _context():
    """在隔离测试库中建立权限上下文，凭证仅供内存请求使用。"""

    token, workspace_id = await _setup_external_context()
    return token, workspace_id, {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(workspace_id)}


async def _seed_theme(client, headers, **fields):
    """创建测试主题，默认请求不依赖文件存储或 Renderer。"""

    response = await client.post("/api/v1/themes", headers={**headers, "Idempotency-Key": "seed"}, json={"key": "review-theme", "name": "Review", **fields})
    assert response.status_code == 201, response.text
    return response.json()


async def _legacy_record(workspace_id, key, operation, method, path, fields):
    """替换隔离库记录的指纹，准确模拟升级前已提交的结果。"""

    async with get_session_factory()() as session:
        record = await session.scalar(select(ApiIdempotencyRecord).where(ApiIdempotencyRecord.workspace_id == workspace_id, ApiIdempotencyRecord.operation == operation, ApiIdempotencyRecord.idempotency_key == key))
        assert record is not None
        record.request_fingerprint = IdempotencyService.calculate_request_fingerprint(http_method=method, path=path, json_data=fields)
        await session.commit()


@pytest.mark.parametrize("algorithm", ["internal", "external"])
async def test_theme_create_replays_both_previous_algorithms(client, algorithm):
    """创建重放兼容两个历史算法，不能重复执行并覆盖后续对象修改。"""

    _, workspace_id, headers = await _context()
    theme = await _seed_theme(client, headers)
    payload = {"key": "review-theme", "name": "Review"}
    if algorithm == "internal":
        previous = WorkspaceThemeCreateRequest(**payload, palette=theme["palette"]).model_dump(mode="json")
    else:
        from app.schemas.external_api import ExternalThemeCreateRequest

        previous = ExternalThemeCreateRequest(**payload).model_dump(mode="json")
    await _legacy_record(workspace_id, "seed", "theme.create", "POST", "/api/v1/themes", previous)
    async with get_session_factory()() as session:
        current = await session.get(WorkspaceTheme, theme["id"])
        current.name = "Later edit"
        await session.commit()
    response = await client.post("/api/v1/themes", headers={**headers, "Idempotency-Key": "seed"}, json=payload)
    assert response.status_code == 201
    assert response.json()["id"] == theme["id"]
    assert response.json()["name"] == "Review"
    current = await client.get(f"/api/v1/themes/{theme['id']}", headers=headers)
    assert current.json()["name"] == "Later edit"


@pytest.mark.parametrize("algorithm", ["full", "partial"])
async def test_theme_patch_replays_previous_algorithms_without_writing(client, algorithm):
    """更新只重放已完成结果，不按旧算法再次执行写入。"""

    _, workspace_id, headers = await _context()
    theme = await _seed_theme(client, headers)
    path = f"/api/v1/themes/{theme['id']}"
    payload = {"name": "Changed"}
    response = await client.patch(path, headers={**headers, "Idempotency-Key": "legacy"}, json=payload)
    assert response.status_code == 200
    previous = WorkspaceThemeUpdateRequest(**payload).model_dump(mode="json") if algorithm == "full" else payload
    await _legacy_record(workspace_id, "legacy", "theme.update", "PATCH", path, previous)
    async with get_session_factory()() as session:
        current = await session.get(WorkspaceTheme, theme["id"])
        current.name = "Later edit"
        await session.commit()
    replay = await client.patch(path, headers={**headers, "Idempotency-Key": "legacy"}, json=payload)
    assert replay.status_code == 200
    assert replay.json()["name"] == "Changed"
    assert (await client.get(path, headers=headers)).json()["name"] == "Later edit"


async def test_ambiguous_old_null_request_is_not_reexecuted(client):
    """旧全量指纹无法证明清空意图时必须冲突，不能重执行或误放行新输入。"""

    _, workspace_id, headers = await _context()
    theme = await _seed_theme(client, headers)
    path = f"/api/v1/themes/{theme['id']}"
    payload = {"name": "Changed"}
    assert (await client.patch(path, headers={**headers, "Idempotency-Key": "legacy"}, json=payload)).status_code == 200
    await _legacy_record(workspace_id, "legacy", "theme.update", "PATCH", path, WorkspaceThemeUpdateRequest(**payload).model_dump(mode="json"))
    conflict = await client.patch(path, headers={**headers, "Idempotency-Key": "legacy"}, json={**payload, "logo_asset_id": None})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD"


async def test_new_full_payload_does_not_alias_legacy_omitted_fields(client):
    """版本化指纹阻止新记录恰好等于旧全量 dump 时误触发兼容重放。"""

    _, _, headers = await _context()
    theme = await _seed_theme(client, headers)
    path = f"/api/v1/themes/{theme['id']}"
    full = WorkspaceThemeUpdateRequest(name="Changed").model_dump(mode="json")
    assert (await client.patch(path, headers={**headers, "Idempotency-Key": "new-full"}, json=full)).status_code == 200
    replay = await client.patch(path, headers={**headers, "Idempotency-Key": "new-full"}, json={"name": "Changed"})
    assert replay.status_code == 409


@pytest.mark.parametrize("field", ["family_name", "font_format", "font_weight", "font_style", "font_display"])
async def test_font_update_rejects_explicit_null_but_allows_omission(client, field):
    """所有 face 可写字段拒绝显式 null，空更新仍保留配置。"""

    _, workspace_id, headers = await _context()
    family_id = await _create_font_family_with_face(workspace_id, "NullGuard")
    family = (await client.get(f"/api/v1/font-families/{family_id}", headers=headers)).json()
    face_id = family["faces"][0]["id"]
    path = f"/api/v1/fonts/{face_id}"
    rejected = await client.patch(path, headers={**headers, "Idempotency-Key": "null"}, json={field: None})
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "VALIDATION_ERROR"
    unchanged = await client.patch(path, headers={**headers, "Idempotency-Key": "empty"}, json={})
    assert unchanged.status_code == 200
    assert unchanged.json()["font_weight"] == "400"


@pytest.mark.parametrize("case", CASES["theme_font_cases"], ids=lambda case: case["name"])
async def test_external_theme_consumes_shared_font_truth_table(client, case):
    """真实请求消费共享正反例，防止契约文件未被测试使用而持续漂移。"""

    _, workspace_id, headers = await _context()
    family_id = await _create_font_family_with_face(workspace_id, "TruthTable")
    theme = await _seed_theme(client, headers, heading_font_family_id=family_id)
    payload = dict(case["input"])
    if payload.get("heading_font_family_id") == 10:
        payload["heading_font_family_id"] = family_id
    response = await client.patch(f"/api/v1/themes/{theme['id']}", headers={**headers, "Idempotency-Key": "truth"}, json=payload)
    if not case["valid"]:
        assert response.status_code in {400, 422}
        assert response.json()["code"] == case["error"]
        return
    assert response.status_code == 200, response.text
    if not payload or payload.get("heading_font_family_id") == family_id:
        assert response.json()["heading_font_family_id"] == family_id
    else:
        assert response.json()["heading_font_family_id"] is None
        assert response.json()["heading_font_label"] == (payload.get("heading_font_preset") or "platform-sans")


@pytest.mark.parametrize("sibling_status", [None, "archived", "active"])
async def test_move_protects_last_usable_face_and_rolls_back(client, sibling_status):
    """只有另有可用兄弟 face 才可移动；拒绝时不残留目标空族或改变绑定。"""

    token, workspace_id, headers = await _context()
    family_id = await _create_font_family_with_face(workspace_id, "Original")
    original = (await client.get(f"/api/v1/font-families/{family_id}", headers=headers)).json()["faces"][0]
    if sibling_status:
        asset_id = await _upload_font_asset(client, token, workspace_id, "sibling")
        sibling = await client.post("/api/v1/fonts", headers={**headers, "Idempotency-Key": "sibling"}, json={"asset_id": asset_id, "family_name": "Original", "font_weight": "700"})
        assert sibling.status_code == 201
        async with get_session_factory()() as session:
            face = await session.get(WorkspaceFontConfig, sibling.json()["id"])
            face.status = sibling_status
            await session.commit()
    theme = await _seed_theme(client, headers, heading_font_family_id=family_id)
    response = await client.patch(f"/api/v1/fonts/{original['id']}", headers={**headers, "Idempotency-Key": "move"}, json={"family_name": "Moved"})
    if sibling_status == "active":
        assert response.status_code == 200, response.text
        assert response.json()["family_id"] != family_id
    else:
        assert response.status_code == 409
        assert response.json()["code"] == "FONT_CONFIG_IN_USE"
        families = (await client.get("/api/v1/font-families", headers=headers)).json()["items"]
        assert not any(item["name"] == "Moved" for item in families)
        assert (await client.get(f"/api/v1/fonts/{original['id']}", headers=headers)).json()["family_id"] == family_id
    assert (await client.get(f"/api/v1/themes/{theme['id']}", headers=headers)).json()["heading_font_family_id"] == family_id


async def test_internal_disable_and_delete_share_last_face_protection(client):
    """内部停用与删除必须和 External 移动共用族锁及引用判断，不能绕过最后字体保护。"""

    _, workspace_id, headers = await _context()
    family_id = await _create_font_family_with_face(workspace_id, "Protected")
    original = (await client.get(f"/api/v1/font-families/{family_id}", headers=headers)).json()["faces"][0]
    await _seed_theme(client, headers, heading_font_family_id=family_id)
    async with get_session_factory()() as session:
        service = WorkspaceFontService(session)
        with pytest.raises(AppException) as disabled:
            await service.update_workspace_font(workspace_id, original["id"], WorkspaceFontConfigUpdateRequest(status=RecordStatus.ARCHIVED), commit=False)
        assert disabled.value.code == "FONT_CONFIG_IN_USE"
        await session.rollback()
        with pytest.raises(AppException) as deleted:
            await service.delete_workspace_font(workspace_id, original["id"])
        assert deleted.value.code == "FONT_CONFIG_IN_USE"
        await session.rollback()
    assert (await client.get(f"/api/v1/fonts/{original['id']}", headers=headers)).json()["status"] == "active"


async def test_same_family_update_keeps_last_bound_face(client):
    """同族名称的大小写与空白变化不属于移走 face，不应误拒绝合法配置更新。"""

    _, workspace_id, headers = await _context()
    family_id = await _create_font_family_with_face(workspace_id, "SameFamily")
    face = (await client.get(f"/api/v1/font-families/{family_id}", headers=headers)).json()["faces"][0]
    await _seed_theme(client, headers, heading_font_family_id=family_id)
    response = await client.patch(f"/api/v1/fonts/{face['id']}", headers={**headers, "Idempotency-Key": "same-family"}, json={"family_name": " samefamily ", "font_display": "fallback"})
    assert response.status_code == 200, response.text
    assert response.json()["family_id"] == family_id
    assert response.json()["font_display"] == "fallback"
