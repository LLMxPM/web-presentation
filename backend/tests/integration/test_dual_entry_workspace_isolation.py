"""文件功能：集成验证 Internal 与 External 双入口在跨用户/跨工作空间场景下的隔离防御（读取、写入、异步任务与归档四象限）。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.db.session import get_session_factory
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.models.workspace import Project, Workspace, WorkspaceMember
from app.models.page import Page
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.services.api_access_token_service import ApiAccessTokenService


async def _create_test_user(
    *,
    username: str,
    password_hash: str = "test-hash",
    display_name: str,
) -> int:
    """直接在数据库创建测试用户并返回其 ID。"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username=username,
            password_hash=password_hash,
            display_name=display_name,
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.commit()
        return user.id


async def _create_user_space_and_data(
    *,
    user_id: int,
    workspace_code: str,
    workspace_name: str,
    project_code: str,
    project_name: str,
    page_title: str,
) -> tuple[int, int, int]:
    """为指定用户创建完整的工作空间、成员绑定、项目与页面，返回 (workspace_id, project_id, page_id)。"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        workspace = Workspace(
            code=workspace_code,
            name=workspace_name,
            created_by=user_id,
            updated_by=user_id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add(workspace)
        await session.flush()

        member = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user_id,
            role="owner",
            status=RecordStatus.ACTIVE.value,
            created_by=user_id,
            updated_by=user_id,
        )
        session.add(member)

        project = Project(
            workspace_id=workspace.id,
            code=project_code,
            name=project_name,
            theme_config_yaml="{}",
            created_by=user_id,
            updated_by=user_id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add(project)
        await session.flush()

        page = Page(
            workspace_id=workspace.id,
            project_id=project.id,
            code=f"page-{project_code}-main",
            title=page_title,
            page_content="<template><div>Test Page</div></template>",
            current_version_no=1,
            created_by=user_id,
            updated_by=user_id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add(page)
        await session.commit()

        return workspace.id, project.id, page.id


@pytest.mark.asyncio
async def test_internal_api_workspace_isolation_quadrant(client: AsyncClient) -> None:
    """验证 Internal API (/api/...) 跨用户空间隔离：读取、写入、异步任务与归档均返回 403。"""

    # 1. 初始化平台管理员以创建可登录账号（确保有可用密码 hash）
    admin_login_resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "Admin123456"},
    )
    assert admin_login_resp.status_code == 200

    # 2. 创建 User A 与 User B
    resp_a = await client.post(
        "/api/users",
        json={
            "username": "user_a",
            "password": "Password123!",
            "display_name": "User A",
            "role": "workspace_user",
            "status": "active",
        },
    )
    assert resp_a.status_code == 201
    user_a_id = resp_a.json()["id"]

    resp_b = await client.post(
        "/api/users",
        json={
            "username": "user_b",
            "password": "Password123!",
            "display_name": "User B",
            "role": "workspace_user",
            "status": "active",
        },
    )
    assert resp_b.status_code == 201
    user_b_id = resp_b.json()["id"]

    await client.post("/api/auth/logout")

    # 3. 为 User A 和 User B 构建独立空间数据
    ws_a_id, proj_a_id, page_a_id = await _create_user_space_and_data(
        user_id=user_a_id,
        workspace_code="ws-iso-internal-a",
        workspace_name="Space A",
        project_code="proj-internal-a",
        project_name="Project A",
        page_title="Page A",
    )
    ws_b_id, proj_b_id, page_b_id = await _create_user_space_and_data(
        user_id=user_b_id,
        workspace_code="ws-iso-internal-b",
        workspace_name="Space B",
        project_code="proj-internal-b",
        project_name="Project B",
        page_title="Page B",
    )

    # 4. User B 登录
    login_b = await client.post(
        "/api/auth/login",
        json={"username": "user_b", "password": "Password123!"},
    )
    assert login_b.status_code == 200

    # --- 象限 1: 读取隔离 (Read) ---
    # User B 试图读取 User A 的 Workspace / Project / Page
    get_ws_resp = await client.get(f"/api/workspaces/{ws_a_id}")
    assert get_ws_resp.status_code == 403
    assert get_ws_resp.json()["code"] == "WORKSPACE_ACCESS_DENIED"

    get_proj_resp = await client.get(f"/api/projects/{proj_a_id}")
    assert get_proj_resp.status_code == 403
    assert get_proj_resp.json()["code"] == "WORKSPACE_ACCESS_DENIED"

    get_page_resp = await client.get(f"/api/pages/{page_a_id}")
    assert get_page_resp.status_code == 403
    assert get_page_resp.json()["code"] == "WORKSPACE_ACCESS_DENIED"

    # --- 象限 2: 写入隔离 (Write) ---
    # User B 试图在 User A 的空间/项目中创建页面
    create_page_resp = await client.post(
        "/api/pages",
        json={
            "workspace_id": ws_a_id,
            "project_id": proj_a_id,
            "title": "B 侵入创建的页面",
            "page_content": "<template><div>Hacked</div></template>",
        },
    )
    assert create_page_resp.status_code == 403
    assert create_page_resp.json()["code"] == "WORKSPACE_ACCESS_DENIED"

    # User B 试图修改 User A 的已有页面
    update_page_resp = await client.patch(
        f"/api/pages/{page_a_id}",
        json={"title": "B 篡改后的标题"},
    )
    assert update_page_resp.status_code == 403
    assert update_page_resp.json()["code"] == "WORKSPACE_ACCESS_DENIED"

    # --- 象限 3: 异步任务隔离 (Async Job) ---
    # User B 试图为 User A 的项目发起构建任务
    create_build_resp = await client.post(
        f"/api/projects/{proj_a_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert create_build_resp.status_code == 403
    assert create_build_resp.json()["code"] == "WORKSPACE_ACCESS_DENIED"

    # --- 象限 4: 归档隔离 (Archive / Delete) ---
    # User B 试图删除/归档 User A 的页面
    delete_page_resp = await client.delete(f"/api/pages/{page_a_id}")
    assert delete_page_resp.status_code == 403
    assert delete_page_resp.json()["code"] == "WORKSPACE_ACCESS_DENIED"

    # User B 试图删除/归档 User A 的项目
    delete_proj_resp = await client.delete(f"/api/projects/{proj_a_id}")
    assert delete_proj_resp.status_code == 403
    assert delete_proj_resp.json()["code"] == "WORKSPACE_ACCESS_DENIED"

    # 5. User B 访问自己的资源应完全正常
    own_proj_resp = await client.get(f"/api/projects/{proj_b_id}")
    assert own_proj_resp.status_code == 200
    assert own_proj_resp.json()["id"] == proj_b_id

    await client.post("/api/auth/logout")


@pytest.mark.asyncio
async def test_external_api_workspace_isolation_quadrant(client: AsyncClient) -> None:
    """验证 External API (/api/v1/...) 跨用户空间隔离：读取、写入、异步任务与归档四象限防御。"""

    # 1. 创建 User A 与 User B 及其资源
    user_a_id = await _create_test_user(username="ext_iso_user_a", display_name="Ext A")
    user_b_id = await _create_test_user(username="ext_iso_user_b", display_name="Ext B")

    ws_a_id, proj_a_id, page_a_id = await _create_user_space_and_data(
        user_id=user_a_id,
        workspace_code="ws-iso-ext-a",
        workspace_name="Ext Space A",
        project_code="proj-ext-a",
        project_name="Ext Project A",
        page_title="Ext Page A",
    )
    ws_b_id, proj_b_id, page_b_id = await _create_user_space_and_data(
        user_id=user_b_id,
        workspace_code="ws-iso-ext-b",
        workspace_name="Ext Space B",
        project_code="proj-ext-b",
        project_name="Ext Project B",
        page_title="Ext Page B",
    )

    # 2. 为 User B 签发仅授权 Workspace B 的 PAT
    session_factory = get_session_factory()
    async with session_factory() as session:
        pat_service = ApiAccessTokenService(session)
        token_res = await pat_service.create_token(
            user_id=user_b_id,
            payload=ApiAccessTokenCreateRequest(
                name="UserB-PAT",
                workspace_ids=[ws_b_id],
                scopes=[
                    "workspace:read",
                    "project:read",
                    "project:write",
                    "page:read",
                    "page:write",
                    "component:read",
                    "component:write",
                ],
                expires_in_days=30,
            ),
        )
        token_b = token_res.token
        await session.commit()

    # User B 正常操作 headers (带授权的 ws_b)
    headers_b_normal = {
        "Authorization": f"Bearer {token_b}",
        "X-Workspace-ID": str(ws_b_id),
    }

    # User B 越权操作 headers (指定未授权的 ws_a)
    headers_b_cross_ws = {
        "Authorization": f"Bearer {token_b}",
        "X-Workspace-ID": str(ws_a_id),
    }

    # --- 象限 1: 读取隔离 (Read) ---
    # 试图直接指定 ws_a 查询项目 A 的页面列表 -> 403 WORKSPACE_NOT_AUTHORIZED
    read_pages_resp = await client.get(
        f"/api/v1/projects/{proj_a_id}/pages",
        headers=headers_b_cross_ws,
    )
    assert read_pages_resp.status_code == 403
    assert read_pages_resp.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"

    # 在合法 ws_b 上试图跨空间读取未授权的 page_a -> 403 WORKSPACE_ACCESS_DENIED
    read_single_page_resp = await client.get(
        f"/api/v1/pages/{page_a_id}",
        headers=headers_b_normal,
    )
    assert read_single_page_resp.status_code == 403
    assert read_single_page_resp.json()["code"] == "WORKSPACE_ACCESS_DENIED"

    # --- 象限 2: 写入隔离 (Write) ---
    # 试图通过页面 Mutation 向 ws_a 注入页面 -> 403 WORKSPACE_NOT_AUTHORIZED
    write_page_resp = await client.post(
        "/api/v1/jobs/mutations/pages",
        headers={**headers_b_cross_ws, "Idempotency-Key": "idemp-ext-write-page-1"},
        json={
            "workspace_id": ws_a_id,
            "project_id": proj_a_id,
            "title": "非法注入页面",
            "page_content": "<template><div>Injected</div></template>",
        },
    )
    assert write_page_resp.status_code == 403
    assert write_page_resp.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"

    # --- 象限 3: 异步任务隔离 (Async Job) ---
    # 试图通过组件 Mutation 向 ws_a 创建组件 -> 403 WORKSPACE_NOT_AUTHORIZED
    mutation_job_resp = await client.post(
        "/api/v1/jobs/mutations/components",
        headers={**headers_b_cross_ws, "Idempotency-Key": "idemp-ext-comp-job-1"},
        json={
            "workspace_id": ws_a_id,
            "import_name": "InjectedComp",
            "name": "Injected Component",
            "component_type": "custom",
            "source_code": "<template><div>Bad</div></template>",
        },
    )
    assert mutation_job_resp.status_code == 403
    assert mutation_job_resp.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"

    # --- 象限 4: 归档隔离 (Archive) ---
    # 试图对 ws_a 空间发起归档页面请求 -> 403 WORKSPACE_NOT_AUTHORIZED
    archive_resp_cross = await client.post(
        f"/api/v1/pages/{page_a_id}/archive",
        headers={**headers_b_cross_ws, "Idempotency-Key": "idemp-ext-archive-cross-1"},
    )
    assert archive_resp_cross.status_code == 403
    assert archive_resp_cross.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"

    # 在 ws_b 下试图归档 page_a -> 403 WORKSPACE_ACCESS_DENIED (不可归档他人空间页面)
    archive_resp_scoped = await client.post(
        f"/api/v1/pages/{page_a_id}/archive",
        headers={**headers_b_normal, "Idempotency-Key": "idemp-ext-archive-scoped-1"},
    )
    assert archive_resp_scoped.status_code == 403
    assert archive_resp_scoped.json()["code"] == "WORKSPACE_ACCESS_DENIED"

    # 批量归档 IDOR 探测：在 ws_b 下试图批量归档属于 ws_a 的 page_a -> 403 跨空间越权拦截
    batch_archive_resp = await client.post(
        "/api/v1/pages/batch-archive",
        headers={**headers_b_normal, "Idempotency-Key": "idemp-ext-batch-archive-1"},
        json={"ids": [page_a_id]},
    )
    assert batch_archive_resp.status_code == 403
