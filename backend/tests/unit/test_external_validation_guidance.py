"""文件功能：保证内部与外部校验共用事实，同时隔离恢复入口及重试语义。"""

import pytest

from app.ai.validation_result_formatter import build_validation_text


@pytest.mark.parametrize("resource", ["page", "component"])
@pytest.mark.parametrize("status", ["failed", "passed_with_warnings", "unavailable"])
def test_external_guidance_preserves_candidate_without_internal_tool(resource, status):
    """警告和失败均保留候选模式，外部不出现平台工具名。"""
    result = {"status": status, "diagnostics": [{"severity": "warning", "code": "TEST", "message": "问题定位"}]}
    external = build_validation_text(result, resource_type=resource, audience="external")
    internal = build_validation_text(result, resource_type=resource)
    assert "validate_entity" not in external
    assert "validate_entity" in internal
    assert "content/edits" in external and "尚无目标 ID" in external
    assert "有界重试" not in external
    assert "[TEST]" in internal and "[TEST]" in external


def test_retry_is_only_suggested_for_retryable_unavailable():
    """只有明确可重试的执行不可用允许提示重试。"""
    result = {"status": "unavailable", "retryable": True}
    assert "有界重试" in build_validation_text(result, resource_type="page", audience="external")
