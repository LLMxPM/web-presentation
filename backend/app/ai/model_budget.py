"""文件功能：集中计算聊天模型的上下文、输出预留与历史压缩预算。"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

CONTEXT_WINDOW_TOKEN_DEFAULT = 128_000
CONTEXT_WINDOW_TOKEN_MIN = 128_000
CONTEXT_WINDOW_TOKEN_MAX = 2_000_000
OUTPUT_TOKEN_RATIO = 0.2
OUTPUT_TOKEN_MIN = 8_192
OUTPUT_TOKEN_MAX = 65_536
COMPRESSION_TARGET_RATIO = 0.1
COMPRESSION_TARGET_TOKEN_MIN = 4_096
COMPRESSION_TARGET_TOKEN_MAX = 32_768
SAFETY_MARGIN_RATIO = 0.08
TOKEN_ROUNDING_UNIT = 1_024


@dataclass(frozen=True, slots=True)
class ModelRunBudget:
    """描述由上下文窗口自动派生的模型运行预算。"""

    context_window_tokens: int
    max_output_tokens: int
    compression_target_ratio: float
    compression_target_tokens: int
    safety_margin_tokens: int
    context_input_budget_tokens: int


def derive_model_run_budget(context_window_tokens: int, *, provider_output_limit: int | None = None) -> ModelRunBudget:
    """根据上下文窗口计算稳定的默认预算，并应用可选供应商输出硬上限。"""

    window = max(1, int(context_window_tokens))
    output_tokens = _floor_to_unit(window * OUTPUT_TOKEN_RATIO)
    output_tokens = min(max(output_tokens, OUTPUT_TOKEN_MIN), OUTPUT_TOKEN_MAX)
    if provider_output_limit is not None:
        output_tokens = min(output_tokens, max(1, int(provider_output_limit)))

    safety_margin_tokens = ceil(window * SAFETY_MARGIN_RATIO)
    context_input_budget_tokens = max(0, window - output_tokens - safety_margin_tokens)
    compression_target_tokens = floor(window * COMPRESSION_TARGET_RATIO)
    compression_target_tokens = min(
        max(compression_target_tokens, COMPRESSION_TARGET_TOKEN_MIN),
        COMPRESSION_TARGET_TOKEN_MAX,
        context_input_budget_tokens,
    )
    effective_compression_ratio = compression_target_tokens / window if window > 0 else 0.0
    return ModelRunBudget(
        context_window_tokens=window,
        max_output_tokens=output_tokens,
        compression_target_ratio=effective_compression_ratio,
        compression_target_tokens=compression_target_tokens,
        safety_margin_tokens=safety_margin_tokens,
        context_input_budget_tokens=context_input_budget_tokens,
    )


def _floor_to_unit(value: float) -> int:
    """将 token 数向下对齐到 1K 二进制边界，保证派生值稳定可读。"""

    return floor(value / TOKEN_ROUNDING_UNIT) * TOKEN_ROUNDING_UNIT
