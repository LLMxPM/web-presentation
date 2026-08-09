"""文件功能：维护 OpenRouter 图片模型白名单及其稳定能力声明。"""

from __future__ import annotations

from app.services.image_generation.contracts import ImageModelSpec

_AUTO_QUALITY = ("auto",)
_ALL_QUALITY = ("auto", "low", "medium", "high")

_RATIOS_QWEN = ("auto", "1:1", "1:2", "1:4", "2:1", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "9:16", "16:9")
_RATIOS_GEMINI_WIDE = ("auto", "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9")
_RATIOS_GEMINI_25 = ("auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")
_RATIOS_OPENAI = ("auto", "1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16", "21:9")
_RATIOS_SEEDREAM = (
    "auto", "1:1", "1:2", "2:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9",
    "9:19.5", "19.5:9", "9:20", "20:9", "9:21", "21:9",
)
_RATIOS_GROK = ("auto", "1:1", "1:2", "2:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "9:19.5", "19.5:9", "9:20", "20:9")

_SEED_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"seed": {"type": "integer", "minimum": 0, "maximum": 2147483647}},
}
_OPENAI_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "background": {"type": "string", "enum": ["auto", "opaque"]},
        "output_compression": {"type": "integer", "minimum": 0, "maximum": 100},
    },
}


def _model(
    model_id: str,
    label: str,
    *,
    ratios: tuple[str, ...],
    resolutions: tuple[str, ...],
    max_references: int,
    max_outputs: int,
    quality: tuple[str, ...] = _AUTO_QUALITY,
    advanced_schema: dict | None = None,
    advanced_defaults: dict | None = None,
) -> ImageModelSpec:
    """构造一个只开放 OpenRouter 目录已声明能力的图片模型。"""

    return ImageModelSpec(
        model_id=model_id,
        label=label,
        operations=("generate", "edit"),
        aspect_ratios=ratios,
        resolution_tiers=resolutions,
        quality_options=quality,
        max_reference_images=max_references,
        max_output_count=max_outputs,
        supports_mask=False,
        advanced_schema=advanced_schema or {},
        advanced_defaults=advanced_defaults or {},
    )


def build_openrouter_image_models() -> tuple[ImageModelSpec, ...]:
    """返回平台明确支持的 OpenRouter 图片模型及当前能力快照。"""

    return (
        _model(
            "google/gemini-3.1-flash-lite-image",
            "Google Gemini 3.1 Flash Lite Image",
            ratios=_RATIOS_GEMINI_WIDE,
            resolutions=("auto", "standard"),
            max_references=14,
            max_outputs=1,
        ),
        _model(
            "google/gemini-2.5-flash-image",
            "Google Gemini 2.5 Flash Image",
            ratios=_RATIOS_GEMINI_25,
            resolutions=("auto",),
            max_references=3,
            max_outputs=1,
        ),
        _model(
            "qwen/qwen-image-3",
            "Qwen Image 3",
            ratios=_RATIOS_QWEN,
            resolutions=("auto", "standard", "high"),
            max_references=4,
            max_outputs=6,
            advanced_schema=_SEED_SCHEMA,
        ),
        _model(
            "qwen/qwen-image-3-pro",
            "Qwen Image 3 Pro",
            ratios=_RATIOS_QWEN,
            resolutions=("auto", "standard", "high"),
            max_references=4,
            max_outputs=6,
            advanced_schema=_SEED_SCHEMA,
        ),
        _model(
            "openai/gpt-image-2",
            "OpenAI GPT Image 2",
            ratios=_RATIOS_OPENAI,
            resolutions=("auto",),
            max_references=16,
            max_outputs=10,
            quality=_ALL_QUALITY,
            advanced_schema=_OPENAI_SCHEMA,
            advanced_defaults={"background": "auto"},
        ),
        _model(
            "openai/gpt-5.4-image-2",
            "OpenAI GPT-5.4 Image 2",
            ratios=("auto",),
            resolutions=("auto",),
            max_references=16,
            max_outputs=10,
            quality=_ALL_QUALITY,
            advanced_schema=_OPENAI_SCHEMA,
            advanced_defaults={"background": "auto"},
        ),
        _model(
            "bytedance-seed/seedream-4.5",
            "ByteDance Seedream 4.5",
            ratios=_RATIOS_SEEDREAM,
            resolutions=("auto", "standard", "high", "ultra"),
            max_references=14,
            max_outputs=10,
            advanced_schema=_SEED_SCHEMA,
        ),
        _model(
            "x-ai/grok-imagine-image-quality",
            "xAI Grok Imagine Image Quality",
            ratios=_RATIOS_GROK,
            resolutions=("auto", "standard", "high"),
            max_references=3,
            max_outputs=1,
        ),
    )
