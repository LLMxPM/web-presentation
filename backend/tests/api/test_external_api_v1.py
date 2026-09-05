"""文件功能：端到端测试 External API v1 路由层（Bearer 鉴权、Scope 拦截、工作空间隔离、业务 CRUD、主题 key 不可变性与批量归档原子事务）。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.db.session import get_session_factory
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.models.workspace import Project, Workspace, WorkspaceMember
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService


@pytest.mark.asyncio
async def test_external_api_auth_and_scope_enforcement(client: AsyncClient) -> None:
    """测试 External API v1 的 Bearer 认证与 Scope 强制检查。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username="ext_user",
            password_hash="hash",
            display_name="External User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()

        ws = Workspace(code="ws-ext-01", name="External Space", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
        session.add(ws)
        await session.flush()

        member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner", status=RecordStatus.ACTIVE.value)
        session.add(member)
        await session.flush()

        # 仅授予只读 project:read 权限
        pat_service = ApiAccessTokenService(session)
        token_res = await pat_service.create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Read-Only-PAT",
                workspace_ids=[ws.id],
                scopes=["project:read", "workspace:read"],
                expires_in_days=30,
            ),
        )
        token = token_res.token
        ws_id = ws.id
        await session.commit()

    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(ws_id)}

    # 1. 查询 PAT 授权的工作空间 -> 200 OK
    workspace_resp = await client.get("/api/v1/workspaces", headers={"Authorization": f"Bearer {token}"})
    assert workspace_resp.status_code == 200
    assert [item["id"] for item in workspace_resp.json()] == [ws_id]

    # 2. 正常只读请求 -> 200 OK
    resp = await client.get("/api/v1/projects", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # 3. 未授权写操作 (无 project:write) -> 必须被拦截 403 INSUFFICIENT_SCOPE
    write_resp = await client.post("/api/v1/projects", json={"name": "Forbidden Project"}, headers=headers)
    assert write_resp.status_code == 403
    assert write_resp.json()["code"] == "INSUFFICIENT_SCOPE"

    # 4. 访问未授权工作空间 -> 403 WORKSPACE_NOT_AUTHORIZED
    bad_ws_headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": "99999"}
    bad_ws_resp = await client.get("/api/v1/projects", headers=bad_ws_headers)
    assert bad_ws_resp.status_code == 403
    assert bad_ws_resp.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"


@pytest.mark.asyncio
async def test_long_lived_pat_dynamically_authorizes_all_member_workspaces(client: AsyncClient) -> None:
    """测试全空间长期 PAT 自动覆盖创建后新增的成员空间，但不绕过成员资格。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username="all_workspace_pat_user",
            password_hash="hash",
            display_name="All Workspace PAT User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        other_user = User(
            username="all_workspace_pat_other_user",
            password_hash="hash",
            display_name="Other User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add_all([user, other_user])
        await session.flush()

        first_workspace = Workspace(code="ws-pat-all-first", name="First Space", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
        session.add(first_workspace)
        await session.flush()
        session.add(WorkspaceMember(workspace_id=first_workspace.id, user_id=user.id, role="owner", status=RecordStatus.ACTIVE.value))

        token_result = await ApiAccessTokenService(session).create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Long-Lived-All-Workspaces",
                all_workspaces=True,
                scopes=["workspace:read", "project:read"],
                expires_in_days=None,
            ),
        )

        later_workspace = Workspace(code="ws-pat-all-later", name="Later Space", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
        inaccessible_workspace = Workspace(code="ws-pat-all-inaccessible", name="Inaccessible Space", created_by=other_user.id, updated_by=other_user.id, status=RecordStatus.ACTIVE.value)
        session.add_all([later_workspace, inaccessible_workspace])
        await session.flush()
        session.add(WorkspaceMember(workspace_id=later_workspace.id, user_id=user.id, role="owner", status=RecordStatus.ACTIVE.value))
        await session.commit()

        token = token_result.token
        first_workspace_id = first_workspace.id
        later_workspace_id = later_workspace.id
        inaccessible_workspace_id = inaccessible_workspace.id

    auth_headers = {"Authorization": f"Bearer {token}"}
    workspaces_response = await client.get("/api/v1/workspaces", headers=auth_headers)
    assert workspaces_response.status_code == 200
    assert {item["id"] for item in workspaces_response.json()} == {first_workspace_id, later_workspace_id}

    whoami_response = await client.get("/api/v1/auth/whoami", headers=auth_headers)
    assert whoami_response.status_code == 200
    assert whoami_response.json()["token"]["expires_at"] is None
    assert whoami_response.json()["token"]["all_workspaces"] is True

    later_response = await client.get(
        "/api/v1/projects",
        headers={**auth_headers, "X-Workspace-ID": str(later_workspace_id)},
    )
    assert later_response.status_code == 200

    inaccessible_response = await client.get(
        "/api/v1/projects",
        headers={**auth_headers, "X-Workspace-ID": str(inaccessible_workspace_id)},
    )
    assert inaccessible_response.status_code == 403
    assert inaccessible_response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_external_api_theme_key_immutability(client: AsyncClient) -> None:
    """测试通过 External API 更新主题时禁止修改 theme key。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username="theme_user",
            password_hash="hash",
            display_name="Theme User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()

        ws = Workspace(code="ws-ext-02", name="Theme Space", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
        session.add(ws)
        await session.flush()

        member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner", status=RecordStatus.ACTIVE.value)
        session.add(member)
        await session.flush()

        pat_service = ApiAccessTokenService(session)
        token_res = await pat_service.create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Theme-PAT",
                workspace_ids=[ws.id],
                scopes=["design-system:read", "design-system:write"],
                expires_in_days=30,
            ),
        )
        token = token_res.token
        ws_id = ws.id
        await session.commit()

    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(ws_id)}

    palette_payload = {
        "text": {"primary": "#111111", "secondary": "#666666", "invert": "#ffffff"},
        "background": {"default": "#ffffff", "invert": "#111111"},
        "border": {"default": "#e5e5e5", "subtle": "#f0f0f0"},
        "link": {"default": "#0066cc", "hover": "#0052a3", "visited": "#551a8b"},
        "accent": ["#0066cc", "#28a745"],
    }

    # 1. 创建主题
    create_resp = await client.post(
        "/api/v1/themes",
        json={"key": "theme-immutable-key", "name": "Initial Name", "description": "Desc", "palette": palette_payload},
        headers={**headers, "Idempotency-Key": "idemp-create-theme-1"},
    )
    assert create_resp.status_code == 201
    theme_id = create_resp.json()["id"]

    # 2. 尝试修改 theme key -> 必须被拒绝 400 THEME_KEY_IMMUTABLE
    update_bad_resp = await client.patch(
        f"/api/v1/themes/{theme_id}",
        json={"key": "attempt-to-change-key", "name": "New Name"},
        headers={**headers, "Idempotency-Key": "idemp-update-bad-1"},
    )
    assert update_bad_resp.status_code == 400
    assert update_bad_resp.json()["code"] == "THEME_KEY_IMMUTABLE"

    # 3. 正常修改主题名称 -> 200 OK
    update_ok_resp = await client.patch(
        f"/api/v1/themes/{theme_id}",
        json={"name": "Updated Name", "key": "theme-immutable-key"},
        headers={**headers, "Idempotency-Key": "idemp-update-ok-1"},
    )
    assert update_ok_resp.status_code == 200
    assert update_ok_resp.json()["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_external_project_workspace_move_rejected(client: AsyncClient) -> None:
    """测试 PAT 不得通过 External API 修改项目所属工作空间。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username="project_move_user",
            password_hash="hash",
            display_name="Project Move User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()

        ws_a = Workspace(code="ws-move-a", name="Move A", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
        ws_b = Workspace(code="ws-move-b", name="Move B", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
        session.add_all([ws_a, ws_b])
        await session.flush()
        session.add_all(
            [
                WorkspaceMember(workspace_id=ws_a.id, user_id=user.id, role="owner", status=RecordStatus.ACTIVE.value),
                WorkspaceMember(workspace_id=ws_b.id, user_id=user.id, role="owner", status=RecordStatus.ACTIVE.value),
            ]
        )
        project = Project(
            workspace_id=ws_a.id,
            code="project-move-test",
            name="Move Test",
            theme_config_yaml="{}",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add(project)
        await session.flush()

        token_result = await ApiAccessTokenService(session).create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Project-Move-PAT",
                workspace_ids=[ws_a.id],
                scopes=["project:write"],
                expires_in_days=30,
            ),
        )
        project_id = project.id
        ws_a_id = ws_a.id
        ws_b_id = ws_b.id
        token = token_result.token
        await session.commit()

    response = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"workspace_id": ws_b_id},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Workspace-ID": str(ws_a_id),
            "Idempotency-Key": "project-move-rejected-1",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "PROJECT_WORKSPACE_MOVE_FORBIDDEN"


@pytest.mark.asyncio
async def test_access_tokens_scopes_and_capabilities(authenticated_client: AsyncClient) -> None:
    """测试获取可用 Scope 列表与工作空间能力接口。"""

    # 1. 测试 Web 端查询可用 Scopes 接口
    scopes_resp = await authenticated_client.get("/api/access-tokens/scopes")
    assert scopes_resp.status_code == 200
    scopes_data = scopes_resp.json()
    assert isinstance(scopes_data, list)
    assert len(scopes_data) > 0
    scope_keys = [item["scope"] for item in scopes_data]
    assert "project:read" in scope_keys
    assert "page:write" in scope_keys

    # 2. 测试通过 Bearer 鉴权查询工作空间 capabilities
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username="cap_user",
            password_hash="hash",
            display_name="Cap User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()

        ws = Workspace(code="ws-cap-01", name="Cap Space", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
        session.add(ws)
        await session.flush()

        member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner", status=RecordStatus.ACTIVE.value)
        session.add(member)
        await session.flush()

        pat_service = ApiAccessTokenService(session)
        token_res = await pat_service.create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Cap-PAT",
                workspace_ids=[ws.id],
                scopes=["project:read", "page:read"],
                expires_in_days=30,
            ),
        )
        token = token_res.token
        ws_id = ws.id
        await session.commit()

    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(ws_id)}
    cap_resp = await authenticated_client.get(f"/api/v1/workspaces/{ws_id}/capabilities", headers=headers)
    assert cap_resp.status_code == 200
    cap_data = cap_resp.json()
    assert cap_data["workspace_id"] == ws_id
    assert "project.list" in cap_data["operations"]
    assert "project.get" in cap_data["operations"]
    assert "page.get" in cap_data["operations"]
    assert "validate.entity" in cap_data["operations"]


@pytest.mark.asyncio
async def test_external_api_whoami_and_system_info(client: AsyncClient) -> None:
    """测试通过 PAT 访问 /auth/whoami 以及系统版本和规范接口。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username="whoami_user",
            password_hash="hash",
            display_name="Whoami User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()

        ws1 = Workspace(code="ws-who-01", name="Space 1", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
        ws2 = Workspace(code="ws-who-02", name="Space 2", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
        session.add_all([ws1, ws2])
        await session.flush()

        session.add(WorkspaceMember(workspace_id=ws1.id, user_id=user.id, role="owner", status=RecordStatus.ACTIVE.value))
        session.add(WorkspaceMember(workspace_id=ws2.id, user_id=user.id, role="owner", status=RecordStatus.ACTIVE.value))
        await session.flush()

        # 创建仅绑定 ws1 的 PAT
        pat_service = ApiAccessTokenService(session)
        token_res = await pat_service.create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Whoami-PAT",
                workspace_ids=[ws1.id],
                scopes=["workspace:read", "project:read", "page:read"],
                expires_in_days=30,
            ),
        )
        token = token_res.token
        ws1_id = ws1.id
        await session.commit()

    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(ws1_id)}

    # 1. 验证 whoami 响应结构与过滤
    who_resp = await client.get("/api/v1/auth/whoami", headers=headers)
    assert who_resp.status_code == 200
    who_data = who_resp.json()
    assert who_data["user"]["username"] == "whoami_user"
    assert isinstance(who_data["token"]["token_public_id"], str)
    assert len(who_data["token"]["token_public_id"]) == 16
    assert "workspace:read" in who_data["token"]["scopes"]
    # 仅能看到绑定的 ws1，不能看到未授权的 ws2
    ws_ids = [w["id"] for w in who_data["workspaces"]]
    assert ws1_id in ws_ids
    assert len(ws_ids) == 1

    # 2. 验证系统信息与页面规范接口
    ver_resp = await client.get("/api/v1/system/version", headers=headers)
    assert ver_resp.status_code == 200
    assert "version" in ver_resp.json()

    std_resp = await client.get("/api/v1/standards/page", headers=headers)
    assert std_resp.status_code == 200
    assert std_resp.json()["standard_type"] == "page"


