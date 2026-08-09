"""文件功能：通过 OpenRouter 独立 Image API 同步生成或编辑图片。"""

from __future__ import annotations

import base64
import binascii
from typing import Any

import httpx

from app.ai.secret_cipher import LlmSecretCipher
from app.core.exceptions import AppException
from app.models.ai_llm import AiLlmConfig
from app.services.image_generation.contracts import (
    GeneratedImage,
    ImageGenerationInput,
    ImageModelSpec,
    ImageProviderResult,
    ProviderTaskCursor,
    validate_model_request,
)

_RESOLUTION_MAP = {"standard": "1K", "high": "2K", "ultra": "4K"}
_SUPPORTED_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp"}


class OpenRouterImageGenerationAdapter:
    """调用 OpenRouter `/images`，并把 Base64 结果转换为平台图片对象。"""

    def __init__(self) -> None:
        self._cipher = LlmSecretCipher()

    def validate(self, config: AiLlmConfig, model: ImageModelSpec, request: ImageGenerationInput) -> None:
        """按模型白名单校验公共参数和 OpenRouter 特有约束。"""

        _ = config
        validate_model_request(model, request)
        if request.mask is not None:
            raise AppException(status_code=422, code="AI_IMAGE_MASK_UNSUPPORTED", detail="OpenRouter 图片接口不支持蒙版编辑。")

    async def submit(
        self,
        config: AiLlmConfig,
        model: ImageModelSpec,
        request: ImageGenerationInput,
    ) -> ImageProviderResult:
        """提交同步生成请求，并返回可直接持久化的图片字节。"""

        self.validate(config, model, request)
        base_url, headers = self._connection(config)
        body = self._request_body(config, request)
        try:
            async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
                response = await client.post(f"{base_url}/images", headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise AppException(
                status_code=503,
                code="AI_IMAGE_PROVIDER_SUBMISSION_UNKNOWN",
                detail="OpenRouter 图片请求超时，无法确认生成结果。",
            ) from exc
        payload = _response_json(response)
        return ImageProviderResult(status="completed", images=_read_images(payload))

    async def resume(
        self,
        config: AiLlmConfig,
        model: ImageModelSpec,
        cursor: ProviderTaskCursor,
    ) -> ImageProviderResult:
        """OpenRouter 当前非流式接入不会产生可轮询任务。"""

        _ = (config, model, cursor)
        raise AppException(status_code=409, code="AI_IMAGE_PROVIDER_TASK_INVALID", detail="OpenRouter 图片任务不支持轮询。")

    async def cancel(self, config: AiLlmConfig, cursor: ProviderTaskCursor) -> bool:
        """OpenRouter 当前非流式接入没有外部取消入口。"""

        _ = (config, cursor)
        return False

    def _connection(self, config: AiLlmConfig) -> tuple[str, dict[str, str]]:
        """解密凭证并构造 OpenRouter Image API 连接信息。"""

        provider = config.provider_config
        api_key = self._cipher.decrypt(provider.api_key_ciphertext)
        base_url = str(provider.base_url or "").strip().rstrip("/") or "https://openrouter.ai/api/v1"
        if not api_key:
            raise AppException(status_code=409, code="AI_IMAGE_GENERATION_API_KEY_REQUIRED", detail="OpenRouter 图片供应商缺少 API Key。")
        if not base_url.startswith("https://"):
            raise AppException(status_code=409, code="AI_IMAGE_GENERATION_BASE_URL_REQUIRED", detail="OpenRouter 图片供应商 Base URL 无效。")
        return base_url, {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    @staticmethod
    def _request_body(config: AiLlmConfig, request: ImageGenerationInput) -> dict[str, Any]:
        """把平台语义参数转换为 OpenRouter Image API JSON。"""

        body: dict[str, Any] = {"model": config.model_id, "prompt": request.prompt, "n": request.count}
        if request.aspect_ratio != "auto":
            body["aspect_ratio"] = request.aspect_ratio
        if request.resolution_tier != "auto":
            body["resolution"] = _RESOLUTION_MAP[request.resolution_tier]
        if request.quality != "auto":
            body["quality"] = request.quality
        if request.references:
            body["input_references"] = [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"},
                }
                for _name, mime, content in request.references
            ]
        body.update(request.advanced_options)
        return body


def _response_json(response: httpx.Response) -> dict[str, Any]:
    """解析 OpenRouter JSON，并把 HTTP 错误映射为稳定平台异常。"""

    try:
        payload = response.json()
    except ValueError as exc:
        raise AppException(status_code=502, code="AI_IMAGE_PROVIDER_RESPONSE_INVALID", detail="OpenRouter 返回了无效响应。") from exc
    if not isinstance(payload, dict):
        raise AppException(status_code=502, code="AI_IMAGE_PROVIDER_RESPONSE_INVALID", detail="OpenRouter 返回了无效响应。")
    if response.is_success:
        return payload
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    provider_code = str(error.get("code") or response.status_code).upper().replace(".", "_")
    retryable = response.status_code == 429 or response.status_code >= 500
    raise AppException(
        status_code=503 if retryable else 422,
        code=f"AI_IMAGE_PROVIDER_{provider_code}",
        detail=str(error.get("message") or "OpenRouter 图片供应商调用失败。"),
        data={"retryable": retryable},
    )


def _read_images(payload: dict[str, Any]) -> list[GeneratedImage]:
    """解码响应图片，并拒绝平台资源库暂不支持的媒体类型。"""

    result: list[GeneratedImage] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        media_type = str(item.get("media_type") or "image/png").lower()
        if media_type not in _SUPPORTED_MEDIA_TYPES:
            raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_INVALID", detail="OpenRouter 返回了不受支持的图片格式。")
        try:
            content = base64.b64decode(item.get("b64_json"), validate=True)
        except (binascii.Error, ValueError, TypeError) as exc:
            raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_INVALID", detail="OpenRouter 返回了无效 Base64 图片。") from exc
        if not content:
            raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_INVALID", detail="OpenRouter 返回了空图片。")
        if len(content) > 25 * 1024 * 1024:
            raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_TOO_LARGE", detail="OpenRouter 返回图片过大。")
        result.append(GeneratedImage(content=content, content_type=media_type))
    if not result:
        raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_EMPTY", detail="OpenRouter 图片任务返回空结果。")
    return result
