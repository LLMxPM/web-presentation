"""文件功能：验证模型运行预算仅由上下文窗口稳定派生。"""

from app.ai.model_budget import derive_model_run_budget


def test_model_budget_should_derive_balanced_defaults_for_128k_window() -> None:
    """128K 窗口应保留约 20% 输出，并使用 10% 压缩目标。"""

    budget = derive_model_run_budget(128_000)

    assert budget.max_output_tokens == 25_600
    assert budget.safety_margin_tokens == 10_240
    assert budget.context_input_budget_tokens == 92_160
    assert budget.compression_target_tokens == 12_800
    assert budget.compression_target_ratio == 0.1


def test_model_budget_should_cap_large_window_output_and_compression() -> None:
    """百万上下文不应让输出和摘要预算随窗口无限增长。"""

    budget = derive_model_run_budget(1_000_000)

    assert budget.max_output_tokens == 65_536
    assert budget.safety_margin_tokens == 80_000
    assert budget.context_input_budget_tokens == 854_464
    assert budget.compression_target_tokens == 32_768
    assert budget.compression_target_ratio == 0.032768


def test_model_budget_should_apply_provider_output_limit() -> None:
    """已知供应商硬上限应覆盖平台通用输出上限。"""

    budget = derive_model_run_budget(1_000_000, provider_output_limit=32_768)

    assert budget.max_output_tokens == 32_768
    assert budget.context_input_budget_tokens == 887_232
