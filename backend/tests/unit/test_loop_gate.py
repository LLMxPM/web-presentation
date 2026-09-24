"""文件功能：架构门禁——禁止新增无登记的亚秒级空转循环。"""

from __future__ import annotations

import ast
from pathlib import Path

# 已知亚秒轮询循环白名单（P3 将逐步收敛）；新循环必须登记并带空闲退避。
ALLOWED_SUBSECOND_LOOP_FILES = {
    "app/ai/external_task_queue.py",
    "app/ai/image_generation_queue.py",
    "app/ai/page_mutation_queue.py",
    "app/ai/component_mutation_queue.py",
    "app/services/rendering/coordinator.py",
    "app/services/page_screenshot_queue_worker.py",
    "app/services/mutation_job_service.py",
    "app/services/asset_render_hint_backfill_job_service.py",
    "app/services/runtime_artifact_store.py",
}


def test_no_unregistered_subsecond_busy_loops() -> None:
    """while True + asyncio.sleep(<1.0) 必须落在白名单文件中，新循环需显式登记。"""

    backend_root = Path(__file__).resolve().parents[2]
    violations: list[str] = []
    for path in backend_root.rglob("*.py"):
        rel = path.relative_to(backend_root).as_posix()
        if rel.startswith("tests/"):
            continue
        source = path.read_text(encoding="utf-8")
        if "while True" not in source or "asyncio.sleep" not in source:
            continue
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.While):
                continue
            if not _is_while_true(node):
                continue
            for child in ast.walk(node):
                if _is_asyncio_sleep_lt(child, 1.0):
                    if rel not in ALLOWED_SUBSECOND_LOOP_FILES:
                        violations.append(rel)
                    break
    assert violations == [], f"未登记的亚秒级循环：{violations}"


def _is_while_true(node: ast.While) -> bool:
    test = node.test
    return isinstance(test, ast.Constant) and test.value is True


def _is_asyncio_sleep_lt(node: ast.AST, limit: float) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    is_sleep = (
        isinstance(func, ast.Attribute)
        and func.attr == "sleep"
        and isinstance(func.value, ast.Name)
        and func.value.id == "asyncio"
    )
    if not is_sleep or not node.args:
        return False
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)):
        return float(arg.value) < limit
    # max(0.05, interval) 等动态下限：视为可能亚秒，若文件未登记则拦截
    return True
