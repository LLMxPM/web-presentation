"""文件功能：验证 Mutation 响应日志的读取上限与正文排除边界。"""

from unittest.mock import patch

from app.api.external_request_logging import (
    MAX_JOB_RESPONSE_BYTES,
    bind_external_operation,
    bind_mutation_response,
    log_external_result,
)
from fastapi import Request
from fastapi.responses import JSONResponse, Response


def test_large_job_response_does_not_parse_domain_result():
    """超限 Job 响应可包含大领域结果；日志层必须在 JSON 解析前跳过，不放大内存和耗时。"""
    request = Request({"type": "http"})
    response = Response(b"x" * (MAX_JOB_RESPONSE_BYTES + 1))
    with patch(
        "app.api.external_request_logging.json.loads",
        side_effect=AssertionError("不能解析大正文"),
    ):
        bind_mutation_response(request, response)
    assert not hasattr(request.state, "external_log_fields")


def test_job_log_ignores_result_errors_and_signed_urls():
    """正常大小响应只提取授权 Job/空间；源码、领域错误与带签名链接不会进入日志状态。"""
    request = Request({"type": "http"})
    response = JSONResponse(
        {
            "job_id": "job-public",
            "workspace_id": 7,
            "result": {
                "source_code": "source-secret",
                "url": "https://preview.test/?ctx=signed-secret",
            },
            "error": {"message": "error-secret"},
        }
    )
    bind_mutation_response(request, response)
    assert request.state.external_log_fields == {
        "job_id": "job-public",
        "workspace_id": 7,
    }


def test_context_space_is_distinct_and_log_fields_are_allowlisted(caplog):
    """Header 上下文与实际 Job 空间可以不同；其它代码写入 state 的正文不能穿透日志白名单。"""
    import json
    import logging

    from app.core.logging_config import JsonLineFormatter

    caplog.set_level(logging.INFO)
    request = Request({"type": "http", "method": "POST"})
    bind_external_operation(request, "page.create", workspace_context_id=2)
    bind_mutation_response(
        request, JSONResponse({"job_id": "job-public", "workspace_id": 7})
    )
    request.state.external_log_fields["source_code"] = "state-secret"
    log_external_result(
        request, route="/pages", operation="page.create", status_code=202, duration_ms=1
    )
    record = next(
        row
        for row in caplog.records
        if getattr(row, "event", None) == "external.request.completed"
    )
    payload = json.loads(JsonLineFormatter(service="backend").format(record))
    assert payload["workspace_context_id"] == 2 and payload["workspace_id"] == 7
    assert "source_code" not in payload and "state-secret" not in json.dumps(payload)
