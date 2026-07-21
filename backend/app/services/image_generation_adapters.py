"""文件功能：实现 OpenAI 图片协议，并兼容导出既有图片生成服务入口。"""

from __future__ import annotations

import base64
import binascii
from io import BytesIO
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.ai.secret_cipher import LlmSecretCipher
from app.core.exceptions import AppException
from app.models.ai_llm import AiLlmConfig
from app.services.image_generation.contracts import (
    GeneratedImage,
    ImageGenerationAdapter,
    ImageGenerationInput,
    ImageModelSpec,
    ImageProviderResult,
    ProviderTaskCursor,
    validate_advanced_options,
    validate_model_request,
)


class OpenAiImageGenerationAdapter:
    """通过 OpenAI Image API 同步执行图片生成或编辑。"""

    def __init__(self) -> None:
        self._cipher = LlmSecretCipher()

    def validate(self, config: AiLlmConfig, model: ImageModelSpec, request: ImageGenerationInput) -> None:
        """校验 OpenAI 图片请求的公共能力约束。"""

        _ = config
        validate_model_request(model, request)
        if "output_compression" in request.advanced_options and request.advanced_options.get("output_format", "png") == "png":
            raise AppException(
                status_code=422,
                code="AI_IMAGE_ADVANCED_CONFIG_INVALID",
                detail="OpenAI output_compression 仅适用于 jpeg 或 webp 输出。",
            )

    async def submit(
        self,
        config: AiLlmConfig,
        model: ImageModelSpec,
        request: ImageGenerationInput,
    ) -> ImageProviderResult:
        """调用 OpenAI，并立即把响应转换成可持久化图片字节。"""

        self.validate(config, model, request)
        provider = config.provider_config
        api_key = self._cipher.decrypt(provider.api_key_ciphertext)
        if not api_key:
            raise AppException(status_code=409, code="AI_IMAGE_GENERATION_API_KEY_REQUIRED", detail="OpenAI 图片供应商缺少 API Key。")
        client = AsyncOpenAI(api_key=api_key, base_url=str(provider.base_url or "").strip() or None)
        common = {
            "model": config.model_id,
            "prompt": request.prompt,
            "size": _openai_size(request.aspect_ratio),
            "quality": request.quality,
            "n": request.count,
            **request.advanced_options,
        }
        if request.operation == "generate":
            response = await client.images.generate(**common)
        else:
            images = [_named_file(name, content) for name, _mime, content in request.references]
            edit_input: dict[str, Any] = {"image": images, **common}
            # OpenAI edits 当前没有 moderation 参数；模型配置中的默认值只应用于 generations。
            edit_input.pop("moderation", None)
            if request.mask is not None:
                edit_input["mask"] = _named_file(request.mask[0], request.mask[2])
            response = await client.images.edit(**edit_input)
        output_format = str(request.advanced_options.get("output_format") or "png")
        return ImageProviderResult(
            status="completed",
            images=await _read_openai_images(response, default_content_type=_output_content_type(output_format)),
        )

    async def resume(
        self,
        config: AiLlmConfig,
        model: ImageModelSpec,
        cursor: ProviderTaskCursor,
    ) -> ImageProviderResult:
        """OpenAI 当前适配器不会产生异步任务。"""

        _ = (config, model, cursor)
        raise AppException(status_code=409, code="AI_IMAGE_PROVIDER_TASK_INVALID", detail="OpenAI 图片任务不支持轮询。")

    async def cancel(self, config: AiLlmConfig, cursor: ProviderTaskCursor) -> bool:
        """OpenAI 当前适配器没有可取消的外部任务。"""

        _ = (config, cursor)
        return False


def get_image_generation_adapter(config: AiLlmConfig) -> ImageGenerationAdapter:
    """兼容旧导入路径，并委托唯一图片供应商注册表。"""

    from app.services.image_generation.registry import get_image_generation_adapter as resolve_adapter

    return resolve_adapter(config)


