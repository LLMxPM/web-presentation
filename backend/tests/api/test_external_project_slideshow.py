"""文件功能：验证 External API 项目放映配置的创建、更新、配置读取、路由覆盖与幂等指纹语义。"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.db.session import get_session_factory
from app.models.enums import RecordStatus, UserRole
from app.models.page import Page
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService
from app.services.workspace_style_service import WorkspaceStyleService

DEFAULT_SLIDESHOW = {
    "transition": {"effect": "fade", "duration_ms": 400},
    "advance": {"mode": "manual", "delay_ms": 5000, "media_timeout_ms": 300000},
    "loop": False,
    "auto_start": False,
}

TIMER_SLIDESHOW = {
    "transition": {"effect": "push", "duration_ms": 700},
    "advance": {"mode": "timer", "delay_ms": 8000, "media_timeout_ms": 450000},
    "loop": True,
    "auto_start": False,
}


async def _create_external_identity() -> tuple[str, int, int]:
    """创建独立用户、工作空间与具备项目/页面读写权限的 PAT。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username=f"slideshow_ext_{uuid.uuid4().hex[:8]}",
            password_hash="hash",
            display_name="Slideshow External User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()
        workspace = Workspace(
            code=f"ws-slideshow-{uuid.uuid4().hex[:8]}",
            name="External 放映空间",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add(workspace)
        await session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role="owner",
                status=RecordStatus.ACTIVE.value,
            )
        )
        await session.flush()
        await WorkspaceStyleService(session).create_default_style_for_workspace(workspace, user.id)
        token_result = await ApiAccessTokenService(session).create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Slideshow-PAT",
                workspace_ids=[workspace.id],
                scopes=["project:read", "project:write", "page:read", "page:write", "workspace:read"],
                expires_in_days=30,
            ),
        )
        user_id = user.id
        workspace_id = workspace.id
        token = token_result.token
        await session.commit()
    return token, workspace_id, user_id


def _headers(token: str, workspace_id: int, idempotency_key: str | None = None) -> dict[str, str]:
    """构造 External 请求头；写操作按需附加幂等键。"""

    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(workspace_id)}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


