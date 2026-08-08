"""文件功能：提供返回固定合法 PNG 的图片生成测试适配器，不发起任何 HTTP 调用。"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from app.services.image_generation.contracts import (
    GeneratedImage,
    ImageGenerationInput,
    ImageProviderResult,
    ProviderTaskCursor,
    validate_model_request,
)

if TYPE_CHECKING:
    from app.models.ai_llm import AiLlmConfig
    from app.services.image_generation.contracts import ImageModelSpec

# 固定 16x16 纯色（#2563EB）PNG；内容恒定，保证断言可复现且不做像素级比较。
_FIXED_MOCK_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAFklEQVR4nGNQTX5NEmIY1TCq"
    "YfhqAAB2SXMQ7mVTQgAAAABJRU5ErkJggg=="
)
FIXED_MOCK_PNG = base64.b64decode(_FIXED_MOCK_PNG_BASE64)
FIXED_MOCK_PNG_CONTENT_TYPE = "image/png"


class E2eMockImageGenerationAdapter:
    """mock 模式下的图片生成适配器：同步返回固定 PNG 并继续走真实资源落库链路。"""

    def validate(self, config: "AiLlmConfig", model: "ImageModelSpec", request: ImageGenerationInput) -> None:
        """复用模型能力校验，保证 mock 路径与真实路径参数边界一致。"""

        _ = config
        validate_model_request(model, request)

    async def submit(
        self,
        config: "AiLlmConfig",
        model: "ImageModelSpec",
        request: ImageGenerationInput,
    ) -> ImageProviderResult:
        """同步完成：按请求数量返回同一张固定 PNG，不访问任何供应商。"""

        _ = (config, model)
        return ImageProviderResult(
            status="completed",
            images=[
                GeneratedImage(content=FIXED_MOCK_PNG, content_type=FIXED_MOCK_PNG_CONTENT_TYPE)
                for _ in range(request.count)
            ],
        )

    async def resume(
        self,
        config: "AiLlmConfig",
        model: "ImageModelSpec",
        cursor: ProviderTaskCursor,
    ) -> ImageProviderResult:
        """mock 任务不存在异步游标；恢复时返回与提交一致的固定结果。"""

        _ = (config, model, cursor)
        return ImageProviderResult(
            status="completed",
            images=[GeneratedImage(content=FIXED_MOCK_PNG, content_type=FIXED_MOCK_PNG_CONTENT_TYPE)],
        )

    async def cancel(self, config: "AiLlmConfig", cursor: ProviderTaskCursor) -> bool:
        """mock 任务没有外部副作用，取消恒成功。"""

        _ = (config, cursor)
        return True
