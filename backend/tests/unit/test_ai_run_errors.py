"""文件功能：验证智能体运行异常归一化，避免向用户暴露底层模型连接错误。"""

from app.ai.run_errors import normalize_agent_run_exception


def test_normalize_agent_run_exception_should_hide_chunked_read_detail() -> None:
    """chunked read 中断应转成模型连接中断提示。"""

    failure = normalize_agent_run_exception(
        RuntimeError("peer closed connection without sending complete message body (incomplete chunked read)"),
        fallback_code="AI_RUN_FAILED",
    )

    assert failure.code == "AI_MODEL_STREAM_INTERRUPTED"
    assert "模型连接中断" in failure.message
    assert "incomplete chunked read" not in failure.message
    assert "incomplete chunked read" in failure.raw_message


def test_normalize_agent_run_exception_should_map_invalid_request() -> None:
    """供应商 400 错误应提示检查模型配置。"""

    failure = normalize_agent_run_exception(
        RuntimeError("status_code: 400, body: {'code': 'invalid_request_error'}"),
        fallback_code="AI_RUN_FAILED",
    )

    assert failure.code == "AI_MODEL_REQUEST_REJECTED"
    assert "模型服务拒绝" in failure.message