async def _create_external_project(
    client: AsyncClient,
    token: str,
    workspace_id: int,
    *,
    slideshow: dict | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """通过 External API 创建项目。"""

    payload: dict[str, object] = {"name": "External 放映项目", "status": "active"}
    if slideshow is not None:
        payload["slideshow"] = slideshow
    response = await client.post(
        "/api/v1/projects",
        json=payload,
        headers=_headers(token, workspace_id, idempotency_key or f"create-{uuid.uuid4().hex[:8]}"),
    )
    assert response.status_code in {200, 201}, response.text
    return response.json()


async def _create_project_pages(workspace_id: int, project_id: int, user_id: int, titles: list[str]) -> list[int]:
    """直接落库创建页面，避免依赖异步页面 Mutation 队列。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        pages = []
        for index, title in enumerate(titles):
            page = Page(
                workspace_id=workspace_id,
                project_id=project_id,
                code=f"EXT_SLIDE_{uuid.uuid4().hex[:6].upper()}",
                title=title,
                page_content=f"<template><div>{title}</div></template>",
                current_version_no=1,
                file_type="vue",
                status=RecordStatus.ACTIVE.value,
                created_by=user_id,
                updated_by=user_id,
            )
            pages.append(page)
        session.add_all(pages)
        await session.commit()
        return [page.id for page in pages]


@pytest.mark.asyncio
async def test_external_project_create_and_patch_should_handle_slideshow(client: AsyncClient) -> None:
    """外部创建省略使用默认值，显式提供时保存；PATCH 支持替换并拒绝 null。"""

    token, workspace_id, _ = await _create_external_identity()
    default_project = await _create_external_project(client, token, workspace_id)
    assert default_project["slideshow"] == DEFAULT_SLIDESHOW

    custom_project = await _create_external_project(
        client,
        token,
        workspace_id,
        slideshow=TIMER_SLIDESHOW,
    )
    assert custom_project["slideshow"] == TIMER_SLIDESHOW

    patch_response = await client.patch(
        f"/api/v1/projects/{custom_project['id']}",
        json={"slideshow": DEFAULT_SLIDESHOW},
        headers=_headers(token, workspace_id, f"patch-{uuid.uuid4().hex[:8]}"),
    )
    assert patch_response.status_code == 200, patch_response.text
    assert patch_response.json()["slideshow"] == DEFAULT_SLIDESHOW

    null_response = await client.patch(
        f"/api/v1/projects/{custom_project['id']}",
        json={"slideshow": None},
        headers=_headers(token, workspace_id, f"patch-null-{uuid.uuid4().hex[:8]}"),
    )
    assert null_response.status_code == 422

    detail = await client.get(f"/api/v1/projects/{custom_project['id']}", headers=_headers(token, workspace_id))
    assert detail.status_code == 200
    assert detail.json()["slideshow"] == DEFAULT_SLIDESHOW


@pytest.mark.asyncio
async def test_external_configuration_should_keep_slideshow_top_level(client: AsyncClient) -> None:
    """configuration 读写中 slideshow 与 presentation 并列，不能塞进 configuration.presentation。"""

    token, workspace_id, _ = await _create_external_identity()
    project = await _create_external_project(client, token, workspace_id, slideshow=TIMER_SLIDESHOW)

    config_response = await client.get(
        f"/api/v1/projects/{project['id']}/configuration",
        headers=_headers(token, workspace_id),
    )
    assert config_response.status_code == 200
    assert config_response.json()["slideshow"] == TIMER_SLIDESHOW

    update_response = await client.put(
        f"/api/v1/projects/{project['id']}/configuration",
        json={"slideshow": DEFAULT_SLIDESHOW},
        headers=_headers(token, workspace_id, f"config-{uuid.uuid4().hex[:8]}"),
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["slideshow"] == DEFAULT_SLIDESHOW

    nested_response = await client.put(
        f"/api/v1/projects/{project['id']}/configuration",
        json={"configuration": {"slideshow": TIMER_SLIDESHOW}},
        headers=_headers(token, workspace_id, f"config-nested-{uuid.uuid4().hex[:8]}"),
    )
    assert nested_response.status_code == 422


@pytest.mark.asyncio
async def test_external_route_tree_should_roundtrip_route_overrides(client: AsyncClient) -> None:
    """外部路由树读写应携带原始覆盖与只读生效值。"""

    token, workspace_id, user_id = await _create_external_identity()
    project = await _create_external_project(client, token, workspace_id, slideshow=TIMER_SLIDESHOW)
    page_id = (await _create_project_pages(workspace_id, project["id"], user_id, ["外部路由页"]))[0]

    put_response = await client.put(
        f"/api/v1/projects/{project['id']}/route-tree",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page_id,
                    "transition": {"effect": "none", "duration_ms": 0},
                    "advance": {"mode": "manual", "delay_ms": 1500, "media_timeout_ms": 300000},
                }
            ]
        },
        headers=_headers(token, workspace_id, f"route-{uuid.uuid4().hex[:8]}"),
    )
    assert put_response.status_code == 200, put_response.text
    route = put_response.json()["routes"][0]
    assert route["transition"] == {"effect": "none", "duration_ms": 0}
    assert route["advance"] == {"mode": "manual", "delay_ms": 1500, "media_timeout_ms": 300000}
    assert route["effective_slideshow"] == {
        "transition": {"effect": "none", "duration_ms": 0},
        "advance": {"mode": "manual", "delay_ms": 1500, "media_timeout_ms": 300000},
    }

    get_response = await client.get(
        f"/api/v1/projects/{project['id']}/route-tree",
        headers=_headers(token, workspace_id),
    )
    assert get_response.status_code == 200
    assert get_response.json()["routes"][0]["transition"] == {"effect": "none", "duration_ms": 0}


@pytest.mark.asyncio
async def test_external_idempotency_should_distinguish_slideshow_and_omitted_fields(client: AsyncClient) -> None:
    """相同幂等键配合不同放映参数或“省略/null”差异必须冲突。"""

    token, workspace_id, user_id = await _create_external_identity()

    create_key = f"idem-create-{uuid.uuid4().hex[:8]}"
    await _create_external_project(client, token, workspace_id, slideshow=DEFAULT_SLIDESHOW, idempotency_key=create_key)
    conflict = await client.post(
        "/api/v1/projects",
        json={"name": "External 放映项目", "status": "active", "slideshow": TIMER_SLIDESHOW},
        headers=_headers(token, workspace_id, create_key),
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD"

    project = await _create_external_project(client, token, workspace_id, slideshow=TIMER_SLIDESHOW)
    page_id = (await _create_project_pages(workspace_id, project["id"], user_id, ["幂等路由页"]))[0]
    route_key = f"idem-route-{uuid.uuid4().hex[:8]}"
    first_route = await client.put(
        f"/api/v1/projects/{project['id']}/route-tree",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page_id,
                    "transition": {"effect": "push", "duration_ms": 600},
                }
            ]
        },
        headers=_headers(token, workspace_id, route_key),
    )
    assert first_route.status_code == 200, first_route.text

    # 省略 transition 与显式 null 的写入结果不同（保留 vs 清除），不能复用同一幂等键。
    reuse_omitted = await client.put(
        f"/api/v1/projects/{project['id']}/route-tree",
        json={
            "routes": [
                {"route_type": "page", "route": "home", "order": 0, "page_id": page_id},
            ]
        },
        headers=_headers(token, workspace_id, route_key),
    )
    assert reuse_omitted.status_code == 409
    assert reuse_omitted.json()["code"] == "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD"


@pytest.mark.asyncio
async def test_external_capabilities_should_declare_schema2_but_keep_media_closed(client: AsyncClient) -> None:
    """schema 2 披露媒体超时结构，但 advance_modes 仍不包含 media_end，演讲者保持不可用。"""

    token, workspace_id, _ = await _create_external_identity()
    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/capabilities",
        headers=_headers(token, workspace_id),
    )
    assert response.status_code == 200, response.text
    slideshow = response.json()["slideshow"]
    assert slideshow["schema_version"] == 2
    assert slideshow["transition_effects"] == ["none", "fade", "push"]
    assert slideshow["advance_modes"] == ["manual", "timer"]
    assert slideshow["single_window_auto_play"] is True
    assert slideshow["presenter_auto_play"] is False
    assert slideshow["capture_auto_play"] is False
    assert slideshow["transition_duration_ms"] == {"min": 100, "max": 2000, "none": 0}
    assert slideshow["delay_ms"] == {"min": 1000, "max": 3600000}
    assert slideshow["media_timeout_ms"] == {"min": 1000, "max": 3600000}