@pytest.mark.asyncio
async def test_external_mutation_workspace_isolation_and_member_status(client: AsyncClient) -> None:
    """测试 PAT 限定空间与禁用成员无法进行 Mutation 任务创建、查询与取消。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username="iso_user",
            password_hash="hash",
            display_name="Iso User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()

        ws_allowed = Workspace(code="ws-iso-01", name="Allowed Space", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
        ws_forbidden = Workspace(code="ws-iso-02", name="Forbidden Space", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
        session.add_all([ws_allowed, ws_forbidden])
        await session.flush()

        member_allowed = WorkspaceMember(workspace_id=ws_allowed.id, user_id=user.id, role="owner", status=RecordStatus.ACTIVE.value)
        member_forbidden = WorkspaceMember(workspace_id=ws_forbidden.id, user_id=user.id, role="owner", status=RecordStatus.ACTIVE.value)
        session.add_all([member_allowed, member_forbidden])
        await session.flush()

        # PAT 仅授权 ws_allowed
        pat_service = ApiAccessTokenService(session)
        token_res = await pat_service.create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Iso-PAT",
                workspace_ids=[ws_allowed.id],
                scopes=["page:read", "page:write", "component:read", "component:write"],
                expires_in_days=30,
            ),
        )
        token = token_res.token
        ws_allowed_id = ws_allowed.id
        ws_forbidden_id = ws_forbidden.id
        await session.commit()

    # 1. 尝试向未绑定的 ws_forbidden 提交组件创建任务 -> 必须被拒绝 403 WORKSPACE_NOT_AUTHORIZED
    bad_headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(ws_forbidden_id), "Idempotency-Key": "idemp-iso-comp-1"}
    bad_resp = await client.post(
        "/api/v1/jobs/mutations/components",
        json={
            "workspace_id": ws_forbidden_id,
            "import_name": "ForbiddenComp",
            "name": "Forbidden Comp",
            "component_type": "custom",
            "source_code": "<template><div>Test</div></template>",
        },
        headers=bad_headers,
    )
    assert bad_resp.status_code == 403
    assert bad_resp.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"

    # 2. 向已授权空间提交组件创建任务 (使用 custom 别名) -> 202 Accepted
    ok_headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(ws_allowed_id), "Idempotency-Key": "idemp-iso-comp-2"}
    ok_resp = await client.post(
        "/api/v1/jobs/mutations/components",
        json={
            "workspace_id": ws_allowed_id,
            "import_name": "AllowedComp",
            "name": "Allowed Comp",
            "component_type": "custom",
            "source_code": "<template><div>Test</div></template>",
        },
        headers=ok_headers,
    )
    assert ok_resp.status_code == 202
    job_id = ok_resp.json()["job_id"]

    # 3. 正常查询任务状态 -> 200 OK
    status_resp = await client.get(f"/api/v1/jobs/mutations/{job_id}", headers=ok_headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["job_id"] == job_id

    # 4. 禁用该用户在 ws_allowed 中的成员身份
    async with session_factory() as session:
        member = await session.get(WorkspaceMember, member_allowed.id)
        member.status = RecordStatus.ARCHIVED.value
        await session.commit()

    # 5. 成员被禁用后查询任务状态 -> 403 PERMISSION_DENIED
    denied_status_resp = await client.get(f"/api/v1/jobs/mutations/{job_id}", headers=ok_headers)
    assert denied_status_resp.status_code == 403
    assert denied_status_resp.json()["code"] == "PERMISSION_DENIED"

    # 6. 成员被禁用后尝试取消任务 -> 403 PERMISSION_DENIED
    denied_cancel_resp = await client.post(f"/api/v1/jobs/mutations/{job_id}/cancel", headers=ok_headers)
    assert denied_cancel_resp.status_code == 403
    assert denied_cancel_resp.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_external_batch_archive_cross_workspace_idor(client: AsyncClient) -> None:
    """测试批量归档时，无法跨工作空间越权归档未授权空间的实体（IDOR 防御）。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username="idor_user",
            password_hash="hash",
            display_name="Idor User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()
        u_id = user.id

        ws_a = Workspace(code="ws-idor-a", name="Space A", created_by=u_id, updated_by=u_id, status=RecordStatus.ACTIVE.value)
        ws_b = Workspace(code="ws-idor-b", name="Space B", created_by=u_id, updated_by=u_id, status=RecordStatus.ACTIVE.value)
        session.add(ws_a)
        session.add(ws_b)
        await session.flush()
        ws_a_id = ws_a.id
        ws_b_id = ws_b.id

        mem_a = WorkspaceMember(workspace_id=ws_a_id, user_id=u_id, role="owner", created_by=u_id, updated_by=u_id, status=RecordStatus.ACTIVE.value)
        mem_b = WorkspaceMember(workspace_id=ws_b_id, user_id=u_id, role="owner", created_by=u_id, updated_by=u_id, status=RecordStatus.ACTIVE.value)
        session.add(mem_a)
        session.add(mem_b)
        await session.flush()

        # 在 ws_b 中创建一个项目
        from app.models.workspace import Project
        proj_b = Project(
            workspace_id=ws_b_id,
            code="proj-b-test",
            name="Project in B",
            theme_config_yaml="{}",
            created_by=u_id,
            updated_by=u_id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add(proj_b)
        await session.flush()
        proj_b_id = proj_b.id

        # 创建仅授权 ws_a 的 PAT
        pat_service = ApiAccessTokenService(session)
        token_res = await pat_service.create_token(
            user_id=u_id,
            payload=ApiAccessTokenCreateRequest(
                name="Idor-PAT",
                workspace_ids=[ws_a_id],
                scopes=["project:read", "project:write"],
                expires_in_days=30,
            ),
        )
        token = token_res.token
        await session.commit()

    # 携带 ws_a 的 Header，试图批量归档属于 ws_b 的项目 -> 必须被拒绝 403 WORKSPACE_NOT_AUTHORIZED
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(ws_a_id), "Idempotency-Key": "idemp-idor-1"}
    resp = await client.post(
        "/api/v1/projects/batch-archive",
        json={"ids": [proj_b_id], "reason": "malicious delete"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"


@pytest.mark.asyncio
async def test_external_capabilities_disabled_member_rejected(client: AsyncClient) -> None:
    """测试当成员被禁用时，无法查询对应工作空间 capabilities。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username="dis_cap_user",
            password_hash="hash",
            display_name="User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()
        u_id = user.id

        ws = Workspace(code="ws-dis-cap", name="Space", created_by=u_id, updated_by=u_id, status=RecordStatus.ACTIVE.value)
        session.add(ws)
        await session.flush()
        ws_id = ws.id

        member = WorkspaceMember(workspace_id=ws_id, user_id=u_id, role="owner", created_by=u_id, updated_by=u_id, status=RecordStatus.ACTIVE.value)
        session.add(member)
        await session.flush()

        pat_service = ApiAccessTokenService(session)
        token_res = await pat_service.create_token(
            user_id=u_id,
            payload=ApiAccessTokenCreateRequest(
                name="Cap-Disabled-PAT",
                workspace_ids=[ws_id],
                scopes=["workspace:read"],
                expires_in_days=30,
            ),
        )
        token = token_res.token

        # 禁用成员
        member.status = RecordStatus.ARCHIVED.value
        await session.commit()

    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(ws_id)}
    resp = await client.get(f"/api/v1/workspaces/{ws_id}/capabilities", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_external_single_archive_restore_idempotency(client: AsyncClient) -> None:
    """测试直接归档与恢复操作携带相同 Idempotency-Key 重放返回缓存响应。"""

    from app.models.workspace_theme import WorkspaceTheme

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username="idem_arch_user",
            password_hash="hash",
            display_name="User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()
        u_id = user.id

        ws = Workspace(code="ws-idem-arch", name="Space", created_by=u_id, updated_by=u_id, status=RecordStatus.ACTIVE.value)
        session.add(ws)
        await session.flush()
        ws_id = ws.id

        member = WorkspaceMember(workspace_id=ws_id, user_id=u_id, role="owner", created_by=u_id, updated_by=u_id, status=RecordStatus.ACTIVE.value)
        session.add(member)
        await session.flush()

        theme = WorkspaceTheme(
            workspace_id=ws_id,
            key="custom-theme-test",
            name="Theme Test",
            palette={
                "text": {"primary": "#111827", "secondary": "#4b5563", "invert": "#ffffff"},
                "background": {"default": "#ffffff", "invert": "#111827"},
                "border": {"default": "#d1d5db", "subtle": "#e5e7eb"},
                "link": {"default": "#2563eb", "hover": "#1d4ed8", "visited": "#4338ca"},
                "accent": ["#3b82f6"],
            },
            heading_font_label="Arial",
            body_font_label="Arial",
            code_font_label="monospace",
            created_by=u_id,
            updated_by=u_id,
        )
        session.add(theme)
        await session.flush()
        theme_id = theme.id

        pat_service = ApiAccessTokenService(session)
        token_res = await pat_service.create_token(
            user_id=u_id,
            payload=ApiAccessTokenCreateRequest(
                name="Arch-PAT",
                workspace_ids=[ws_id],
                scopes=["design-system:read", "design-system:write"],
                expires_in_days=30,
            ),
        )
        token = token_res.token
        await session.commit()

    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(ws_id), "Idempotency-Key": "idemp-theme-arch-1"}

    # 1. 首次归档
    del_resp1 = await client.post(f"/api/v1/themes/{theme_id}/archive", headers=headers)
    assert del_resp1.status_code == 200
    assert del_resp1.json()["message"] == "主题已成功归档"

    # 2. 携带相同 Idempotency-Key 再次重试归档 -> 应重放第一次的 200 响应
    del_resp2 = await client.post(f"/api/v1/themes/{theme_id}/archive", headers=headers)
    assert del_resp2.status_code == 200
    assert del_resp2.json()["message"] == "主题已成功归档"

    # 首版 External API 不暴露 Restore；归档后的生命周期操作到此结束。


@pytest.mark.asyncio
async def test_external_api_page_screenshot(client: AsyncClient) -> None:
    """测试通过 External API v1 获取页面最新截图契约。"""

    from unittest.mock import AsyncMock, patch
    from app.models.page import Page
    from app.services.page_screenshot_service import PageScreenshotResult

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username="screenshot_user",
            password_hash="hash",
            display_name="Screenshot User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()

        ws = Workspace(code="ws-shot-01", name="Screenshot Space", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
        session.add(ws)
        await session.flush()

        member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner", status=RecordStatus.ACTIVE.value)
        session.add(member)
        await session.flush()

        proj = Project(workspace_id=ws.id, code="proj-shot", name="Shot Proj", theme_config_yaml="{}", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)

        session.add(proj)
        await session.flush()

        page = Page(
            workspace_id=ws.id,
            project_id=proj.id,
            code="p1",
            title="Page 1",
            page_content="<template><div>Shot</div></template>",
            current_version_no=1,
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )

        session.add(page)
        await session.flush()
        page_id = page.id
        ws_id = ws.id

        pat_service = ApiAccessTokenService(session)
        # 1. 仅授予只读 page:read 权限
        token_read_only_res = await pat_service.create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Page-Read-PAT",
                workspace_ids=[ws.id],
                scopes=["page:read"],
                expires_in_days=30,
            ),
        )
        # 2. 授予 page:read + preview:run 权限
        token_full_res = await pat_service.create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Page-Shot-PAT",
                workspace_ids=[ws.id],
                scopes=["page:read", "preview:run"],
                expires_in_days=30,
            ),
        )
        token_read_only = token_read_only_res.token
        token_full = token_full_res.token
        await session.commit()

    headers_read_only = {"Authorization": f"Bearer {token_read_only}", "X-Workspace-ID": str(ws_id)}
    headers_full = {"Authorization": f"Bearer {token_full}", "X-Workspace-ID": str(ws_id)}
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR_SHOT"
    fake_result = PageScreenshotResult(
        page=page,
        page_item=None,  # type: ignore
        storage_key="test/shot.png",
        content=fake_png,
        refreshed=True,
        public_url="http://test/shot.png",
    )

    # 1. 缺少 preview:run 权限 -> 403 INSUFFICIENT_SCOPE
    forbidden_resp = await client.get(f"/api/v1/pages/{page_id}/screenshot", headers=headers_read_only)
    assert forbidden_resp.status_code == 403
    assert forbidden_resp.json()["code"] == "INSUFFICIENT_SCOPE"

    # 2. 具备完整的 page:read + preview:run 权限 -> 200 OK 且返回 PNG
    with patch(
        "app.services.page_screenshot_job_service.PageScreenshotJobService.ensure_latest_page_screenshot_via_queue",
        new=AsyncMock(return_value=fake_result),
    ):
        resp = await client.get(f"/api/v1/pages/{page_id}/screenshot", headers=headers_full)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.headers["x-page-id"] == str(page_id)
        assert resp.content == fake_png

    # 3. 检查工作空间能力查询接口包含 page.screenshot.latest 操作注册
    cap_resp = await client.get(f"/api/v1/workspaces/{ws_id}/capabilities", headers=headers_full)
    assert cap_resp.status_code == 200
    available_ops = cap_resp.json().get("operations", [])
    assert "page.screenshot.latest" in available_ops

    # 4. 仅有 page:read 权限的 Token 查 capabilities 不应包含 page.screenshot.latest
    read_only_cap_resp = await client.get(f"/api/v1/workspaces/{ws_id}/capabilities", headers=headers_read_only)
    assert read_only_cap_resp.status_code == 200
    read_only_ops = read_only_cap_resp.json().get("operations", [])
    assert "page.screenshot.latest" not in read_only_ops
