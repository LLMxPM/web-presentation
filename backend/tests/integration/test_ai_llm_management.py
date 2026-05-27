"""文件功能：验证用户级大模型管理接口、槽位绑定与模型解析能力。"""

from __future__ import annotations

from agno.media import Image
from agno.models.message import Message
from httpx import AsyncClient

from app.ai.model_resolver import LlmModelResolver
from app.ai.providers.mimo import MiMo
from app.ai.secret_cipher import LlmSecretCipher
from app.models.ai_llm import AiLlmConfig
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
        assert providers[provider_key]["agno_class_path"]
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
    assert providers["mimo"]["default_model_id"] is None
    assert providers["mimo"]["default_supports_image_input"] is False
    assert all(item["advanced_json_hint"] == {} for item in providers.values())


async def test_llm_config_crud_should_encrypt_and_mask_api_key(authenticated_client: AsyncClient) -> None:
    """创建和更新大模型配置时，应加密保存 API Key 并只向前端返回脱敏值。"""

    create_response = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "OpenRouter 主模型",
            "provider_key": "openrouter",
            "model_id": "openai/gpt-4.1-mini",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-or-v1-test-secret",
            "thinking_enabled": True,
            "thinking_effort": "xhigh",
            "advanced_config_json": {"temperature": 0.2},
        },
    )
    assert create_response.status_code == 201
    created_item = create_response.json()
    assert created_item["has_api_key"] is True
    assert created_item["api_key_masked"] != "sk-or-v1-test-secret"
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

    update_response = await authenticated_client.patch(
        f"/api/ai/llm-configs/{config_id}",
        json={
            "name": "OpenRouter 归档模型",
            "api_key": "",
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
    assert updated_item["has_api_key"] is False
    assert updated_item["api_key_masked"] is None
    assert updated_item["context_window_tokens"] == 128000
    assert updated_item["max_output_tokens"] == 8192
    assert updated_item["history_token_ratio"] == 0.35
    assert updated_item["compression_target_ratio"] == 0.2
    assert updated_item["advanced_config_json"] == {"temperature": 0.5}


async def test_llm_config_should_accept_large_context_model_limits(authenticated_client: AsyncClient) -> None:
    """大模型配置应允许百万级上下文与超过旧 20 万限制的输出 token。"""

    response = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "百万上下文模型",
            "provider_key": "openrouter",
            "model_id": "openai/gpt-4.1-long-context",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-or-v1-large-context",
            "context_window_tokens": 1_000_000,
            "max_output_tokens": 300_000,
            "advanced_config_json": {},
        },
    )

    assert response.status_code == 201
    created_item = response.json()
    assert created_item["context_window_tokens"] == 1_000_000
    assert created_item["max_output_tokens"] == 300_000


async def test_llm_slot_binding_should_drive_agent_binding_state(authenticated_client: AsyncClient) -> None:
    """当前固定槽位绑定后，Agent 列表应返回已绑定的大模型信息。"""

    config_response = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "总控模型",
            "provider_key": "openai",
            "model_id": "gpt-4.1-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-openai",
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


