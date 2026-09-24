"""文件功能：验证校验结果单一判定谓词与跨阶段写入门槛语义。"""

from __future__ import annotations

import ast
from pathlib import Path

from app.services.validation_result import (
    is_render_unavailable,
    is_validation_passed,
    resolve_write_gate,
)


def test_is_validation_passed_should_reject_render_unavailable() -> None:
    """页面默认 require_render=True 时，render unavailable 不得视为通过。"""

    result = {
        "success": False,
        "status": "unavailable",
        "retryable": True,
        "stages": {"compile": "passed", "render": "unavailable"},
    }
    assert is_validation_passed(result, require_render=True) is False
    assert is_validation_passed(result, require_render=False) is True
    assert is_render_unavailable(result) is True


def test_is_validation_passed_should_allow_content_warning() -> None:
    """内容级 warning 保持通过，不得被 unavailable 语义误伤。"""

    result = {
        "success": True,
        "status": "passed",
        "stages": {"compile": "passed", "render": "warning"},
    }
    assert is_validation_passed(result, require_render=True) is True
    assert is_render_unavailable(result) is False


def test_is_validation_passed_should_allow_skipped_render() -> None:
    """render=skipped（未执行渲染）时按编译结果判定。"""

    result = {
        "success": True,
        "status": "passed",
        "stages": {"compile": "passed", "render": "skipped"},
    }
    assert is_validation_passed(result, require_render=True) is True


def test_resolve_write_gate_skip_visual_verification_leaves_audit_flag() -> None:
    """skip_visual_verification 仅放行渲染不可用，且必须返回审计标记。"""

    unavailable = {
        "success": False,
        "status": "unavailable",
        "retryable": True,
        "stages": {"compile": "passed", "render": "unavailable"},
    }
    assert resolve_write_gate(unavailable) == (False, False)
    assert resolve_write_gate(unavailable, skip_visual_verification=True) == (True, True)

    failed = {
        "success": False,
        "status": "failed",
        "stages": {"compile": "failed", "render": "skipped"},
    }
    assert resolve_write_gate(failed, skip_visual_verification=True) == (False, False)


def test_validation_predicate_definition_is_single() -> None:
    """防漂移：全仓只允许 validation_result.is_validation_passed 一处定义。"""

    backend_root = Path(__file__).resolve().parents[2]
    private_defs = 0
    public_defs = 0
    for path in backend_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if node.name == "_is_validation_passed":
                    private_defs += 1
                elif node.name == "is_validation_passed":
                    public_defs += 1
    assert private_defs == 0
    assert public_defs == 1
