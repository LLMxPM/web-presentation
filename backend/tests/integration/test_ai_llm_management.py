"""文件功能：验证用户级大模型管理接口、槽位绑定与模型解析能力。"""

from __future__ import annotations

from httpx import AsyncClient

from app.ai.pydantic_model_resolver import PydanticLlmModelResolver
from app.ai.secret_cipher import LlmSecretCipher
from app.models.ai_llm import AiLlmConfig, AiLlmProviderConfig
from app.models.enums import RecordStatus


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建一个工作空间并返回主键。"""

    response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _create_project(authenticated_client: AsyncClient, workspace_id: int, name: str) -> int:
    """创建一个项目并返回主键。"""

    response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _create_page(
    authenticated_client: AsyncClient,
    *,
    workspace_id: int,
    project_id: int,
    title: str,
) -> int:
    """创建一个页面并返回主键。"""

    response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": title,
            "page_content": "<template><div>ai</div></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _create_llm_provider_config(
    authenticated_client: AsyncClient,
    *,
    name: str,
    provider_key: str = "openai",
    base_url: str | None = "https://api.openai.com/v1",
    api_key: str | None = "sk-session-provider",
) -> dict:
    """创建一个测试用供应商配置。"""

    response = await authenticated_client.post(
        "/api/ai/llm-provider-configs",
        json={
            "name": name,
            "provider_key": provider_key,
            "base_url": base_url,
            "api_key": api_key,
        },
    )
    assert response.status_code == 201
    return response.json()


async def _create_llm_config(
    authenticated_client: AsyncClient,
    *,
    name: str,
    supports_image_input: bool = False,
) -> dict:
    """创建一个测试用个人大模型配置。"""

    provider = await _create_llm_provider_config(
        authenticated_client,
        name=f"{name} 供应商",
    )
    response = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": name,
            "provider_config_id": provider["id"],
            "model_id": "gpt-4.1-mini",
            "supports_image_input": supports_image_input,
            "advanced_config_json": {},
        },
    )
    assert response.status_code == 201
    return response.json()


async def _create_agent_project_scope(authenticated_client: AsyncClient, name: str) -> tuple[int, int]:
    """创建内容助手可启动的项目级 scope。"""

    workspace_id = await _create_workspace(authenticated_client, f"{name} 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, f"{name} 项目")
    return workspace_id, project_id


async def test_llm_provider_catalog_should_only_include_supported_providers(authenticated_client: AsyncClient) -> None:
    """供应商目录接口应只返回平台保留的 provider 元数据。"""

    response = await authenticated_client.get("/api/ai/llm-providers")
    assert response.status_code == 200

    providers = {item["provider_key"]: item for item in response.json()}
    assert set(providers) == {
        "dashscope",
        "deepseek",
        "google",
        "mimo",
        "nvidia",
        "ollama",
        "openai",
        "openai_like",
        "openrouter",
    }
    for provider_key in providers:
        assert provider_key in providers
        assert providers[provider_key]["label"]
        assert providers[provider_key]["provider_adapter"].startswith("pydantic_ai.")
        assert providers[provider_key]["docs_url"].startswith("https://")
    assert providers["ollama"]["supports_thinking"] is True
    assert providers["ollama"]["thinking_mode"] == "ollama_think"
    assert providers["ollama"]["default_base_url"] == "http://localhost:11434"
    assert providers["ollama"]["default_model_id"] == "llama3.1"
    assert providers["ollama"]["default_thinking_effort"] == "medium"
    assert providers["ollama"]["thinking_effort_options"] == ["low", "medium", "high"]
    assert providers["google"]["supports_thinking"] is True
    assert providers["google"]["thinking_mode"] == "google_thinking_level"
    assert providers["google"]["default_model_id"] == "gemini-flash-latest"
    assert providers["google"]["thinking_effort_options"] == ["low", "high"]
    assert providers["openai"]["default_base_url"] == "https://api.openai.com/v1"
    assert providers["openrouter"]["default_base_url"] == "https://openrouter.ai/api/v1"
    assert providers["openrouter"]["thinking_mode"] == "openrouter_reasoning"
    assert providers["openrouter"]["advanced_json_hint"] == {}
    assert providers["dashscope"]["default_model_id"] == "qwen-plus"
    assert providers["nvidia"]["default_model_id"] == "meta/llama-3.3-70b-instruct"
    assert providers["deepseek"]["thinking_mode"] == "openai_extra_body_thinking"
    assert providers["deepseek"]["default_base_url"] == "https://api.deepseek.com"
    assert providers["deepseek"]["default_model_id"] == "deepseek-v4-pro"
    assert providers["deepseek"]["default_thinking_enabled"] is True
    assert providers["deepseek"]["default_context_window_tokens"] == 1_000_000
    assert providers["deepseek"]["default_max_output_tokens"] == 384_000
    assert providers["deepseek"]["thinking_effort_options"] == ["high", "max"]
    assert providers["mimo"]["default_base_url"] == "https://api.xiaomimimo.com/v1"
    assert providers["mimo"]["default_model_id"] == "mimo-v2.5"
    assert providers["mimo"]["default_thinking_enabled"] is True
    assert providers["mimo"]["default_context_window_tokens"] == 1_000_000
    assert providers["mimo"]["default_max_output_tokens"] == 32_768
    assert providers["mimo"]["default_supports_image_input"] is True
    assert all(item["advanced_json_hint"] == {} for item in providers.values())


async def test_llm_provider_and_config_crud_should_split_secret_from_model(authenticated_client: AsyncClient) -> None:
    """供应商配置负责密钥脱敏，模型配置只引用供应商并维护模型参数。"""

    provider_response = await authenticated_client.post(
        "/api/ai/llm-provider-configs",
        json={
            "name": "OpenRouter 工作账号",
            "provider_key": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-or-v1-test-secret",
        },
    )
    assert provider_response.status_code == 201
    provider = provider_response.json()
    assert provider["has_api_key"] is True
    assert provider["api_key_masked"] != "sk-or-v1-test-secret"
    assert provider["provider_label"] == "OpenRouter"

    create_response = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "OpenRouter 主模型",
            "provider_config_id": provider["id"],
            "model_id": "openai/gpt-4.1-mini",
            "thinking_enabled": True,
            "thinking_effort": "xhigh",
            "advanced_config_json": {"temperature": 0.2},
        },
    )
    assert create_response.status_code == 201
    created_item = create_response.json()
    assert created_item["provider_config_id"] == provider["id"]
    assert created_item["provider_config_name"] == "OpenRouter 工作账号"
    assert created_item["provider_label"] == "OpenRouter"
    assert created_item["context_window_tokens"] == 128000
    assert created_item["max_output_tokens"] == 32000
    assert created_item["history_token_ratio"] == 0.5
    assert created_item["compression_target_ratio"] == 0.1
    assert created_item["thinking_effort"] == "xhigh"

    config_id = created_item["id"]
    detail_response = await authenticated_client.get(f"/api/ai/llm-configs/{config_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["advanced_config_json"] == {"temperature": 0.2}

    protected_key_response = await authenticated_client.patch(
        f"/api/ai/llm-configs/{config_id}",
        json={
            "advanced_config_json": {"api_key": "should-fail"},
        },
    )
    assert protected_key_response.status_code == 400
    assert protected_key_response.json()["code"] == "AI_LLM_ADVANCED_CONFIG_CONFLICT"

    clear_secret_response = await authenticated_client.patch(
        f"/api/ai/llm-provider-configs/{provider['id']}",
        json={"api_key": ""},
    )
    assert clear_secret_response.status_code == 200
    assert clear_secret_response.json()["has_api_key"] is False
    assert clear_secret_response.json()["api_key_masked"] is None

    update_response = await authenticated_client.patch(
        f"/api/ai/llm-configs/{config_id}",
        json={
            "name": "OpenRouter 归档模型",
            "status": "archived",
            "context_window_tokens": 128000,
            "max_output_tokens": 8192,
            "history_token_ratio": 0.35,
            "compression_target_ratio": 0.2,
            "advanced_config_json": {"temperature": 0.5},
        },
    )
    assert update_response.status_code == 200
    updated_item = update_response.json()
    assert updated_item["name"] == "OpenRouter 归档模型"
    assert updated_item["status"] == "archived"
    assert updated_item["context_window_tokens"] == 128000
    assert updated_item["max_output_tokens"] == 8192
    assert updated_item["history_token_ratio"] == 0.35
    assert updated_item["compression_target_ratio"] == 0.2
    assert updated_item["advanced_config_json"] == {"temperature": 0.5}


async def test_llm_config_should_accept_large_context_model_limits(authenticated_client: AsyncClient) -> None:
    """大模型配置应允许百万级上下文与超过旧 20 万限制的输出 token。"""

    provider = await _create_llm_provider_config(
        authenticated_client,
        name="OpenRouter 长上下文供应商",
        provider_key="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-v1-large-context",
    )
    response = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "百万上下文模型",
            "provider_config_id": provider["id"],
            "model_id": "openai/gpt-4.1-long-context",
            "context_window_tokens": 1_000_000,
            "max_output_tokens": 300_000,
            "advanced_config_json": {},
        },
    )

    assert response.status_code == 201
    created_item = response.json()
    assert created_item["context_window_tokens"] == 1_000_000
    assert created_item["max_output_tokens"] == 300_000


async def test_llm_config_should_reject_mimo_output_above_provider_limit(authenticated_client: AsyncClient) -> None:
    """MiMo 配置不应允许保存超过供应商硬限制的输出 token。"""

    provider = await _create_llm_provider_config(
        authenticated_client,
        name="MiMo 供应商",
        provider_key="mimo",
        base_url="https://api.xiaomimimo.com/v1",
        api_key="sk-mimo-test",
    )
    response = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "MiMo 超限模型",
            "provider_config_id": provider["id"],
            "model_id": "mimo-v2.5",
            "context_window_tokens": 1_000_000,
            "max_output_tokens": 200_000,
            "advanced_config_json": {},
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "AI_LLM_MAX_OUTPUT_TOKENS_UNSUPPORTED"


async def test_llm_slot_binding_should_drive_agent_binding_state(authenticated_client: AsyncClient) -> None:
    """当前固定槽位绑定后，Agent 列表应返回已绑定的大模型信息。"""

    provider = await _create_llm_provider_config(
        authenticated_client,
        name="OpenAI 槽位供应商",
        api_key="sk-test-openai",
    )
    config_response = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "总控模型",
            "provider_config_id": provider["id"],
            "model_id": "gpt-4.1-mini",
            "thinking_enabled": True,
            "thinking_effort": "low",
            "advanced_config_json": {},
        },
    )
    assert config_response.status_code == 201
    config_id = config_response.json()["id"]

    update_slot_response = await authenticated_client.put(
        "/api/ai/llm-slots/agent_coordinator",
        json={"llm_config_id": config_id},
    )
    assert update_slot_response.status_code == 200
    assert update_slot_response.json()["binding_ready"] is True
    assert update_slot_response.json()["llm_config_name"] == "总控模型"

    update_component_slot_response = await authenticated_client.put(
        "/api/ai/llm-slots/component_manager",
        json={"llm_config_id": config_id},
    )
    assert update_component_slot_response.status_code == 200
    assert update_component_slot_response.json()["binding_ready"] is True
    assert update_component_slot_response.json()["llm_config_name"] == "总控模型"

    update_resource_slot_response = await authenticated_client.put(
        "/api/ai/llm-slots/resource_manager",
        json={"llm_config_id": config_id},
    )
    assert update_resource_slot_response.status_code == 200
    assert update_resource_slot_response.json()["binding_ready"] is True
    assert update_resource_slot_response.json()["llm_config_name"] == "总控模型"

    slots_response = await authenticated_client.get("/api/ai/llm-slots")
    assert slots_response.status_code == 200
    slots = {item["slot"]: item for item in slots_response.json()}
    assert set(slots) == {"agent_coordinator", "component_manager", "resource_manager"}
    assert slots["agent_coordinator"]["binding_ready"] is True
    assert slots["agent_coordinator"]["provider_label"] == "OpenAI"
    assert slots["component_manager"]["binding_ready"] is True
    assert slots["component_manager"]["provider_label"] == "OpenAI"
    assert slots["resource_manager"]["binding_ready"] is True
    assert slots["resource_manager"]["provider_label"] == "OpenAI"

    removed_slot_response = await authenticated_client.put(
        "/api/ai/llm-slots/page_editor",
        json={"llm_config_id": config_id},
    )
    assert removed_slot_response.status_code == 400
    assert removed_slot_response.json()["code"] == "AI_LLM_SLOT_UNSUPPORTED"

    workspace_id = await _create_workspace(authenticated_client, "AI LLM 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI LLM 项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI LLM 页面",
    )

    agents_response = await authenticated_client.get(
        "/api/ai/agents",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
        },
    )
    assert agents_response.status_code == 200
    agents = {item["id"]: item for item in agents_response.json()}
    assert set(agents) == {"agent-coordinator", "component-manager", "resource-manager"}
    component_agent = agents["component-manager"]
    coordinator_agent = agents["agent-coordinator"]
    resource_agent = agents["resource-manager"]
    assert coordinator_agent["llm_slot"] == "agent_coordinator"
    assert coordinator_agent["llm_binding_ready"] is True
    assert coordinator_agent["bound_llm_name"] == "总控模型"
    assert coordinator_agent["bound_provider_label"] == "OpenAI"
    assert component_agent["llm_slot"] == "component_manager"
    assert component_agent["llm_binding_ready"] is True
    assert component_agent["bound_llm_name"] == "总控模型"
    assert component_agent["bound_provider_label"] == "OpenAI"
    assert resource_agent["llm_slot"] == "resource_manager"
    assert resource_agent["llm_binding_ready"] is True
    assert resource_agent["bound_llm_name"] == "总控模型"
    assert resource_agent["bound_provider_label"] == "OpenAI"
    assert agents["agent-coordinator"]["entry_kind"] == "team"
    assert agents["agent-coordinator"]["scope_type"] == "workspace"
    assert agents["component-manager"]["scope_type"] == "workspace"
    assert agents["resource-manager"]["scope_type"] == "workspace"


async def test_agent_session_should_persist_explicit_personal_llm_config(authenticated_client: AsyncClient) -> None:
    """创建会话时显式选择个人模型，应把具体配置固化到 metadata.llm。"""

    config = await _create_llm_config(
        authenticated_client,
        name="会话个人模型",
        supports_image_input=True,
    )
    workspace_id, project_id = await _create_agent_project_scope(authenticated_client, "显式模型会话")

    response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "agent-coordinator",
            "session_name": "显式模型会话",
            "scope": {
                "scope_type": "project",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "source": "test-agent-session",
            },
            "llm_config_id": config["id"],
        },
    )

    assert response.status_code == 201
    llm_metadata = response.json()["metadata"]["llm"]
    assert llm_metadata == {
        "selection_kind": "explicit_config",
        "config_id": config["id"],
        "scope": "personal",
        "name": "会话个人模型",
        "provider_config_id": config["provider_config_id"],
        "provider_config_name": config["provider_config_name"],
        "provider_key": "openai",
        "provider_label": "OpenAI",
        "model_id": "gpt-4.1-mini",
        "supports_image_input": True,
    }


async def test_agent_session_should_reject_unavailable_selected_llm_config(authenticated_client: AsyncClient) -> None:
    """会话显式模型选择应拒绝归档模型和不存在模型。"""

    config = await _create_llm_config(authenticated_client, name="归档会话模型")
    archive_response = await authenticated_client.patch(
        f"/api/ai/llm-configs/{config['id']}",
        json={"status": "archived"},
    )
    assert archive_response.status_code == 200
    workspace_id, project_id = await _create_agent_project_scope(authenticated_client, "归档模型会话")
    scope_payload = {
        "scope_type": "project",
        "workspace_id": workspace_id,
        "project_id": project_id,
        "source": "test-agent-session",
    }

    archived_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "agent-coordinator",
            "session_name": "归档模型会话",
            "scope": scope_payload,
            "llm_config_id": config["id"],
        },
    )
    assert archived_response.status_code == 409
    assert archived_response.json()["code"] == "AI_LLM_CONFIG_DISABLED"

    missing_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "agent-coordinator",
            "session_name": "不存在模型会话",
            "scope": scope_payload,
            "llm_config_id": 999_999_999,
        },
    )
    assert missing_response.status_code == 404
    assert missing_response.json()["code"] == "AI_LLM_CONFIG_NOT_FOUND"


async def test_agent_session_without_llm_config_should_fallback_to_slot_binding(authenticated_client: AsyncClient) -> None:
    """旧客户端未传 llm_config_id 时，应继续按当前智能体槽位绑定创建会话。"""

    config = await _create_llm_config(authenticated_client, name="槽位兼容模型")
    slot_response = await authenticated_client.put(
        "/api/ai/llm-slots/agent_coordinator",
        json={"llm_config_id": config["id"]},
    )
    assert slot_response.status_code == 200
    workspace_id, project_id = await _create_agent_project_scope(authenticated_client, "槽位兼容会话")

    response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "agent-coordinator",
            "session_name": "槽位兼容会话",
            "scope": {
                "scope_type": "project",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "source": "test-agent-session",
            },
        },
    )

    assert response.status_code == 201
    llm_metadata = response.json()["metadata"]["llm"]
    assert llm_metadata["selection_kind"] == "slot_binding"
    assert llm_metadata["config_id"] == config["id"]
    assert llm_metadata["name"] == "槽位兼容模型"


def test_llm_model_resolver_should_build_common_provider_models() -> None:
    """模型解析器应能构造常见供应商的 Pydantic AI 模型对象与运行参数。"""

    cipher = LlmSecretCipher()
    resolver = PydanticLlmModelResolver()

    def build_config(*, id: int, provider_key: str, model_id: str, api_key: str = "sk-test", **kwargs) -> AiLlmConfig:
        """构造激活状态的大模型配置，聚焦 provider 差异字段。"""

        base_url = kwargs.pop("base_url", None)
        provider_config = AiLlmProviderConfig(
            id=id + 100,
            user_id=1,
            scope="personal",
            name=f"{provider_key} 供应商",
            provider_key=provider_key,
            base_url=base_url,
            api_key_ciphertext=cipher.encrypt(api_key),
            status=RecordStatus.ACTIVE.value,
        )
        return AiLlmConfig(
            id=id,
            user_id=1,
            scope="personal",
            name=kwargs.pop("name", provider_key),
            provider_config_id=provider_config.id,
            provider_config=provider_config,
            model_id=model_id,
            advanced_config_json=kwargs.pop("advanced_config_json", {}),
            status=RecordStatus.ACTIVE.value,
            **kwargs,
        )

    openai_config = build_config(
        id=1,
        provider_key="openai",
        model_id="gpt-4.1-mini",
        base_url="https://api.openai.com/v1",
        thinking_enabled=True,
        thinking_effort="medium",
    )
    openai_model = resolver.resolve_model(openai_config)
    assert openai_model.__class__.__name__ == "OpenAIChatModel"
    assert openai_model.model_name == "gpt-4.1-mini"
    assert resolver.resolve_model_settings(openai_config)["openai_reasoning_effort"] == "medium"

    openrouter_config = build_config(
        id=2,
        provider_key="openrouter",
        model_id="openai/gpt-4.1-mini",
        api_key="sk-openrouter-test",
        base_url="https://openrouter.ai/api/v1",
        thinking_enabled=True,
        thinking_effort="xhigh",
    )
    openrouter_model = resolver.resolve_model(openrouter_config)
    assert openrouter_model.__class__.__name__ == "OpenRouterModel"
    assert openrouter_model.model_name == "openai/gpt-4.1-mini"
    assert resolver.resolve_model_settings(openrouter_config)["openrouter_reasoning"] == {"effort": "xhigh"}

    dashscope_config = build_config(
        id=3,
        provider_key="dashscope",
        model_id="qwen-plus",
        api_key="sk-dashscope-test",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        thinking_enabled=True,
        thinking_effort="medium",
    )
    dashscope_model = resolver.resolve_model(dashscope_config)
    assert dashscope_model.__class__.__name__ == "OpenAIChatModel"
    assert dashscope_model.model_name == "qwen-plus"
    assert resolver.resolve_model_settings(dashscope_config)["extra_body"] == {
        "enable_thinking": True,
        "thinking_budget": 5000,
    }

    openai_like_config = build_config(
        id=4,
        provider_key="openai_like",
        model_id="custom-model",
        api_key="sk-compatible-test",
        base_url="https://api.example.com/v1",
        thinking_enabled=True,
        thinking_effort="max",
    )
    openai_like_model = resolver.resolve_model(openai_like_config)
    assert openai_like_model.__class__.__name__ == "OpenAIChatModel"
    assert openai_like_model.model_name == "custom-model"
    assert resolver.resolve_model_settings(openai_like_config)["openai_reasoning_effort"] == "max"

    deepseek_config = build_config(
        id=8,
        provider_key="deepseek",
        model_id="deepseek-v4-flash",
        api_key="sk-deepseek-test",
        base_url="https://api.deepseek.com",
        thinking_enabled=True,
        thinking_effort="xhigh",
    )
    deepseek_model = resolver.resolve_model(deepseek_config)
    assert deepseek_model.__class__.__name__ == "OpenAIChatModel"
    assert resolver.resolve_model_settings(deepseek_config) == {
        "openai_reasoning_effort": "max",
        "extra_body": {"thinking": {"type": "enabled"}},
    }

    deepseek_disabled_config = build_config(
        id=9,
        name="deepseek-disabled",
        provider_key="deepseek",
        model_id="deepseek-v4-flash",
        api_key="sk-deepseek-test",
        base_url="https://api.deepseek.com",
        thinking_enabled=False,
    )
    deepseek_disabled_model = resolver.resolve_model(deepseek_disabled_config)
    assert deepseek_disabled_model.__class__.__name__ == "OpenAIChatModel"
    assert resolver.resolve_model_settings(deepseek_disabled_config) == {
        "extra_body": {"thinking": {"type": "disabled"}},
    }

    deepseek_legacy_effort_config = build_config(
        id=12,
        name="deepseek-legacy-effort",
        provider_key="deepseek",
        model_id="deepseek-v4-pro",
        api_key="sk-deepseek-test",
        base_url="https://api.deepseek.com",
        thinking_enabled=True,
        thinking_effort="medium",
    )
    deepseek_legacy_effort_model = resolver.resolve_model(deepseek_legacy_effort_config)
    assert deepseek_legacy_effort_model.__class__.__name__ == "OpenAIChatModel"
    assert resolver.resolve_model_settings(deepseek_legacy_effort_config) == {
        "openai_reasoning_effort": "high",
        "extra_body": {"thinking": {"type": "enabled"}},
    }

    deepseek_custom_config = build_config(
        id=10,
        name="deepseek-custom",
        provider_key="deepseek",
        model_id="deepseek-v4-pro",
        api_key="sk-deepseek-test",
        base_url="https://api.deepseek.com",
        thinking_enabled=True,
        thinking_effort="medium",
        advanced_config_json={
            "openai_reasoning_effort": "max",
            "timeout": 60,
            "retries": 0,
            "extra_body": {"thinking": {"type": "disabled"}, "custom": "value"},
        },
    )
    deepseek_custom_model = resolver.resolve_model(deepseek_custom_config)
    assert deepseek_custom_model.__class__.__name__ == "OpenAIChatModel"
    assert resolver.resolve_model_settings(deepseek_custom_config) == {
        "openai_reasoning_effort": "max",
        "timeout": 60,
        "retries": 0,
        "extra_body": {
            "thinking": {"type": "enabled"},
            "custom": "value",
        },
    }

    ollama_config = build_config(
        id=5,
        provider_key="ollama",
        model_id="llama3.1",
        api_key="",
        base_url="http://localhost:11434",
        thinking_enabled=True,
        thinking_effort="medium",
    )
    ollama_model = resolver.resolve_model(ollama_config)
    assert ollama_model.__class__.__name__ == "OpenAIChatModel"
    assert ollama_model.model_name == "llama3.1"
    assert resolver.resolve_model_settings(ollama_config)["extra_body"] == {"think": "medium"}

    ollama_custom_think_config = build_config(
        id=7,
        name="ollama-custom-think",
        provider_key="ollama",
        model_id="gpt-oss:20b",
        api_key="",
        base_url="http://localhost:11434",
        thinking_enabled=True,
        thinking_effort="low",
        advanced_config_json={"extra_body": {"think": "high"}},
    )
    ollama_custom_think_model = resolver.resolve_model(ollama_custom_think_config)
    assert ollama_custom_think_model.__class__.__name__ == "OpenAIChatModel"
    assert resolver.resolve_model_settings(ollama_custom_think_config)["extra_body"] == {"think": "low"}

    google_config = build_config(
        id=11,
        provider_key="google",
        model_id="gemini-2.5-pro",
        api_key="sk-google-test",
        thinking_enabled=True,
        thinking_effort="low",
    )
    google_model = resolver.resolve_model(google_config)
    assert google_model.__class__.__name__ == "GoogleModel"
    assert google_model.model_name == "gemini-2.5-pro"
    assert resolver.resolve_model_settings(google_config)["google_thinking_config"] == {
        "thinking_level": "LOW",
        "include_thoughts": True,
    }

    nvidia_config = build_config(
        id=6,
        provider_key="nvidia",
        model_id="meta/llama-3.3-70b-instruct",
        api_key="nvapi-test",
        base_url="https://integrate.api.nvidia.com/v1",
        thinking_enabled=True,
    )
    nvidia_model = resolver.resolve_model(nvidia_config)
    assert nvidia_model.__class__.__name__ == "OpenAIChatModel"
    assert nvidia_model.model_name == "meta/llama-3.3-70b-instruct"

    mimo_config = build_config(
        id=13,
        provider_key="mimo",
        model_id="mimo-v2.5",
        api_key="sk-mimo-test",
        base_url="https://api.xiaomimimo.com/v1",
        thinking_enabled=True,
        thinking_effort="max",
        max_output_tokens=320_000,
    )
    mimo_model = resolver.resolve_model(mimo_config)
    assert mimo_model.__class__.__name__ == "OpenAIChatModel"
    assert mimo_model.model_name == "mimo-v2.5"
    assert resolver.resolve_model_settings(mimo_config) == {
        "max_tokens": 131_072,
        "extra_body": {"thinking": {"type": "enabled"}},
    }
