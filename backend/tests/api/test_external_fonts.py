"""文件功能：端到端测试 External API v1 字体与字体族管理接口（能力发现、注册、更新、重命名、幂等与权限检查）。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.db.session import get_session_factory
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService


async def _setup_external_context(
    scopes: list[str] | None = None,
) -> tuple[str, int]:
    """创建外部测试用户、工作空间与指定 Scope 的 PAT。"""
    effective_scopes = scopes if scopes is not None else ["asset:read", "asset:write", "workspace:read"]
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username=f"font_user_{id(effective_scopes)}",
            password_hash="hash",
            display_name="Font User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()

        ws = Workspace(
            code=f"ws-font-{user.id}",
            name="Font Test Space",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add(ws)
        await session.flush()

        member = WorkspaceMember(
            workspace_id=ws.id,
            user_id=user.id,
            role="owner",
            status=RecordStatus.ACTIVE.value,
        )
        session.add(member)
        await session.flush()

        pat_service = ApiAccessTokenService(session)
        token_res = await pat_service.create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Font-PAT",
                workspace_ids=[ws.id],
                scopes=effective_scopes,
                expires_in_days=30,
            ),
        )
        token = token_res.token
        ws_id = ws.id
        await session.commit()
    return token, ws_id


async def _upload_font_asset(client: AsyncClient, token: str, workspace_id: int, name: str) -> int:
    from app.models.asset import WorkspaceAsset
    session_factory = get_session_factory()
    async with session_factory() as session:
        asset = WorkspaceAsset(
            workspace_id=workspace_id,
            name=name,
            file_name=f"{name}.woff2",
            original_name=f"{name}.woff2",
            file_size=1024,
            file_hash=f"hash_{name}",
            content_type="font/woff2",
            asset_type="font",
            tags=[],
            status="active",
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        return asset.id


@pytest.mark.asyncio
async def test_external_font_capabilities_disclosure(client: AsyncClient) -> None:
    """验证工作空间能力发现接口披露字体 operations 与真实的预设目录。"""
    token, ws_id = await _setup_external_context(["asset:read", "asset:write", "workspace:read"])
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(ws_id)}

    res = await client.get(f"/api/v1/workspaces/{ws_id}/capabilities", headers=headers)
    assert res.status_code == 200
    data = res.json()

    # 1. 验证 operations 包含字体全套能力
    ops = set(data["operations"])
    for expected_op in (
        "font.list",
        "font.get",
        "font.register",
        "font.update",
        "font_family.list",
        "font_family.get",
        "font_family.rename",
    ):
        assert expected_op in ops, f"缺少 operation: {expected_op}"

    # 2. 验证 fonts.presets 能力结构
    assert "fonts" in data
    fonts_cap = data["fonts"]
    assert "presets" in fonts_cap
    assert "platform-sans" in fonts_cap["presets"]["sans"]
    assert "system-ui" in fonts_cap["presets"]["sans"]
    assert "platform-mono" in fonts_cap["presets"]["mono"]
    assert "monospace" in fonts_cap["presets"]["mono"]


@pytest.mark.asyncio
async def test_external_font_crud_idempotency_and_family(client: AsyncClient) -> None:
    """端到端测试通过 External API 进行注册、幂等重放/冲突、更新配置、移动族与族重命名。"""
    token, ws_id = await _setup_external_context(["asset:read", "asset:write", "workspace:read"])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": str(ws_id),
    }

    asset_id_1 = await _upload_font_asset(client, token, ws_id, "external_font_regular")
    asset_id_2 = await _upload_font_asset(client, token, ws_id, "external_font_bold")

    # 1. 注册 face (带 Idempotency-Key)
    idemp_key_1 = "idemp-reg-face-001"
    reg_payload_1 = {
        "asset_id": asset_id_1,
        "family_name": "BrandSans",
        "font_format": "woff2",
        "font_weight": "400",
        "font_style": "normal",
        "font_display": "swap",
    }
    reg_res = await client.post(
        "/api/v1/fonts",
        headers={**headers, "Idempotency-Key": idemp_key_1},
        json=reg_payload_1,
    )
    assert reg_res.status_code == 201
    font_data = reg_res.json()
    font_id_1 = font_data["id"]
    family_id = font_data["family_id"]
    assert font_data["font_family"] == "BrandSans"
    assert font_data["font_weight"] == "400"

    # 2. 同键同输入重放 -> 201 且结果一致
    replay_res = await client.post(
        "/api/v1/fonts",
        headers={**headers, "Idempotency-Key": idemp_key_1},
        json=reg_payload_1,
    )
    assert replay_res.status_code == 201
    assert replay_res.json()["id"] == font_id_1

    # 3. 同键异输入 -> 409 冲突
    conflict_res = await client.post(
        "/api/v1/fonts",
        headers={**headers, "Idempotency-Key": idemp_key_1},
        json={**reg_payload_1, "font_weight": "700"},
    )
    assert conflict_res.status_code == 409

    # 4. 注册第二个 face 归入同一字体族
    reg_res_2 = await client.post(
        "/api/v1/fonts",
        headers={**headers, "Idempotency-Key": "idemp-reg-face-002"},
        json={
            "asset_id": asset_id_2,
            "family_name": "BrandSans",
            "font_weight": "700",
        },
    )
    assert reg_res_2.status_code == 201
    assert reg_res_2.json()["family_id"] == family_id

    # 5. 读取单个 face 详情
    detail_res = await client.get(f"/api/v1/fonts/{font_id_1}", headers=headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == font_id_1
    assert detail_res.json()["font_family"] == "BrandSans"

    # 6. 读取字体列表
    list_res = await client.get("/api/v1/fonts", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()["items"]) >= 2

    # 7. 读取字体族列表及详情
    families_res = await client.get("/api/v1/font-families", headers=headers)
    assert families_res.status_code == 200
    assert any(f["id"] == family_id for f in families_res.json()["items"])

    family_detail_res = await client.get(f"/api/v1/font-families/{family_id}", headers=headers)
    assert family_detail_res.status_code == 200
    assert family_detail_res.json()["name"] == "BrandSans"
    assert len(family_detail_res.json()["faces"]) == 2

    # 8. 更新配置：将第一个 face 的 display 修改为 fallback
    patch_face_res = await client.patch(
        f"/api/v1/fonts/{font_id_1}",
        headers={**headers, "Idempotency-Key": "idemp-patch-face-001"},
        json={"font_display": "fallback"},
    )
    assert patch_face_res.status_code == 200
    assert patch_face_res.json()["font_display"] == "fallback"

    # 9. 重命名字体族
    rename_res = await client.patch(
        f"/api/v1/font-families/{family_id}",
        headers={**headers, "Idempotency-Key": "idemp-rename-fam-001"},
        json={"name": "BrandSansRenamed"},
    )
    assert rename_res.status_code == 200
    assert rename_res.json()["name"] == "BrandSansRenamed"

    # 验证单项详情中的 font_family 已同步更新
    updated_face = await client.get(f"/api/v1/fonts/{font_id_1}", headers=headers)
    assert updated_face.status_code == 200
    assert updated_face.json()["font_family"] == "BrandSansRenamed"


@pytest.mark.asyncio
async def test_external_font_scope_enforcement_and_extra_forbidden(client: AsyncClient) -> None:
    """验证 Scope 拦截、未知字段拒绝与非法状态注入防护。"""
    # 仅授予只读 asset:read
    read_only_token, ws_id = await _setup_external_context(["asset:read", "workspace:read"])
    read_headers = {"Authorization": f"Bearer {read_only_token}", "X-Workspace-ID": str(ws_id)}

    # 1. asset:read 权限试图执行 POST /api/v1/fonts 必须被拒绝 (403)
    forbidden_res = await client.post(
        "/api/v1/fonts",
        headers={**read_headers, "Idempotency-Key": "idemp-forbidden"},
        json={"asset_id": 1, "family_name": "Test"},
    )
    assert forbidden_res.status_code == 403

    # 2. 具备 write 权限但传入 status 非法注入参数必须报 422 (extra="forbid")
    write_token, write_ws_id = await _setup_external_context(["asset:read", "asset:write", "workspace:read"])
    write_headers = {"Authorization": f"Bearer {write_token}", "X-Workspace-ID": str(write_ws_id)}
    extra_res = await client.post(
        "/api/v1/fonts",
        headers={**write_headers, "Idempotency-Key": "idemp-extra"},
        json={"asset_id": 1, "family_name": "Test", "status": "disabled"},
    )
    assert extra_res.status_code == 422
