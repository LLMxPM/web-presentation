"""文件功能：验证管理中心可独立读取全局聊天槽位且不会混入个人绑定。"""

from httpx import AsyncClient


async def test_binding_scope_reads_raw_binding_and_enforces_admin(authenticated_client: AsyncClient) -> None:
    """默认读取个人生效值；显式范围读取原始绑定，普通用户不可读取管理快照。"""

    client = authenticated_client
    endpoint = "/api/ai/chat-model-bindings/agent_coordinator"
    model_ids: dict[str, int] = {}
    for scope in ("global", "personal"):
        provider = await client.post(
            "/api/ai/chat-provider-configs",
            json={"scope": scope, "name": f"{scope} 供应商", "catalog_provider_key": "openai", "api_key": "test-key"},
        )
        assert provider.status_code == 201
        model = await client.post(
            "/api/ai/chat-model-configs",
            json={
                "scope": scope, "name": f"{scope} 模型", "provider_config_id": provider.json()["id"],
                "model_id": "gpt-4.1-mini", "capability_override": {"supports_tool_call": True},
            },
        )
        assert model.status_code == 201
        model_ids[scope] = model.json()["id"]
        binding = await client.put(endpoint, json={"scope": scope, "model_config_id": model_ids[scope]})
        assert binding.status_code == 200

    effective = await client.get(endpoint)
    assert effective.status_code == 200
    assert effective.json()["model_config_id"] == model_ids["personal"]
    global_binding = await client.get(endpoint, params={"scope": "global"})
    assert global_binding.status_code == 200
    assert global_binding.json()["model_config_id"] == model_ids["global"]
    assert global_binding.json()["inherited_from_global"] is False

    cleared = await client.put(endpoint, json={"scope": "global", "model_config_id": None})
    assert cleared.status_code == 200
    raw_empty = await client.get(endpoint, params={"scope": "global"})
    assert raw_empty.json()["model_config_id"] is None
    assert (await client.get(endpoint)).json()["model_config_id"] == model_ids["personal"]
    assert (await client.get(endpoint, params={"scope": "invalid"})).status_code == 422

    created_user = await client.post(
        "/api/users", json={"username": "reader", "display_name": "普通用户", "password": "User123456", "role": "workspace_user"},
    )
    assert created_user.status_code == 201
    await client.post("/api/auth/logout")
    login = await client.post("/api/auth/login", json={"username": "reader", "password": "User123456"})
    assert login.status_code == 200
    forbidden = await client.get(endpoint, params={"scope": "global"})
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "AI_CHAT_GLOBAL_ADMIN_REQUIRED"
    assert (await client.get(endpoint, params={"scope": "personal"})).status_code == 200
