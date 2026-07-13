"""文件功能：验证 AI 页面变更队列的权限错误分类规则。"""

from __future__ import annotations

import pytest

from app.ai.page_mutation_queue import (
    _fatal_permission_error_code,
    _is_fatal_job_error,
    _is_permission_denied_error,
    _is_retryable_infrastructure_error,
)
from app.core.exceptions import AppException


@pytest.mark.parametrize(
    ("status_code", "code", "expected_code"),
    [
        (403, "WORKSPACE_ACCESS_DENIED", "WORKSPACE_ACCESS_DENIED"),
        (403, "PAGE_ACCESS_DENIED", "PAGE_ACCESS_DENIED"),
        (401, "TOKEN_INVALID", "AUTH_PERMISSION_DENIED:TOKEN_INVALID"),
        (403, "CUSTOM_POLICY_REJECTED", "AUTH_PERMISSION_DENIED:CUSTOM_POLICY_REJECTED"),
    ],
)
def test_permission_or_access_denied_should_be_fatal_for_page_mutation_batch(
    status_code: int,
    code: str,
    expected_code: str,
) -> None:
    """所有认证、授权及工作空间/页面访问拒绝都必须终止 Batch 自动续跑。"""

    error = AppException(status_code=status_code, code=code, detail="访问已被拒绝。")

    assert _is_permission_denied_error(error) is True
    assert _fatal_permission_error_code(error.code) == expected_code
    assert _is_fatal_job_error(_fatal_permission_error_code(error.code)) is True


@pytest.mark.parametrize("code", ["RUNTIME_VITE_QUEUE_FULL", "RUNTIME_VITE_QUEUE_TIMEOUT"])
def test_runtime_capacity_errors_should_retry_even_when_http_status_is_429(code: str) -> None:
    """Runtime 有界调度返回 429 时，AI Job 应按基础设施错误有限重试。"""

    error = AppException(status_code=429, code=code, detail="Runtime 正忙。")

    assert _is_retryable_infrastructure_error(error) is True
