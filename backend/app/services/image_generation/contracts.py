"""文件功能：定义图片生成公共请求、模型能力、可恢复任务游标和适配器协议。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TYPE_CHECKING

from app.core.exceptions import AppException

if TYPE_CHECKING:
    from app.models.ai_llm import AiLlmConfig


@dataclass(slots=True)
class ImageGenerationInput:
    """承载供应商无关的图片生成或编辑输入和已校验模型参数。"""

    operation: str
    prompt: str
    aspect_ratio: str
    resolution_tier: str
    quality: str
    count: int
    references: list[tuple[str, str, bytes]]
    mask: tuple[str, str, bytes] | None = None
    advanced_options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ImageModelSpec:
    """描述单个生图模型的稳定能力和供应商参数白名单。"""

    model_id: str
    label: str
    operations: tuple[str, ...]
    aspect_ratios: tuple[str, ...]
    resolution_tiers: tuple[str, ...]
    quality_options: tuple[str, ...]
    max_reference_images: int
    max_output_count: int
    supports_mask: bool
    advanced_schema: dict[str, Any] = field(default_factory=dict)
    advanced_defaults: dict[str, Any] = field(default_factory=dict)
    allow_custom_model_id: bool = False

    def as_catalog_item(self) -> dict[str, Any]:
        """转换成前端目录可消费的纯 JSON 能力描述。"""

        return {
            "model_id": self.model_id,
            "label": self.label,
            "operations": list(self.operations),
            "aspect_ratios": list(self.aspect_ratios),
            "resolution_tiers": list(self.resolution_tiers),
            "quality_options": list(self.quality_options),
            "max_reference_images": self.max_reference_images,
            "max_output_count": self.max_output_count,
            "supports_mask": self.supports_mask,
            "advanced_schema": self.advanced_schema,
            "advanced_defaults": self.advanced_defaults,
            "allow_custom_model_id": self.allow_custom_model_id,
        }


@dataclass(slots=True)
class GeneratedImage:
    """保存供应商返回的单张图片字节和可信 MIME。"""

    content: bytes
    content_type: str = "image/png"


@dataclass(slots=True)
class ProviderTaskCursor:
    """持久化恢复异步供应商任务所需的最小游标。"""

    task_id: str
    status: str | None = None
    request_id: str | None = None
    state: dict[str, Any] = field(default_factory=dict)
    next_poll_after_seconds: float | None = None
    cancellable: bool = False


@dataclass(slots=True)
class ImageProviderResult:
    """统一表示同步完成或等待外部供应商的执行结果。"""

    status: Literal["completed", "waiting"]
    images: list[GeneratedImage] = field(default_factory=list)
    cursor: ProviderTaskCursor | None = None

    @property
    def provider_task_id(self) -> str | None:
        """兼容读取游标中的供应商任务 ID。"""

        return self.cursor.task_id if self.cursor is not None else None

    @property
    def provider_status(self) -> str | None:
        """兼容读取游标中的供应商状态。"""

        return self.cursor.status if self.cursor is not None else None

    @property
    def provider_request_id(self) -> str | None:
        """兼容读取游标中的供应商请求 ID。"""

        return self.cursor.request_id if self.cursor is not None else None


class ImageGenerationAdapter(Protocol):
    """约束供应商提交、恢复和取消生命周期，不区分同步或异步实现。"""

    def validate(self, config: AiLlmConfig, model: ImageModelSpec, request: ImageGenerationInput) -> None: ...

    async def submit(
        self,
        config: AiLlmConfig,
        model: ImageModelSpec,
        request: ImageGenerationInput,
    ) -> ImageProviderResult: ...

    async def resume(
        self,
        config: AiLlmConfig,
        model: ImageModelSpec,
        cursor: ProviderTaskCursor,
    ) -> ImageProviderResult: ...

    async def cancel(self, config: AiLlmConfig, cursor: ProviderTaskCursor) -> bool: ...


def validate_model_request(model: ImageModelSpec, request: ImageGenerationInput) -> None:
    """按模型能力统一校验公共参数，避免每个适配器重复维护边界。"""

    if request.operation not in model.operations:
        _raise_unsupported_parameter(
            model,
            field="operation",
            received=request.operation,
            allowed=model.operations,
            code="AI_IMAGE_OPERATION_UNSUPPORTED",
            detail="当前图片模型不支持该操作。",
        )
    if request.aspect_ratio not in model.aspect_ratios:
        _raise_unsupported_parameter(
            model,
            field="aspect_ratio",
            received=request.aspect_ratio,
            allowed=model.aspect_ratios,
            code="AI_IMAGE_ASPECT_RATIO_UNSUPPORTED",
            detail="当前图片模型不支持该宽高比。",
        )
    if request.resolution_tier not in model.resolution_tiers:
        _raise_unsupported_parameter(
            model,
            field="resolution_tier",
            received=request.resolution_tier,
            allowed=model.resolution_tiers,
            code="AI_IMAGE_RESOLUTION_UNSUPPORTED",
            detail="当前图片模型不支持该分辨率。",
        )
    if request.quality not in model.quality_options:
        _raise_unsupported_parameter(
            model,
            field="quality",
            received=request.quality,
            allowed=model.quality_options,
            code="AI_IMAGE_QUALITY_UNSUPPORTED",
            detail="当前图片模型不支持该质量参数。",
        )
    if len(request.references) > model.max_reference_images:
        raise AppException(status_code=422, code="AI_IMAGE_REFERENCE_COUNT_UNSUPPORTED", detail="参考图片数量超过当前模型限制。")
    if request.count < 1 or request.count > model.max_output_count:
        raise AppException(status_code=422, code="AI_IMAGE_COUNT_UNSUPPORTED", detail="输出图片数量超过当前模型限制。")
    if request.operation == "edit" and not request.references:
        raise AppException(status_code=422, code="AI_IMAGE_EDIT_SOURCE_REQUIRED", detail="图片编辑至少需要一张参考图。")
    if request.mask is not None and not model.supports_mask:
        raise AppException(status_code=422, code="AI_IMAGE_MASK_UNSUPPORTED", detail="当前图片模型不支持蒙版编辑。")


def _raise_unsupported_parameter(
    model: ImageModelSpec,
    *,
    field: str,
    received: str,
    allowed: tuple[str, ...],
    code: str,
    detail: str,
) -> None:
    """返回模型可直接修正的字段级错误信息，同时保留统一业务错误码。"""

    data: dict[str, Any] = {
        "field": field,
        "received": received,
        "allowed_values": list(allowed),
        "model_id": model.model_id,
    }
    if "auto" in allowed:
        data["retry_patch"] = {field: "auto"}
    raise AppException(status_code=422, code=code, detail=detail, data=data)


def validate_advanced_options(model: ImageModelSpec, value: dict[str, Any]) -> dict[str, Any]:
    """依据模型公开 Schema 校验高级参数并合并安全默认值。"""

    if not isinstance(value, dict):
        raise AppException(status_code=422, code="AI_IMAGE_ADVANCED_CONFIG_INVALID", detail="生图高级参数必须是 JSON 对象。")
    properties = model.advanced_schema.get("properties", {})
    unknown = sorted(set(value) - set(properties))
    if unknown:
        raise AppException(
            status_code=422,
            code="AI_IMAGE_ADVANCED_CONFIG_UNSUPPORTED",
            detail=f"当前图片模型不支持高级参数：{', '.join(unknown)}。",
        )
    result = {**model.advanced_defaults, **value}
    for key, item in result.items():
        rule = properties.get(key, {})
        expected = rule.get("type")
        if expected == "boolean" and not isinstance(item, bool):
            _raise_advanced_type(key)
        if expected == "integer" and (not isinstance(item, int) or isinstance(item, bool)):
            _raise_advanced_type(key)
        if expected == "string" and not isinstance(item, str):
            _raise_advanced_type(key)
        if "enum" in rule and item not in rule["enum"]:
            raise AppException(status_code=422, code="AI_IMAGE_ADVANCED_CONFIG_INVALID", detail=f"高级参数 {key} 取值无效。")
        if isinstance(item, int) and (item < rule.get("minimum", item) or item > rule.get("maximum", item)):
            raise AppException(status_code=422, code="AI_IMAGE_ADVANCED_CONFIG_INVALID", detail=f"高级参数 {key} 超出允许范围。")
    return result


def _raise_advanced_type(key: str) -> None:
    """抛出统一的高级参数类型错误。"""

    raise AppException(status_code=422, code="AI_IMAGE_ADVANCED_CONFIG_INVALID", detail=f"高级参数 {key} 类型无效。")
