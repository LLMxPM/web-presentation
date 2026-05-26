"""文件功能：验证浏览器错误日志上报接口与请求访问日志行为。"""

from __future__ import annotations

import logging

from httpx import AsyncClient


async def test_client_error_log_requires_authentication(client: AsyncClient) -> None:
    """浏览器错误日志上报必须具备登录态。"""

    response = await client.post(
        "/api/client-logs/errors",
        json={"source": "editor", "message": "boom"},
    )

    assert response.status_code == 401


async def test_client_error_log_should_write_sanitized_record(
    authenticated_client: AsyncClient,
    caplog,
) -> None:
    """客户端错误日志应写入已脱敏的结构化日志记录。"""

    caplog.set_level(logging.ERROR, logger="app.api.routes.client_logs")
    response = await authenticated_client.post(
        "/api/client-logs/errors",
        json={
            "source": "editor",
            "message": "boom?token=secret-token",
            "stack": "Error: boom\nAuthorization: Bearer abcdefghijklmnopqrstuvwxyz",
            "context": {"api_key": "hidden", "safe": "ok"},
        },
    )

    assert response.status_code == 202
    record = next(item for item in caplog.records if getattr(item, "event", "") == "client.error")
    assert getattr(record, "source") == "editor"
    assert getattr(record, "user_id") == 1
    assert "secret-token" not in str(record.__dict__)
    assert "abcdefghijklmnopqrstuvwxyz" not in str(record.__dict__)
    assert "hidden" not in str(record.__dict__)


async def test_request_middleware_should_return_request_id_and_log_path_without_query(
    authenticated_client: AsyncClient,
    caplog,
) -> None:
    """访问日志应包含 request_id、path、状态码和耗时，不包含 query。"""

    caplog.set_level(logging.INFO, logger="app.access")
    response = await authenticated_client.get(
        "/api/auth/me?token=should-not-log",
        headers={"X-Request-ID": "req-from-test"},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-from-test"
    record = next(item for item in caplog.records if getattr(item, "event", "") == "http.request.completed")
    assert getattr(record, "request_id") == "req-from-test"
    assert getattr(record, "path") == "/api/auth/me"
    assert getattr(record, "status_code") == 200
    assert isinstance(getattr(record, "duration_ms"), float)
    assert "should-not-log" not in str(record.__dict__)
