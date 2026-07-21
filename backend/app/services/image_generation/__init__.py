"""文件功能：导出图片生成统一协议、供应商注册表和模型能力查询入口。"""

from app.services.image_generation.contracts import (
    GeneratedImage,
    ImageGenerationAdapter,
    ImageGenerationInput,
    ImageModelSpec,
    ImageProviderResult,
    ProviderTaskCursor,
)
from app.services.image_generation.registry import (
    get_image_generation_adapter,
    get_image_model_spec,
    get_image_provider_spec,
    list_image_provider_specs,
)

__all__ = [
    "GeneratedImage",
    "ImageGenerationAdapter",
    "ImageGenerationInput",
    "ImageModelSpec",
    "ImageProviderResult",
    "ProviderTaskCursor",
    "get_image_generation_adapter",
    "get_image_model_spec",
    "get_image_provider_spec",
    "list_image_provider_specs",
]
