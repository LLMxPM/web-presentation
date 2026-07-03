"""文件功能：验证智能体运行异常归一化，避免向用户暴露底层模型连接错误。"""

from app.ai.run_errors import build_agent_error_log_extra, normalize_agent_run_exception


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


def test_normalize_agent_run_exception_should_map_payment_required() -> None:
    """供应商 402 错误应提示检查余额或额度。"""

    failure = normalize_agent_run_exception(
        RuntimeError("Error code: 402 - {'error': {'message': 'Payment Required'}}"),
        fallback_code="AI_RUN_FAILED",
    )

    assert failure.code == "AI_MODEL_PAYMENT_REQUIRED"
    assert "余额或额度不足" in failure.message
    assert "Payment Required" in failure.raw_message


def test_build_agent_error_log_extra_should_include_error_chain() -> None:
    """错误日志字段应包含原始异常类型、消息和 cause 链路。"""

    try:
        try:
            raise ValueError("provider rejected request")
        except ValueError as cause:
            raise RuntimeError("member runner failed") from cause
    except RuntimeError as exc:
        extra = build_agent_error_log_extra(
            exc,
            event="ai.member_run.exception",
            error_code="AI_MEMBER_RUN_FAILED",
            user_error_message="智能体运行中断",
            member_run_id="member-run-test",
        )

    assert extra["event"] == "ai.member_run.exception"
    assert extra["member_run_id"] == "member-run-test"
    assert extra["error_code"] == "AI_MEMBER_RUN_FAILED"
    assert extra["raw_error_type"] == "RuntimeError"
    assert extra["raw_error_message"] == "member runner failed"
    assert extra["raw_error_chain"] == [
        {"type": "RuntimeError", "module": "builtins", "message": "member runner failed"},
        {"type": "ValueError", "module": "builtins", "message": "provider rejected request"},
    ]