def test_llm_model_resolver_should_build_common_provider_models() -> None:
    """模型解析器应能构造常见供应商的 Agno 模型对象。"""

    cipher = LlmSecretCipher()
    resolver = LlmModelResolver()

    openai_model = resolver.resolve_model(
        AiLlmConfig(
            id=1,
            user_id=1,
            name="openai",
            provider_key="openai",
            model_id="gpt-4.1-mini",
            base_url="https://api.openai.com/v1",
            api_key_ciphertext=cipher.encrypt("sk-openai-test"),
            thinking_enabled=True,
            advanced_config_json={},
            status=RecordStatus.ACTIVE.value,
        )
    )
    assert openai_model.__class__.__name__ == "OpenAIResponses"
    assert getattr(openai_model, "reasoning_effort", None) is None

    openrouter_model = resolver.resolve_model(
        AiLlmConfig(
            id=2,
            user_id=1,
            name="openrouter",
            provider_key="openrouter",
            model_id="openai/gpt-4.1-mini",
            base_url="https://openrouter.ai/api/v1",
            api_key_ciphertext=cipher.encrypt("sk-openrouter-test"),
            thinking_enabled=True,
            thinking_effort="xhigh",
            advanced_config_json={},
            status=RecordStatus.ACTIVE.value,
        )
    )
    assert openrouter_model.__class__.__name__ == "OpenRouter"
    assert getattr(openrouter_model, "reasoning_effort", None) == "xhigh"

    dashscope_model = resolver.resolve_model(
        AiLlmConfig(
            id=3,
            user_id=1,
            name="dashscope",
            provider_key="dashscope",
            model_id="qwen-plus",
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            api_key_ciphertext=cipher.encrypt("sk-dashscope-test"),
            thinking_enabled=True,
            thinking_effort="medium",
            advanced_config_json={},
            status=RecordStatus.ACTIVE.value,
        )
    )
    assert dashscope_model.__class__.__name__ == "DashScope"
    assert getattr(dashscope_model, "enable_thinking", None) is True
    assert getattr(dashscope_model, "thinking_budget", None) == 5000

    openai_like_model = resolver.resolve_model(
        AiLlmConfig(
            id=4,
            user_id=1,
            name="openai_like",
            provider_key="openai_like",
            model_id="custom-model",
            base_url="https://api.example.com/v1",
            api_key_ciphertext=cipher.encrypt("sk-compatible-test"),
            thinking_enabled=True,
            thinking_effort="max",
            advanced_config_json={},
            status=RecordStatus.ACTIVE.value,
        )
    )
    assert openai_like_model.__class__.__name__ == "OpenAILike"
    assert getattr(openai_like_model, "base_url", None) == "https://api.example.com/v1"
    assert getattr(openai_like_model, "reasoning_effort", None) == "max"

    deepseek_model = resolver.resolve_model(
        AiLlmConfig(
            id=8,
            user_id=1,
            name="deepseek",
            provider_key="deepseek",
            model_id="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
            api_key_ciphertext=cipher.encrypt("sk-deepseek-test"),
            thinking_enabled=True,
            thinking_effort="xhigh",
            advanced_config_json={},
            status=RecordStatus.ACTIVE.value,
        )
    )
    assert deepseek_model.__class__.__name__ == "DeepSeek"
    assert getattr(deepseek_model, "reasoning_effort", None) == "max"
    assert getattr(deepseek_model, "extra_body", None) == {"thinking": {"type": "enabled"}}
    assert getattr(deepseek_model, "timeout", None) is None
    assert getattr(deepseek_model, "retries", None) == 0

    deepseek_disabled_model = resolver.resolve_model(
        AiLlmConfig(
            id=9,
            user_id=1,
            name="deepseek-disabled",
            provider_key="deepseek",
            model_id="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
            api_key_ciphertext=cipher.encrypt("sk-deepseek-test"),
            thinking_enabled=False,
            advanced_config_json={},
            status=RecordStatus.ACTIVE.value,
        )
    )
    assert deepseek_disabled_model.__class__.__name__ == "DeepSeek"
    assert getattr(deepseek_disabled_model, "reasoning_effort", None) is None
    assert getattr(deepseek_disabled_model, "extra_body", None) == {"thinking": {"type": "disabled"}}
    assert getattr(deepseek_disabled_model, "timeout", None) is None

    deepseek_legacy_effort_model = resolver.resolve_model(
        AiLlmConfig(
            id=12,
            user_id=1,
            name="deepseek-legacy-effort",
            provider_key="deepseek",
            model_id="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key_ciphertext=cipher.encrypt("sk-deepseek-test"),
            thinking_enabled=True,
            thinking_effort="medium",
            advanced_config_json={},
            status=RecordStatus.ACTIVE.value,
        )
    )
    assert getattr(deepseek_legacy_effort_model, "reasoning_effort", None) == "high"
    assert getattr(deepseek_legacy_effort_model, "extra_body", None) == {"thinking": {"type": "enabled"}}

    deepseek_custom_model = resolver.resolve_model(
        AiLlmConfig(
            id=10,
            user_id=1,
            name="deepseek-custom",
            provider_key="deepseek",
            model_id="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key_ciphertext=cipher.encrypt("sk-deepseek-test"),
            thinking_enabled=True,
            thinking_effort="medium",
            advanced_config_json={
                "reasoning_effort": "max",
                "timeout": 60,
                "retries": 0,
                "extra_body": {"thinking": {"type": "disabled"}, "custom": "value"},
            },
            status=RecordStatus.ACTIVE.value,
        )
    )
    assert getattr(deepseek_custom_model, "reasoning_effort", None) == "max"
    assert getattr(deepseek_custom_model, "timeout", None) == 60
    assert getattr(deepseek_custom_model, "retries", None) == 0
    assert getattr(deepseek_custom_model, "extra_body", None) == {
        "thinking": {"type": "enabled"},
        "custom": "value",
    }

    ollama_model = resolver.resolve_model(
        AiLlmConfig(
            id=5,
            user_id=1,
            name="ollama",
            provider_key="ollama",
            model_id="llama3.1",
            base_url="http://localhost:11434",
            api_key_ciphertext=cipher.encrypt(""),
            thinking_enabled=True,
            thinking_effort="medium",
            advanced_config_json={},
            status=RecordStatus.ACTIVE.value,
        )
    )
    assert ollama_model.__class__.__name__ == "Ollama"
    assert getattr(ollama_model, "host", None) == "http://localhost:11434"
    assert getattr(ollama_model, "request_params", None) == {"think": "medium"}

    ollama_custom_think_model = resolver.resolve_model(
        AiLlmConfig(
            id=7,
            user_id=1,
            name="ollama-custom-think",
            provider_key="ollama",
            model_id="gpt-oss:20b",
            base_url="http://localhost:11434",
            api_key_ciphertext=cipher.encrypt(""),
            thinking_enabled=True,
            thinking_effort="low",
            advanced_config_json={"request_params": {"think": "high"}},
            status=RecordStatus.ACTIVE.value,
        )
    )
    assert ollama_custom_think_model.__class__.__name__ == "Ollama"
    assert getattr(ollama_custom_think_model, "request_params", None) == {"think": "high"}

    google_model = resolver.resolve_model(
        AiLlmConfig(
            id=11,
            user_id=1,
            name="google",
            provider_key="google",
            model_id="gemini-2.5-pro",
            api_key_ciphertext=cipher.encrypt("sk-google-test"),
            thinking_enabled=True,
            thinking_effort="low",
            advanced_config_json={},
            status=RecordStatus.ACTIVE.value,
        )
    )
    assert google_model.__class__.__name__ == "Gemini"
    assert getattr(google_model, "thinking_level", None) == "low"

    nvidia_model = resolver.resolve_model(
        AiLlmConfig(
            id=6,
            user_id=1,
            name="nvidia",
            provider_key="nvidia",
            model_id="meta/llama-3.3-70b-instruct",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key_ciphertext=cipher.encrypt("nvapi-test"),
            thinking_enabled=True,
            advanced_config_json={},
            status=RecordStatus.ACTIVE.value,
        )
    )
    assert nvidia_model.__class__.__name__ == "Nvidia"
    assert getattr(nvidia_model, "reasoning_effort", None) is None

    mimo_model = resolver.resolve_model(
        AiLlmConfig(
            id=13,
            user_id=1,
            name="mimo",
            provider_key="mimo",
            model_id="mimo-v2.5",
            base_url="https://api.xiaomimimo.com/v1",
            api_key_ciphertext=cipher.encrypt("sk-mimo-test"),
            thinking_enabled=True,
            thinking_effort="max",
            advanced_config_json={},
            status=RecordStatus.ACTIVE.value,
        )
    )
    assert mimo_model.__class__.__name__ == "MiMo"
    assert getattr(mimo_model, "base_url", None) == "https://api.xiaomimimo.com/v1"
    assert getattr(mimo_model, "reasoning_effort", None) is None
    assert getattr(mimo_model, "extra_body", None) == {"thinking": {"type": "enabled"}}


def test_mimo_formatter_should_preserve_reasoning_content_and_strip_image_detail() -> None:
    """MiMo formatter 应回传历史 reasoning_content，并生成无 detail 的 image_url parts。"""

    model = MiMo(id="mimo-v2.5", api_key="sk-mimo-test")
    formatted = model._format_message(
        Message(
            role="assistant",
            content="先看图",
            reasoning_content="上一轮思考",
            images=[Image(content=b"image-bytes", mime_type="image/png", detail="auto")],
        )
    )

    assert formatted["reasoning_content"] == "上一轮思考"
    assert formatted["content"][0] == {"type": "text", "text": "先看图"}
    image_part = formatted["content"][1]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
    assert "detail" not in image_part["image_url"]