def normalize_image_request(
    payload: dict[str, Any],
    *,
    references,
    mask,
    advanced_options: dict[str, Any] | None = None,
) -> ImageGenerationInput:
    """把当前 Tool 请求与历史 size 请求归一化为新画布协议。"""

    aspect_ratio = str(payload.get("aspect_ratio") or "").strip()
    resolution_tier = str(payload.get("resolution_tier") or "").strip()
    if not aspect_ratio and payload.get("size"):
        aspect_ratio = {
            "1024x1024": "1:1",
            "1536x1024": "3:2",
            "1024x1536": "2:3",
        }.get(str(payload["size"]), "auto")
        resolution_tier = "standard"
    return ImageGenerationInput(
        operation=str(payload.get("operation") or "generate"),
        prompt=str(payload.get("prompt") or ""),
        aspect_ratio=aspect_ratio or "auto",
        resolution_tier=resolution_tier or "auto",
        quality=str(payload.get("quality") or "auto"),
        count=int(payload.get("count") or 1),
        references=references,
        mask=mask,
        advanced_options=dict(advanced_options or {}),
    )


def validate_image_generation_request(config: AiLlmConfig, payload: dict[str, Any]) -> None:
    """在入队前按绑定供应商校验画布、操作和输入数量。"""

    references = [("reference.png", "image/png", b"") for _ in payload.get("reference_attachment_ids") or []]
    mask = ("mask.png", "image/png", b"") if payload.get("mask_attachment_id") is not None else None
    from app.services.image_generation.registry import get_image_model_spec

    provider_key = str(config.provider_config.provider_key or "").strip()
    model = get_image_model_spec(provider_key, config.model_id)
    options = validate_advanced_options(model, dict(config.advanced_config_json or {}))
    request = normalize_image_request(payload, references=references, mask=mask, advanced_options=options)
    get_image_generation_adapter(config).validate(config, model, request)


def _openai_size(aspect_ratio: str) -> str:
    """把语义宽高比转换为 OpenAI 的固定尺寸。"""

    return {"1:1": "1024x1024", "3:2": "1536x1024", "2:3": "1024x1536"}.get(aspect_ratio, "auto")


async def _read_openai_images(response: Any, *, default_content_type: str = "image/png") -> list[GeneratedImage]:
    """读取 OpenAI Base64 或临时 URL 输出，不向上泄露 URL。"""

    result: list[GeneratedImage] = []
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        for item in response.data:
            encoded = getattr(item, "b64_json", None)
            if encoded:
                try:
                    content = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError, TypeError) as exc:
                    raise AppException(
                        status_code=502,
                        code="AI_IMAGE_GENERATION_RESULT_INVALID",
                        detail="图片供应商返回了无效 Base64 图片。",
                    ) from exc
                _validate_image_bytes(content)
                result.append(GeneratedImage(content=content, content_type=default_content_type))
                continue
            url = str(getattr(item, "url", None) or "")
            if not url.startswith("https://"):
                raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_INVALID", detail="图片供应商未返回可保存的图片。")
            downloaded = await http.get(url)
            downloaded.raise_for_status()
            result.append(GeneratedImage(content=downloaded.content, content_type=_safe_content_type(downloaded)))
    if not result:
        raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_EMPTY", detail="图片供应商返回空结果。")
    return result


def _output_content_type(output_format: str) -> str:
    """把受控 OpenAI 输出格式映射为平台 MIME。"""

    return {"jpeg": "image/jpeg", "webp": "image/webp"}.get(output_format, "image/png")


def _safe_content_type(response: httpx.Response) -> str:
    """校验下载结果为受支持的图片类型。"""

    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_INVALID", detail="图片供应商返回了无效文件。")
    _validate_image_bytes(response.content)
    return content_type


def _validate_image_bytes(content: bytes) -> None:
    """确保供应商图片非空且没有超过单文件上限。"""

    if not content:
        raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_INVALID", detail="图片供应商返回了空文件。")
    if len(content) > 25 * 1024 * 1024:
        raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_TOO_LARGE", detail="图片供应商返回文件过大。")


def _named_file(name: str, content: bytes) -> BytesIO:
    """构造 OpenAI SDK multipart 上传可识别的具名内存文件。"""

    file = BytesIO(content)
    file.name = name  # type: ignore[attr-defined]
    return file
