"""文件功能：统一 Models.dev 的供应商/模型 SDK 声明与平台运行协议映射。"""

from __future__ import annotations

PROVIDER_PROTOCOL_OVERRIDES = {
    "openai": "openai_chat",
    "openrouter": "openrouter_chat",
    "google": "google_chat",
    "google-vertex": "google_chat",
    "alibaba": "alibaba_openai_compatible",
    "alibaba-cn": "alibaba_openai_compatible",
    "deepseek": "deepseek_openai_compatible",
    "xiaomi": "xiaomi_openai_compatible",
    "ollama-cloud": "ollama_openai_compatible",
}

SUPPORTED_NPM_PROTOCOLS = {
    "@ai-sdk/openai": "openai_chat",
    "@ai-sdk/openai-compatible": "openai_compatible_chat",
    "@ai-sdk/google": "google_chat",
    "@openrouter/ai-sdk-provider": "openrouter_chat",
}

# 模型级覆盖只能映射到当前已经接入的协议。
# @ai-sdk/openai 在 OpenCode 等混合供应商中通常对应 Responses API；该协议尚未
# 纳入当前运行时，因此不能沿用供应商默认的 OpenAI-compatible 协议，也不能入目录。
SUPPORTED_MODEL_NPM_PROTOCOLS = {
    "@ai-sdk/openai-compatible": "openai_compatible_chat",
    "@ai-sdk/google": "google_chat",
    "@openrouter/ai-sdk-provider": "openrouter_chat",
}


def resolve_catalog_protocol(provider_key: str, npm_package: str | None) -> str | None:
    """把供应商级 Models.dev npm 声明映射为平台已实现的协议。"""

    override = PROVIDER_PROTOCOL_OVERRIDES.get(provider_key)
    if override is not None:
        return override
    return SUPPORTED_NPM_PROTOCOLS.get(str(npm_package or "").strip())


def resolve_model_catalog_protocol(
    provider_key: str,
    provider_npm_package: str | None,
    model_npm_package: str | None = None,
) -> str | None:
    """解析模型最终协议；模型级 npm 覆盖优先，无法实现的协议返回 None。"""

    normalized_model_npm = str(model_npm_package or "").strip()
    if not normalized_model_npm:
        return resolve_catalog_protocol(provider_key, provider_npm_package)

    # OpenAI 自有供应商的同协议声明继续使用现有 Chat Completions 适配器；
    # 其它显式覆盖必须命中模型级白名单，不能错误回退到供应商默认协议。
    if provider_key == "openai" and normalized_model_npm == "@ai-sdk/openai":
        return "openai_chat"
    return SUPPORTED_MODEL_NPM_PROTOCOLS.get(normalized_model_npm)
