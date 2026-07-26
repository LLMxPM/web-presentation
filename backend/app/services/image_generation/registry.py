"""文件功能：维护图片生成供应商、适配器工厂和模型能力的单一注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.core.exceptions import AppException
from app.services.image_generation.contracts import ImageGenerationAdapter, ImageModelSpec

OPENAI_IMAGE_DOCS_URL = "https://developers.openai.com/api/docs/guides/image-generation"
DASHSCOPE_IMAGE_DOCS_URL = "https://help.aliyun.com/en/model-studio/wan-image-generation-and-editing-api-reference"

_COMMON_RATIOS = ("auto", "1:1", "3:2", "2:3")

_OPENAI_ADVANCED_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "background": {"type": "string", "enum": ["auto", "opaque"]},
        "output_format": {"type": "string", "enum": ["png", "jpeg", "webp"]},
        "output_compression": {"type": "integer", "minimum": 0, "maximum": 100},
        "moderation": {"type": "string", "enum": ["auto", "low"]},
    },
}

_DASHSCOPE_ADVANCED_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "execution_mode": {"type": "string", "enum": ["async", "sync"]},
        "watermark": {"type": "boolean"},
        "thinking_mode": {"type": "boolean"},
    },
}


@dataclass(slots=True, frozen=True)
class ImageProviderSpec:
    """描述一个图片供应商的目录元数据、连接约束和模型集合。"""

    provider_key: str
    label: str
    docs_url: str
    adapter_factory: Callable[[], ImageGenerationAdapter]
    supports_base_url: bool
    requires_base_url: bool
    default_base_url: str | None
    base_url_hint: str | None
    default_model_id: str
    models: tuple[ImageModelSpec, ...]
    validate_base_url: Callable[[str | None], None] | None = None

    @property
    def adapter_path(self) -> str:
        """返回真实适配器类路径，供目录展示和防漂移测试使用。"""

        adapter_type = self.adapter_factory
        return f"{adapter_type.__module__}.{adapter_type.__qualname__}"


def _validate_dashscope_base_url(base_url: str | None) -> None:
    """校验百炼图片供应商的 HTTPS Base URL。"""

    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized.startswith("https://"):
        raise AppException(
            status_code=400,
            code="AI_LLM_BASE_URL_INVALID",
            detail="百炼图片供应商 Base URL 必须使用 HTTPS。",
        )


def _build_registry() -> dict[str, ImageProviderSpec]:
    """延迟导入适配器并构造唯一供应商注册表。"""

    from app.services.dashscope_image_generation_adapter import DashScopeImageGenerationAdapter
    from app.services.image_generation_adapters import OpenAiImageGenerationAdapter

    openai_model = ImageModelSpec(
        model_id="gpt-image-2",
        label="GPT Image 2",
        operations=("generate", "edit"),
        aspect_ratios=_COMMON_RATIOS,
        resolution_tiers=("auto", "standard"),
        quality_options=("auto", "low", "medium", "high"),
        max_reference_images=4,
        max_output_count=4,
        supports_mask=True,
        advanced_schema=_OPENAI_ADVANCED_SCHEMA,
        advanced_defaults={"background": "auto", "output_format": "png", "moderation": "auto"},
        allow_custom_model_id=True,
    )
    dashscope_models = tuple(
        ImageModelSpec(
            model_id=model_id,
            label=label,
            operations=("generate", "edit"),
            aspect_ratios=_COMMON_RATIOS,
            resolution_tiers=("auto", "standard", "high", "ultra"),
            quality_options=("auto",),
            max_reference_images=4,
            max_output_count=4,
            supports_mask=False,
            advanced_schema=_DASHSCOPE_ADVANCED_SCHEMA,
            advanced_defaults={"execution_mode": "async", "watermark": False},
        )
        for model_id, label in (("wan2.7-image-pro", "Wan 2.7 Image Pro"), ("wan2.7-image", "Wan 2.7 Image"))
    )
    return {
        "openai_image": ImageProviderSpec(
            provider_key="openai_image",
            label="OpenAI 图片",
            docs_url=OPENAI_IMAGE_DOCS_URL,
            adapter_factory=OpenAiImageGenerationAdapter,
            supports_base_url=True,
            requires_base_url=False,
            default_base_url="https://api.openai.com/v1",
            base_url_hint=None,
            default_model_id=openai_model.model_id,
            models=(openai_model,),
        ),
        "dashscope_image": ImageProviderSpec(
            provider_key="dashscope_image",
            label="阿里云百炼图片",
            docs_url=DASHSCOPE_IMAGE_DOCS_URL,
            adapter_factory=DashScopeImageGenerationAdapter,
            supports_base_url=True,
            requires_base_url=True,
            default_base_url=None,
            base_url_hint="例如：https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1",
            default_model_id="wan2.7-image-pro",
            models=dashscope_models,
            validate_base_url=_validate_dashscope_base_url,
        ),
    }


IMAGE_PROVIDER_REGISTRY = _build_registry()


def list_image_provider_specs() -> list[ImageProviderSpec]:
    """按展示名称返回所有图片供应商。"""

    return sorted(IMAGE_PROVIDER_REGISTRY.values(), key=lambda item: item.label.lower())


def get_image_provider_spec(provider_key: str) -> ImageProviderSpec:
    """按固定 provider key 获取图片供应商定义。"""

    spec = IMAGE_PROVIDER_REGISTRY.get(str(provider_key or "").strip())
    if spec is None:
        raise AppException(status_code=400, code="AI_IMAGE_GENERATION_PROVIDER_UNSUPPORTED", detail="当前供应商不是可用的图片生成供应商。")
    return spec


def get_image_model_spec(provider_key: str, model_id: str) -> ImageModelSpec:
    """获取已知模型能力；仅显式允许自定义 ID 的供应商可使用回退能力。"""

    provider = get_image_provider_spec(provider_key)
    normalized = str(model_id or "").strip()
    for model in provider.models:
        if model.model_id == normalized:
            return model
    fallback = next((model for model in provider.models if model.allow_custom_model_id), None)
    if fallback is not None:
        return fallback
    raise AppException(status_code=400, code="AI_IMAGE_GENERATION_MODEL_UNSUPPORTED", detail="当前图片供应商不支持该模型 ID。")


def get_image_generation_adapter(config) -> ImageGenerationAdapter:  # noqa: ANN001
    """由唯一供应商注册表创建与模型配置匹配的适配器。"""

    return get_image_provider_spec(config.provider_config.provider_key).adapter_factory()


def validate_image_provider_connection(provider_key: str, base_url: str | None) -> None:
    """执行供应商注册的额外连接配置校验。"""

    spec = get_image_provider_spec(provider_key)
    if spec.validate_base_url is not None:
        spec.validate_base_url(base_url)
