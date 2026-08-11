"""文件功能：集中计算聊天模型的固定输入、输出预留与历史压缩预算。"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

CONTEXT_WINDOW_TOKEN_DEFAULT = 128_000
CONTEXT_WINDOW_TOKEN_MIN = 128_000
CONTEXT_WINDOW_TOKEN_MAX = 2_000_000
BUDGET_POLICY_VERSION = "fixed-context-budget.v2"
REQUEST_OUTPUT_TOKENS = 32_768
RUNTIME_HEADROOM_TOKENS = 32_768
COMPRESSION_TARGET_TOKENS = 16_384

# 仅供没有 budget_policy_version 的历史 Run 恢复旧预算，不再用于新配置。
LEGACY_OUTPUT_TOKEN_RATIO = 0.2
LEGACY_OUTPUT_TOKEN_MIN = 8_192
LEGACY_OUTPUT_TOKEN_MAX = 65_536
LEGACY_COMPRESSION_TARGET_RATIO = 0.1
LEGACY_COMPRESSION_TARGET_TOKEN_MIN = 4_096
LEGACY_COMPRESSION_TARGET_TOKEN_MAX = 32_768
LEGACY_SAFETY_MARGIN_RATIO = 0.08
TOKEN_ROUNDING_UNIT = 1_024


@dataclass(frozen=True, slots=True)
class ModelRunBudget:
    """描述一次运行使用的绝对 token 预算及其策略版本。"""

    budget_policy_version: str
    context_window_tokens: int
    max_output_tokens: int
    required_model_context_tokens: int
    runtime_headroom_tokens: int
    compression_trigger_tokens: int
    compression_target_tokens: int
    context_input_budget_tokens: int
    # 以下两个字段仅用于兼容旧 API，新的运行逻辑不读取它们。
    compression_target_ratio: float
    safety_margin_tokens: int


def derive_model_run_budget(context_window_tokens: int, *, provider_output_limit: int | None = None) -> ModelRunBudget:
    """按固定策略计算新 Run 预算，并应用模型或供应商输出硬上限。"""

    usable_input = max(1, int(context_window_tokens))
    output_tokens = REQUEST_OUTPUT_TOKENS
    if provider_output_limit is not None:
        output_tokens = min(output_tokens, max(1, int(provider_output_limit)))
    headroom = min(RUNTIME_HEADROOM_TOKENS, usable_input)
    trigger = max(0, usable_input - headroom)
    compression_target = min(COMPRESSION_TARGET_TOKENS, usable_input)
    return ModelRunBudget(
        budget_policy_version=BUDGET_POLICY_VERSION,
        context_window_tokens=usable_input,
        max_output_tokens=output_tokens,
        required_model_context_tokens=usable_input + output_tokens,
        runtime_headroom_tokens=headroom,
        compression_trigger_tokens=trigger,
        compression_target_tokens=compression_target,
        context_input_budget_tokens=usable_input,
        compression_target_ratio=compression_target / usable_input,
        safety_margin_tokens=headroom,
    )


def derive_legacy_model_run_budget(context_window_tokens: int, *, provider_output_limit: int | None = None) -> ModelRunBudget:
    """恢复未携带预算策略版本的历史 Run，保持旧比例算法不变。"""

    window = max(1, int(context_window_tokens))
    output_tokens = _floor_to_unit(window * LEGACY_OUTPUT_TOKEN_RATIO)
    output_tokens = min(max(output_tokens, LEGACY_OUTPUT_TOKEN_MIN), LEGACY_OUTPUT_TOKEN_MAX)
    if provider_output_limit is not None:
        output_tokens = min(output_tokens, max(1, int(provider_output_limit)))
    safety_margin = ceil(window * LEGACY_SAFETY_MARGIN_RATIO)
    input_budget = max(0, window - output_tokens - safety_margin)
    compression_target = floor(window * LEGACY_COMPRESSION_TARGET_RATIO)
    compression_target = min(
        max(compression_target, LEGACY_COMPRESSION_TARGET_TOKEN_MIN),
        LEGACY_COMPRESSION_TARGET_TOKEN_MAX,
        input_budget,
    )
    return ModelRunBudget(
        budget_policy_version="legacy-ratio-budget.v1",
        context_window_tokens=window,
        max_output_tokens=output_tokens,
        required_model_context_tokens=window,
        runtime_headroom_tokens=safety_margin,
        compression_trigger_tokens=input_budget,
        compression_target_tokens=compression_target,
        context_input_budget_tokens=input_budget,
        compression_target_ratio=compression_target / window if window else 0.0,
        safety_margin_tokens=safety_margin,
    )


def _floor_to_unit(value: float) -> int:
    """将 token 数向下对齐到 1K 二进制边界，保证旧预算稳定。"""

    return floor(value / TOKEN_ROUNDING_UNIT) * TOKEN_ROUNDING_UNIT
