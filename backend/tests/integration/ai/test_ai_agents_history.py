"""文件功能：覆盖 AI 历史保留、上下文压缩与继续执行历史注入测试。"""

from tests.integration.ai.ai_agents_cases import (
    test_ai_continue_stream_should_not_reinject_current_run_history,
    test_ai_cancelled_runtime_snapshot_should_restore_tool_details,
    test_ai_error_should_not_preserve_streamed_delta_in_agno_history,
    test_ai_history_policy_should_expand_budget_with_history_ratio,
    test_ai_history_policy_should_scale_with_model_context_window,
    test_ai_history_policy_should_trigger_compression_by_token_budget,
    test_ai_new_run_should_inject_cancelled_history_to_model_context,
    test_ai_user_cancel_should_preserve_full_user_input_and_reasoning,
    test_ai_user_cancel_should_preserve_streamed_delta_in_agno_history,
)
