"""文件功能：覆盖 AI 流式输出、事件标准化与会话互斥相关测试。"""

from tests.integration.ai.ai_agents_streaming_cases_1 import (
    test_ai_agent_run_events_should_be_normalized_for_editor,
    test_ai_stream_delta_should_preserve_markdown_boundaries,
    test_ai_stream_should_mark_cancelled_and_close_upstream_when_client_interrupts,
    test_ai_reasoning_stream_delta_should_preserve_newline_boundaries,
    test_ai_raw_sse_cancelled_event_should_trigger_preservation,
    test_ai_raw_sse_string_stream_should_trigger_cancelled_preservation,
    test_ai_raw_sse_object_events_should_continue_existing_event_index,
    test_ai_run_routes_should_stream_direct_page_apply,
    test_extract_tool_error_info_should_keep_structured_code,
)

from tests.integration.ai.ai_agents_streaming_cases_2 import (
    test_ai_active_run_cancel_route_should_proxy_interrupt_request,
    test_ai_run_stream_should_refresh_context_status_at_message_checkpoints,
    test_extract_tool_error_info_should_parse_repair_metadata_from_json_string,
)
