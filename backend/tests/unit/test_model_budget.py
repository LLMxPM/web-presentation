"""文件功能：验证固定上下文预算和历史 Run 比例预算兼容。"""

from app.ai.model_budget import derive_legacy_model_run_budget, derive_model_run_budget


def test_fixed_budget_should_derive_expected_values_for_128k_input() -> None:
    """128K 可用输入应直接作为压缩触发线，并使用固定 32K 输出和 16K 摘要。"""

    budget = derive_model_run_budget(128_000)

    assert budget.budget_policy_version == "fixed-context-budget.v3"
    assert budget.max_output_tokens == 32_768
    assert budget.required_model_context_tokens == 160_768
    assert budget.runtime_headroom_tokens == 0
    assert budget.compression_trigger_tokens == 128_000
    assert budget.context_input_budget_tokens == 128_000
    assert budget.compression_target_tokens == 16_384


def test_fixed_budget_should_derive_expected_values_for_200k_input() -> None:
    """未知模型默认 200K 输入应明确要求 232,768 总上下文。"""

    budget = derive_model_run_budget(200_000)

    assert budget.required_model_context_tokens == 232_768
    assert budget.compression_trigger_tokens == 200_000
    assert budget.compression_target_tokens == 16_384


def test_fixed_budget_should_apply_model_output_limit() -> None:
    """模型硬上限低于 32K 时应降低实际输出及最低总上下文。"""

    budget = derive_model_run_budget(200_000, provider_output_limit=8_192)

    assert budget.max_output_tokens == 8_192
    assert budget.required_model_context_tokens == 208_192
    assert budget.compression_trigger_tokens == 200_000


def test_legacy_budget_should_keep_ratio_algorithm_for_old_runs() -> None:
    """没有策略版本的历史 Run 仍使用旧比例预算。"""

    budget = derive_legacy_model_run_budget(128_000)

    assert budget.budget_policy_version == "legacy-ratio-budget.v1"
    assert budget.max_output_tokens == 25_600
    assert budget.context_input_budget_tokens == 92_160
    assert budget.compression_target_tokens == 12_800
