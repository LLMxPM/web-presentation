"""文件功能：实现阿里云百炼图片异步任务提交、轮询、取消和结果下载。"""

from __future__ import annotations

import base64
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

_SIZE_MAP = {
    "standard": {"1:1": "1024*1024", "3:2": "1248*832", "2:3": "832*1248"},
    "high": {"1:1": "2048*2048", "3:2": "2496*1664", "2:3": "1664*2496"},
    "ultra": {"1:1": "4096*4096", "3:2": "4992*3328", "2:3": "3328*4992"},
}


class DashScopeImageGenerationAdapter:
    """通过百炼图片异步 API 执行图片生成与编辑。"""

    def __init__(self) -> None:
        self._cipher = LlmSecretCipher()

    def validate(self, config: AiLlmConfig, model: ImageModelSpec, request: ImageGenerationInput) -> None:
        """校验百炼图片生成请求。"""

        validate_model_request(model, request)
        self._validate_request(config, request)

    async def submit(
        self,
        config: AiLlmConfig,
        model: ImageModelSpec,
        request: ImageGenerationInput,
    ) -> ImageProviderResult:
        """根据模型配置提交百炼同步或异步任务。"""

        self.validate(config, model, request)
        base_url, headers = self._connection(config)
        content: list[dict[str, str]] = [{"text": request.prompt}]
        content.extend(
            {"image": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"}
            for _name, mime, data in request.references
        )
        parameters = {
            "size": _dashscope_size(request),
            "n": request.count,
            "watermark": bool(request.advanced_options.get("watermark", False)),
        }
        if "thinking_mode" in request.advanced_options:
            parameters["thinking_mode"] = bool(request.advanced_options["thinking_mode"])
        body = {
            "model": config.model_id,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }
        execution_mode = str(request.advanced_options.get("execution_mode") or "async")
        endpoint = "multimodal-generation" if execution_mode == "sync" else "image-generation"
        request_headers = headers if execution_mode == "sync" else {**headers, "X-DashScope-Async": "enable"}
        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                response = await client.post(
                    f"{base_url}/services/aigc/{endpoint}/generation",
                    headers=request_headers,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise AppException(
                status_code=503,
                code="AI_IMAGE_PROVIDER_SUBMISSION_UNKNOWN",
                detail="百炼图片任务提交超时，无法确认是否已创建任务。",
            ) from exc
        payload = _response_json(response)
        output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
        if execution_mode == "sync":
            urls = _extract_image_urls(output)
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                images = [await _download_image(client, url) for url in urls]
            return ImageProviderResult(status="completed", images=images)
        task_id = str(output.get("task_id") or "").strip()
        if not task_id:
            _raise_provider_error(response, payload)
        return ImageProviderResult(
            status="waiting",
            cursor=ProviderTaskCursor(
                task_id=task_id,
                status=str(output.get("task_status") or "PENDING"),
                request_id=str(payload.get("request_id") or "") or None,
                state={"execution_mode": "async"},
                next_poll_after_seconds=2,
                cancellable=True,
            ),
        )

    async def resume(
        self,
        config: AiLlmConfig,
        model: ImageModelSpec,
        cursor: ProviderTaskCursor,
    ) -> ImageProviderResult:
        """查询百炼任务；成功时立即下载所有图片。"""

        _ = model
        base_url, headers = self._connection(config)
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(f"{base_url}/tasks/{cursor.task_id}", headers=headers)
            payload = _response_json(response)
            output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
            status = str(output.get("task_status") or "UNKNOWN").upper()
            if status in {"PENDING", "RUNNING"}:
                return ImageProviderResult(
                    status="waiting",
                    cursor=ProviderTaskCursor(
                        task_id=cursor.task_id,
                        status=status,
                        request_id=str(payload.get("request_id") or "") or cursor.request_id,
                        state=cursor.state,
                        next_poll_after_seconds=min(15, max(2, float(cursor.next_poll_after_seconds or 2) * 2)),
                        cancellable=status in {"PENDING", "RUNNING"},
                    ),
                )
            if status != "SUCCEEDED":
                raise AppException(
                    status_code=502,
                    code=f"AI_IMAGE_PROVIDER_{status}",
                    detail=str(output.get("message") or payload.get("message") or "百炼图片任务未成功完成。"),
                )
            urls = _extract_image_urls(output)
            images = [await _download_image(client, url) for url in urls]
            return ImageProviderResult(
                status="completed",
                images=images,
                cursor=ProviderTaskCursor(
                    task_id=cursor.task_id,
                    status=status,
                    request_id=str(payload.get("request_id") or "") or cursor.request_id,
                    state=cursor.state,
                ),
            )

    async def cancel(self, config: AiLlmConfig, cursor: ProviderTaskCursor) -> bool:
        """按游标能力尝试取消仍在处理的百炼任务。"""

        if not cursor.cancellable:
            return False
        base_url, headers = self._connection(config)
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(f"{base_url}/tasks/{cursor.task_id}/cancel", headers=headers)
            return response.is_success
        except httpx.HTTPError:
            return False

    def _connection(self, config: AiLlmConfig) -> tuple[str, dict[str, str]]:
        """解析并校验百炼图片连接。"""

        provider = config.provider_config
        api_key = self._cipher.decrypt(provider.api_key_ciphertext)
        base_url = str(provider.base_url or "").strip().rstrip("/")
        if not api_key:
            raise AppException(status_code=409, code="AI_IMAGE_GENERATION_API_KEY_REQUIRED", detail="百炼图片供应商缺少 API Key。")
        if not base_url.startswith("https://"):
            raise AppException(status_code=409, code="AI_IMAGE_GENERATION_BASE_URL_REQUIRED", detail="百炼图片供应商 Base URL 无效。")
        return base_url, {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    @staticmethod
    def _validate_request(config: AiLlmConfig, request: ImageGenerationInput) -> None:
        """校验百炼图片生成请求。"""

        if request.mask is not None:
            raise AppException(status_code=422, code="AI_IMAGE_MASK_UNSUPPORTED", detail="百炼图片生成当前不支持蒙版编辑。")
        if request.quality != "auto":
            raise AppException(status_code=422, code="AI_IMAGE_QUALITY_UNSUPPORTED", detail="百炼图片生成不支持 quality 参数。")
        if request.operation == "edit" and not request.references:
            raise AppException(status_code=422, code="AI_IMAGE_EDIT_SOURCE_REQUIRED", detail="图片编辑至少需要一张参考图。")
        if len(request.references) > 4 or request.count not in range(1, 5):
            raise AppException(status_code=422, code="AI_IMAGE_COUNT_UNSUPPORTED", detail="百炼图片输入和输出数量必须在 1～4 范围内。")
        if request.resolution_tier == "ultra" and request.references:
            raise AppException(status_code=422, code="AI_IMAGE_RESOLUTION_UNSUPPORTED", detail="百炼 4K 仅支持无参考图生成。")


def _dashscope_size(request: ImageGenerationInput) -> str:
    """把公共画布参数映射为百炼尺寸。"""

    tier = "high" if request.resolution_tier == "auto" else request.resolution_tier
    if tier not in _SIZE_MAP:
        raise AppException(status_code=422, code="AI_IMAGE_RESOLUTION_UNSUPPORTED", detail="百炼图片供应商不支持当前分辨率。")
    ratio = "1:1" if request.aspect_ratio == "auto" else request.aspect_ratio
    size = _SIZE_MAP[tier].get(ratio)
    if size is None:
        raise AppException(status_code=422, code="AI_IMAGE_ASPECT_RATIO_UNSUPPORTED", detail="百炼图片供应商不支持当前宽高比。")
    return size


def _response_json(response: httpx.Response) -> dict[str, Any]:
    """安全读取供应商 JSON 响应。"""

    try:
        payload = response.json()
    except ValueError as exc:
        raise AppException(status_code=502, code="AI_IMAGE_PROVIDER_RESPONSE_INVALID", detail="百炼返回了无效响应。") from exc
    if not isinstance(payload, dict):
        raise AppException(status_code=502, code="AI_IMAGE_PROVIDER_RESPONSE_INVALID", detail="百炼返回了无效响应。")
    if not response.is_success:
        _raise_provider_error(response, payload)
    return payload


def _raise_provider_error(response: httpx.Response, payload: dict[str, Any]) -> None:
    """把百炼 HTTP 错误转换为稳定平台异常。"""

    code = str(payload.get("code") or "FAILED").upper().replace(".", "_")
    retryable = response.status_code == 429 or response.status_code >= 500
    raise AppException(
        status_code=503 if retryable else 422,
        code=f"AI_IMAGE_PROVIDER_{code}",
        detail=str(payload.get("message") or "百炼图片供应商调用失败。"),
        data={"retryable": retryable},
    )


def _extract_image_urls(output: dict[str, Any]) -> list[str]:
    """从 Wan choices 中提取临时图片 URL。"""

    urls: list[str] = []
    for choice in output.get("choices") or []:
        message = choice.get("message") if isinstance(choice, dict) else None
        for item in message.get("content", []) if isinstance(message, dict) else []:
            if isinstance(item, dict) and item.get("type") == "image":
                url = str(item.get("image") or "")
                if url:
                    urls.append(url)
    if not urls:
        raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_EMPTY", detail="百炼图片任务返回空结果。")
    return urls


async def _download_image(client: httpx.AsyncClient, url: str) -> GeneratedImage:
    """下载并校验百炼临时图片。"""

    if not url.startswith("https://"):
        raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_INVALID", detail="百炼返回了非 HTTPS 图片地址。")
    response = await client.get(url)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in {"image/png", "image/jpeg", "image/webp"} or not response.content:
        raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_INVALID", detail="百炼返回了无效图片文件。")
    if len(response.content) > 25 * 1024 * 1024:
        raise AppException(status_code=502, code="AI_IMAGE_GENERATION_RESULT_TOO_LARGE", detail="百炼返回图片过大。")
    return GeneratedImage(content=response.content, content_type=content_type)
