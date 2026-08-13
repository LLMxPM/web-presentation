"""文件功能：验证拆分后的 Chat/Image 模型配置、目录和槽位绑定集成契约。"""

from __future__ import annotations

from httpx import AsyncClient


async def _chat_provider(client: AsyncClient, *, custom: bool = False) -> dict:
    """创建目录或自定义聊天供应商。"""

    payload = {
        "name": "自定义兼容连接" if custom else "OpenAI 连接",
        "custom": custom,
        "catalog_provider_key": None if custom else "openai",
        "base_url": "https://compatible.example/v1" if custom else "https://api.openai.com/v1",
        "api_key": "sk-chat-test",
    }
    response = await client.post("/api/ai/chat-provider-configs", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _chat_model(client: AsyncClient, provider_id: int, *, tool_call: bool = True) -> dict:
    """创建显式声明能力的聊天模型。"""

    response = await client.post("/api/ai/chat-model-configs", json={
        "name": "内容模型",
        "provider_config_id": provider_id,
        "model_id": "manual-chat-model",
        "capability_override": {
            "context_tokens": 200_000,
            "input_tokens": 191_808,
            "output_tokens": 8_192,
            "supports_tool_call": tool_call,
            "supports_reasoning": True,
        },
        "advanced_config": {"temperature": 0.2},
    })
    assert response.status_code == 201, response.text
    return response.json()


async def _image_model(client: AsyncClient) -> dict:
    """创建独立的图片供应商和模型。"""

    provider = await client.post("/api/ai/image-provider-configs", json={
        "name": "OpenAI 图片连接",
        "provider_key": "openai_image",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-image-test",
    })
    assert provider.status_code == 201, provider.text
    model = await client.post("/api/ai/image-model-configs", json={
        "name": "图片模型",
        "provider_config_id": provider.json()["id"],
        "model_id": "gpt-image-2",
        "advanced_config": {},
    })
    assert model.status_code == 201, model.text
    return model.json()


async def test_catalog_and_provider_protocol_are_server_controlled(authenticated_client: AsyncClient) -> None:
    """目录只展示已实现协议，连接响应不泄露密钥且协议不可由用户覆盖。"""

    catalog = await authenticated_client.get("/api/ai/chat-provider-catalog")
    assert catalog.status_code == 200
    assert all(item["protocol_key"] not in {"anthropic", "bedrock", "openai_responses"} for item in catalog.json())

    provider = await _chat_provider(authenticated_client)
    assert provider["protocol_key"] == "openai_chat"
    assert provider["has_api_key"] is True
    assert "sk-chat-test" not in str(provider)


async def test_custom_compatible_requires_base_url_and_only_auto_reasoning(authenticated_client: AsyncClient) -> None:
    """自定义供应商不回退 OpenAI 地址，也不能接受未知方言的推理参数。"""

    rejected = await authenticated_client.post("/api/ai/chat-provider-configs", json={
        "name": "缺少地址", "custom": True, "catalog_provider_key": None, "api_key": "sk-test",
    })
    assert rejected.status_code == 422

    provider = await _chat_provider(authenticated_client, custom=True)
    model = await _chat_model(authenticated_client, provider["id"])
    binding = await authenticated_client.put("/api/ai/chat-model-bindings/agent_coordinator", json={
        "model_config_id": model["id"],
        "policy": {"reasoning": {"mode": "disabled"}, "input_budget_tokens": None, "output_budget_tokens": None},
    })
    assert binding.status_code == 422

    accepted = await authenticated_client.put("/api/ai/chat-model-bindings/agent_coordinator", json={
        "model_config_id": model["id"],
    })
    assert accepted.status_code == 200


async def test_capability_override_cannot_spoof_catalog_metadata(authenticated_client: AsyncClient) -> None:
    """用户只能覆盖客观能力字段，不能伪造目录来源和验证状态。"""

    provider = await _chat_provider(authenticated_client, custom=True)
    rejected = await authenticated_client.post("/api/ai/chat-model-configs", json={
        "name": "伪造目录模型",
        "provider_config_id": provider["id"],
        "model_id": "manual-model",
        "capability_override": {"source": "models.dev", "verified": True},
    })
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "AI_CHAT_CAPABILITY_OVERRIDE_INVALID"


async def test_chat_binding_only_validates_slot_capability(authenticated_client: AsyncClient) -> None:
    """槽位只绑定模型并校验客观能力，不再接收推理或 token 预算。"""

    provider = await _chat_provider(authenticated_client)
    unsupported = await _chat_model(authenticated_client, provider["id"], tool_call=False)
    rejected = await authenticated_client.put("/api/ai/chat-model-bindings/agent_coordinator", json={"model_config_id": unsupported["id"]})
    assert rejected.status_code == 409

    supported = await _chat_model(authenticated_client, provider["id"])
    bound = await authenticated_client.put("/api/ai/chat-model-bindings/agent_coordinator", json={"model_config_id": supported["id"]})
    assert bound.status_code == 200
    assert "policy" not in bound.json()
    assert "effective_output_budget_tokens" not in bound.json()
    assert bound.json()["provider_config_id"] == provider["id"]
    assert bound.json()["provider_name"] == "OpenAI"
    assert bound.json()["model_id"] == "manual-chat-model"

    rejected_policy = await authenticated_client.put("/api/ai/chat-model-bindings/agent_coordinator", json={
        "model_config_id": supported["id"],
        "policy": {"reasoning": {"mode": "auto"}, "input_budget_tokens": 195_000, "output_budget_tokens": 8_192},
    })
    assert rejected_policy.status_code == 422


async def test_chat_and_image_domains_cannot_cross_bind(authenticated_client: AsyncClient) -> None:
    """两类模型使用独立 ID 域、接口和槽位，交叉绑定会被拒绝。"""

    provider = await _chat_provider(authenticated_client)
    chat = await _chat_model(authenticated_client, provider["id"])
    image = await _image_model(authenticated_client)

    wrong_image = await authenticated_client.put("/api/ai/image-model-bindings/image_generation", json={"model_config_id": chat["id"] + 100_000})
    wrong_chat = await authenticated_client.put("/api/ai/chat-model-bindings/agent_coordinator", json={"model_config_id": image["id"] + 100_000})
    assert wrong_image.status_code == 404
    assert wrong_chat.status_code == 404

    bound = await authenticated_client.put("/api/ai/image-model-bindings/image_generation", json={"model_config_id": image["id"]})
    assert bound.status_code == 200
    assert bound.json()["binding_ready"] is True
    assert bound.json()["provider_key"] == "openai_image"
    assert bound.json()["model_id"] == "gpt-image-2"


async def test_removed_mixed_endpoints_return_not_found(authenticated_client: AsyncClient) -> None:
    """旧混合接口一次性移除，不形成隐式兼容层。"""

    for path in ("/api/ai/llm-providers", "/api/ai/llm-provider-configs", "/api/ai/llm-configs", "/api/ai/llm-slots"):
        response = await authenticated_client.get(path)
        assert response.status_code == 404
