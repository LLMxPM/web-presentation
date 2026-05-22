"""文件功能：验证多用户管理、工作空间隔离与全局/个人模型配置规则。"""

from httpx import AsyncClient


async def _login(client: AsyncClient, username: str, password: str) -> dict:
    """使用指定账号登录，并返回当前用户信息。"""

    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["user"]


async def _logout(client: AsyncClient) -> None:
    """退出当前登录态，便于同一测试客户端切换用户。"""

    response = await client.post("/api/auth/logout")
    assert response.status_code == 200


async def _create_user(
    client: AsyncClient,
    *,
    username: str,
    password: str = "User123456",
    display_name: str = "普通用户",
    role: str = "workspace_user",
) -> dict:
    """由当前管理员创建平台用户。"""

    response = await client.post(
        "/api/users",
        json={
            "username": username,
            "password": password,
            "display_name": display_name,
            "role": role,
            "status": "active",
        },
    )
    assert response.status_code == 201
    return response.json()


async def _create_workspace(client: AsyncClient, name: str) -> int:
    """用当前用户创建工作空间，并返回工作空间 ID。"""

    response = await client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def test_user_management_should_require_platform_admin_and_protect_last_admin(client: AsyncClient) -> None:
    """普通用户不能管理用户；最后一个启用管理员不能被禁用或降级。"""

    admin = await _login(client, "admin", "Admin123456")
    user = await _create_user(client, username="alice", display_name="Alice")

    disable_last_admin_response = await client.patch(
        f"/api/users/{admin['id']}",
        json={"status": "archived"},
    )
    assert disable_last_admin_response.status_code == 409
    assert disable_last_admin_response.json()["code"] == "USER_LAST_ADMIN_PROTECTED"

    demote_last_admin_response = await client.patch(
        f"/api/users/{admin['id']}",
        json={"role": "workspace_user"},
    )
    assert demote_last_admin_response.status_code == 409
    assert demote_last_admin_response.json()["code"] == "USER_LAST_ADMIN_PROTECTED"

    await _logout(client)
    await _login(client, "alice", "User123456")

    forbidden_response = await client.get("/api/users")
    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["code"] == "USER_ADMIN_REQUIRED"

    reset_response = await client.post(
        f"/api/users/{user['id']}/reset-password",
        json={"new_password": "Next123456"},
    )
    assert reset_response.status_code == 403


async def test_workspace_membership_should_isolate_users_and_admins(client: AsyncClient) -> None:
    """用户只能看到自己的成员工作空间，平台管理员也不会隐式进入用户空间。"""

    await _login(client, "admin", "Admin123456")
    await _create_user(client, username="bob", display_name="Bob")
    admin_workspace_id = await _create_workspace(client, "管理员工作空间")

    await _logout(client)
    await _login(client, "bob", "User123456")
    user_workspace_id = await _create_workspace(client, "Bob 工作空间")

    user_list_response = await client.get("/api/workspaces")
    assert user_list_response.status_code == 200
    assert [item["id"] for item in user_list_response.json()["items"]] == [user_workspace_id]

    user_read_admin_workspace_response = await client.get(f"/api/workspaces/{admin_workspace_id}")
    assert user_read_admin_workspace_response.status_code == 403
    assert user_read_admin_workspace_response.json()["code"] == "WORKSPACE_ACCESS_DENIED"

    await _logout(client)
    await _login(client, "admin", "Admin123456")

    admin_list_response = await client.get("/api/workspaces")
    assert admin_list_response.status_code == 200
    assert [item["id"] for item in admin_list_response.json()["items"]] == [admin_workspace_id]

    admin_read_user_workspace_response = await client.get(f"/api/workspaces/{user_workspace_id}")
    assert admin_read_user_workspace_response.status_code == 403
    assert admin_read_user_workspace_response.json()["code"] == "WORKSPACE_ACCESS_DENIED"


async def test_global_and_personal_llm_configs_should_follow_scope_rules(client: AsyncClient) -> None:
    """管理员全局模型可被用户选择但不可修改，个人绑定优先于全局默认。"""

    await _login(client, "admin", "Admin123456")
    await _create_user(client, username="carol", display_name="Carol")

    global_model_response = await client.post(
        "/api/ai/llm-configs",
        json={
            "scope": "global",
            "name": "平台默认模型",
            "provider_key": "openai",
            "model_id": "gpt-4.1-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-global",
            "advanced_config_json": {},
        },
    )
    assert global_model_response.status_code == 201
    global_model = global_model_response.json()
    assert global_model["scope"] == "global"
    assert global_model["editable"] is True

    global_slot_response = await client.put(
        "/api/ai/llm-slots/agent_coordinator",
        json={"llm_config_id": global_model["id"], "scope": "global"},
    )
    assert global_slot_response.status_code == 200
    assert global_slot_response.json()["binding_ready"] is True

    await _logout(client)
    await _login(client, "carol", "User123456")

    list_response = await client.get("/api/ai/llm-configs")
    assert list_response.status_code == 200
    visible_models = {item["id"]: item for item in list_response.json()}
    assert visible_models[global_model["id"]]["scope"] == "global"
    assert visible_models[global_model["id"]]["editable"] is False

    update_global_response = await client.patch(
        f"/api/ai/llm-configs/{global_model['id']}",
        json={"name": "尝试修改全局模型"},
    )
    assert update_global_response.status_code == 403
    assert update_global_response.json()["code"] == "AI_LLM_GLOBAL_READONLY"

    create_global_response = await client.post(
        "/api/ai/llm-configs",
        json={
            "scope": "global",
            "name": "越权全局模型",
            "provider_key": "openai",
            "model_id": "gpt-4.1-mini",
            "advanced_config_json": {},
        },
    )
    assert create_global_response.status_code == 403
    assert create_global_response.json()["code"] == "AI_LLM_GLOBAL_ADMIN_REQUIRED"

    inherited_slots_response = await client.get("/api/ai/llm-slots")
    assert inherited_slots_response.status_code == 200
    inherited_slot = {item["slot"]: item for item in inherited_slots_response.json()}["agent_coordinator"]
    assert inherited_slot["llm_config_id"] == global_model["id"]
    assert inherited_slot["inherited_from_global"] is True

    personal_model_response = await client.post(
        "/api/ai/llm-configs",
        json={
            "name": "Carol 个人模型",
            "provider_key": "openai",
            "model_id": "gpt-4.1",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-personal",
            "advanced_config_json": {},
        },
    )
    assert personal_model_response.status_code == 201
    personal_model = personal_model_response.json()
    assert personal_model["scope"] == "personal"
    assert personal_model["editable"] is True

    personal_slot_response = await client.put(
        "/api/ai/llm-slots/agent_coordinator",
        json={"llm_config_id": personal_model["id"]},
    )
    assert personal_slot_response.status_code == 200
    assert personal_slot_response.json()["llm_config_id"] == personal_model["id"]
    assert personal_slot_response.json()["inherited_from_global"] is False

