"""文件功能：端到端测试 External API v1 主题设计配置（图片/三槽字体一次性创建、更新真值表、省略与 null 幂等指纹冲突及约束校验）。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.db.session import get_session_factory
from app.models.asset import WorkspaceAsset
from app.models.enums import RecordStatus, UserRole
from app.models.font import WorkspaceFontConfig, WorkspaceFontFamily
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService


async def _setup_external_context(
    scopes: list[str] | None = None,
) -> tuple[str, int]:
    """创建外部测试用户、工作空间与指定 Scope 的 PAT。"""
    effective_scopes = (
        scopes
        if scopes is not None
        else ["design-system:read", "design-system:write", "asset:read", "asset:write"]
    )
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username=f"theme_user_{id(effective_scopes)}",
            password_hash="hash",
            display_name="Theme Test User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()

        ws = Workspace(
            code=f"ws-theme-{user.id}",
            name="Theme Test Space",
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
                name="Theme-PAT",
                workspace_ids=[ws.id],
                scopes=effective_scopes,
                expires_in_days=30,
            ),
        )
        token = token_res.token
        ws_id = ws.id
        await session.commit()
    return token, ws_id


async def _create_asset(workspace_id: int, asset_type: str, name: str) -> int:
    """直接在工作空间创建测试资源。"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        asset = WorkspaceAsset(
            workspace_id=workspace_id,
            name=name,
            file_name=f"{name}.svg" if asset_type == "icon" else f"{name}.png",
            original_name=f"{name}.svg" if asset_type == "icon" else f"{name}.png",
            file_size=512,
            file_hash=f"hash_{name}",
            content_type="image/svg+xml" if asset_type == "icon" else "image/png",
            asset_type=asset_type,
            tags=[],
            status=RecordStatus.ACTIVE.value,
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        return asset.id


async def _create_font_family_with_face(workspace_id: int, family_name: str) -> int:
    """创建字体资源、所属族与关联 face。"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        asset = WorkspaceAsset(
            workspace_id=workspace_id,
            name=f"{family_name.lower()}_font",
            file_name=f"{family_name.lower()}.woff2",
            original_name=f"{family_name.lower()}.woff2",
            file_size=2048,
            file_hash=f"hash_font_{family_name}",
            content_type="font/woff2",
            asset_type="font",
            tags=[],
            status=RecordStatus.ACTIVE.value,
        )
        session.add(asset)
        await session.flush()

        family = WorkspaceFontFamily(
            workspace_id=workspace_id,
            name=family_name,
        )
        session.add(family)
        await session.flush()

        face = WorkspaceFontConfig(
            workspace_id=workspace_id,
            family_id=family.id,
            asset_id=asset.id,
            asset_name=asset.name,
            font_format="woff2",
            font_weight="400",
            font_style="normal",
            font_display="swap",
            status=RecordStatus.ACTIVE.value,
        )
        session.add(face)
        await session.commit()
        return family.id


@pytest.mark.asyncio
async def test_external_theme_create_with_full_design_config(client: AsyncClient) -> None:
    """验证 External API 创建主题时支持一次性配置图片与三槽字体，省略 palette 时填充默认值。"""
    token, ws_id = await _setup_external_context()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": str(ws_id),
        "Idempotency-Key": "idemp-theme-create-full-1",
    }

    logo_id = await _create_asset(ws_id, "icon", "brand_logo")
    invert_logo_id = await _create_asset(ws_id, "icon", "brand_logo_invert")
    project_icon_id = await _create_asset(ws_id, "icon", "project_favicon")
    family_id = await _create_font_family_with_face(ws_id, "HeadlineSans")

    payload = {
        "key": "corp-brand",
        "name": "企业品牌主题",
        "description": "企业专属视觉主题",
        "logo_asset_id": logo_id,
        "invert_logo_asset_id": invert_logo_id,
        "project_icon_asset_id": project_icon_id,
        "heading_font_family_id": family_id,
        "body_font_preset": "system-ui",
        "code_font_preset": "monospace",
    }

    # 1. 首次创建主题
    res = await client.post("/api/v1/themes", json=payload, headers=headers)
    assert res.status_code == 201
    created = res.json()
    assert created["key"] == "corp-brand"
    assert created["name"] == "企业品牌主题"
    assert created["logo_asset_id"] == logo_id
    assert created["invert_logo_asset_id"] == invert_logo_id
    assert created["project_icon_asset_id"] == project_icon_id
    assert created["heading_font_family_id"] == family_id
    assert created["heading_font_label"] == "HeadlineSans"
    assert created["body_font_label"] == "system-ui"
    assert created["code_font_label"] == "monospace"
    # palette 省略时自动填充默认色板
    assert "text" in created["palette"]
    assert "background" in created["palette"]

    theme_id = created["id"]

    # 2. 详情查询核对
    get_res = await client.get(f"/api/v1/themes/{theme_id}", headers=headers)
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["logo_asset"]["id"] == logo_id
    assert detail["heading_font_family"]["id"] == family_id
    assert "logo: brand_logo" in detail["resolved_theme_config_yaml"]

    # 3. 相同 Idempotency-Key 重放 -> 返回 201 同一主题
    replay_res = await client.post("/api/v1/themes", json=payload, headers=headers)
    assert replay_res.status_code == 201
    assert replay_res.json()["id"] == theme_id


@pytest.mark.asyncio
async def test_external_theme_update_semantics_and_truth_table(client: AsyncClient) -> None:
    """验证 External API 主题更新字段省略保持、显式 null 清空与字体真值表切换。"""
    token, ws_id = await _setup_external_context()
    base_headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(ws_id)}

    logo_id = await _create_asset(ws_id, "icon", "logo_init")
    family_id = await _create_font_family_with_face(ws_id, "CustomSans")

    create_res = await client.post(
        "/api/v1/themes",
        json={
            "key": "test-theme-update",
            "name": "待更新主题",
            "logo_asset_id": logo_id,
            "heading_font_family_id": family_id,
        },
        headers={**base_headers, "Idempotency-Key": "idemp-create-before-update"},
    )
    assert create_res.status_code == 201
    theme_id = create_res.json()["id"]

    # 1. 省略图片与字体字段，仅更新名称 -> 必须保留原图片与字体绑定
    p1 = await client.patch(
        f"/api/v1/themes/{theme_id}",
        json={"name": "新主题名称"},
        headers={**base_headers, "Idempotency-Key": "idemp-patch-omit-fields"},
    )
    assert p1.status_code == 200
    assert p1.json()["name"] == "新主题名称"
    assert p1.json()["logo_asset_id"] == logo_id
    assert p1.json()["heading_font_family_id"] == family_id

    # 2. 显式传 null 清空 logo_asset_id -> 同步清空持久化名称与关联
    p2 = await client.patch(
        f"/api/v1/themes/{theme_id}",
        json={"logo_asset_id": None},
        headers={**base_headers, "Idempotency-Key": "idemp-patch-clear-logo"},
    )
    assert p2.status_code == 200
    assert p2.json()["logo_asset_id"] is None
    assert p2.json()["logo_asset"] is None
    assert "logo:" not in p2.json()["resolved_theme_config_yaml"]

    # 3. 标题字体切换为内置预设 system-ui -> family_id 自动置为 None
    p3 = await client.patch(
        f"/api/v1/themes/{theme_id}",
        json={"heading_font_preset": "system-ui"},
        headers={**base_headers, "Idempotency-Key": "idemp-patch-switch-preset"},
    )
    assert p3.status_code == 200
    assert p3.json()["heading_font_family_id"] is None
    assert p3.json()["heading_font_label"] == "system-ui"

    # 4. 双显式 null 恢复默认预设 (platform-sans)
    p4 = await client.patch(
        f"/api/v1/themes/{theme_id}",
        json={"heading_font_family_id": None, "heading_font_preset": None},
        headers={**base_headers, "Idempotency-Key": "idemp-patch-restore-default"},
    )
    assert p4.status_code == 200
    assert p4.json()["heading_font_family_id"] is None
    assert p4.json()["heading_font_label"] == "platform-sans"


@pytest.mark.asyncio
async def test_external_theme_idempotency_fingerprint_omit_vs_null(client: AsyncClient) -> None:
    """验证同键下省略字段与显式 null 生成不同指纹，产生 409 IDEMPOTENCY_CONFLICT。"""
    token, ws_id = await _setup_external_context()
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(ws_id)}

    create_res = await client.post(
        "/api/v1/themes",
        json={"key": "idemp-test-theme", "name": "幂等测试主题"},
        headers={**headers, "Idempotency-Key": "idemp-seed-theme"},
    )
    assert create_res.status_code == 201
    theme_id = create_res.json()["id"]

    same_key = "idemp-patch-omit-vs-null"

    # 输入 A：仅更新名称，logo_asset_id 省略
    res_a = await client.patch(
        f"/api/v1/themes/{theme_id}",
        json={"name": "Theme A"},
        headers={**headers, "Idempotency-Key": same_key},
    )
    assert res_a.status_code == 200
    assert res_a.json()["name"] == "Theme A"

    # 输入 B：使用同一 Idempotency-Key，但显式传入 logo_asset_id: null
    res_b = await client.patch(
        f"/api/v1/themes/{theme_id}",
        json={"name": "Theme A", "logo_asset_id": None},
        headers={**headers, "Idempotency-Key": same_key},
    )
    assert res_b.status_code == 409
    assert res_b.json()["code"] in ("IDEMPOTENCY_CONFLICT", "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD")


@pytest.mark.asyncio
async def test_external_theme_validations_and_key_immutability(client: AsyncClient) -> None:
    """验证未知字段 422、互斥预设 422、非法预设 422 与修改 key 400。"""
    token, ws_id = await _setup_external_context()
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(ws_id)}

    create_res = await client.post(
        "/api/v1/themes",
        json={"key": "validate-test-theme", "name": "校验测试主题"},
        headers={**headers, "Idempotency-Key": "idemp-validate-seed"},
    )
    assert create_res.status_code == 201
    theme_id = create_res.json()["id"]

    # 1. 传入未知字段 -> extra="forbid" 拦截 (422)
    bad_field = await client.patch(
        f"/api/v1/themes/{theme_id}",
        json={"invalid_field_unknown": "bad_value"},
        headers={**headers, "Idempotency-Key": "idemp-err-unknown"},
    )
    assert bad_field.status_code == 422

    # 2. 标题字体槽同时传入 family_id 与 preset -> 互斥拦截 (422)
    bad_font_mutex = await client.patch(
        f"/api/v1/themes/{theme_id}",
        json={"heading_font_family_id": 99999, "heading_font_preset": "system-ui"},
        headers={**headers, "Idempotency-Key": "idemp-err-mutex"},
    )
    assert bad_font_mutex.status_code == 422

    # 3. 标题字体传入等宽预设 (monospace) -> 槽位预设不支持 (422)
    bad_preset = await client.patch(
        f"/api/v1/themes/{theme_id}",
        json={"heading_font_preset": "monospace"},
        headers={**headers, "Idempotency-Key": "idemp-err-preset"},
    )
    assert bad_preset.status_code == 422

    # 4. PATCH 尝试修改 theme key -> 严格拒绝 (400 THEME_KEY_IMMUTABLE)
    bad_key = await client.patch(
        f"/api/v1/themes/{theme_id}",
        json={"key": "attempt-new-key"},
        headers={**headers, "Idempotency-Key": "idemp-err-key"},
    )
    assert bad_key.status_code == 400
    assert bad_key.json()["code"] == "THEME_KEY_IMMUTABLE"

    # 5. 项目图标传入 image 类型资产 -> 严格拦截 (400)
    image_asset_id = await _create_asset(ws_id, "image", "photo_asset")
    bad_icon = await client.patch(
        f"/api/v1/themes/{theme_id}",
        json={"project_icon_asset_id": image_asset_id},
        headers={**headers, "Idempotency-Key": "idemp-err-icon-type"},
    )
    assert bad_icon.status_code == 400
    assert bad_icon.json()["code"] == "WORKSPACE_THEME_ASSET_INVALID"
