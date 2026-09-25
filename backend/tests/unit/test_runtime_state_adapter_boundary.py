"""文件功能：门禁式检查业务代码只经窄接口访问运行态，且未登记命令不可被静默使用。"""

from __future__ import annotations

import ast
from pathlib import Path

from app.services.redis_runtime_client import (
    FORBIDDEN_RUNTIME_STATE_COMMANDS,
    REGISTERED_RUNTIME_STATE_COMMANDS,
    RUNTIME_STATE_HELPER_COMMANDS,
)
from app.services.runtime_state import InMemoryRuntimeStateBackend, RedisRuntimeStateBackend


BACKEND_APP_ROOT = Path(__file__).resolve().parents[2] / "app"
# 只有运行态适配层可以直接接触 redis-py 对象；其余业务代码必须走 facade。
RAW_REDIS_ALLOWED_FILES = {
    Path("services/redis_runtime_client.py"),
    Path("services/runtime_state/__init__.py"),
    Path("services/runtime_state/contracts.py"),
    Path("services/runtime_state/memory_backend.py"),
    Path("services/runtime_state/redis_backend.py"),
}
RAW_REDIS_MODULES = {"redis", "redis.client", "redis.exceptions", "redis.asyncio"}
RAW_REDIS_COMMAND_NAMES = REGISTERED_RUNTIME_STATE_COMMANDS | FORBIDDEN_RUNTIME_STATE_COMMANDS | {
    "from_url",
    "dumps",
    "loads",
    "purge_expired",
}


def _iter_business_files() -> list[Path]:
    """列出所有必须遵守窄接口约束的业务源码文件。"""

    files: list[Path] = []
    for path in BACKEND_APP_ROOT.rglob("*.py"):
        relative = path.relative_to(BACKEND_APP_ROOT)
        if relative.as_posix() in {item.as_posix() for item in RAW_REDIS_ALLOWED_FILES}:
            continue
        files.append(relative)
    return files


def _imported_modules(tree: ast.AST) -> set[str]:
    """收集模块内所有 import 的目标模块名。"""

    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _raw_client_calls(tree: ast.AST) -> list[str]:
    """收集形如 `<...>.client.<已登记命令>` 的原始客户端调用。"""

    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr not in RAW_REDIS_COMMAND_NAMES:
            continue
        try:
            base = ast.unparse(node.value)
        except Exception:  # noqa: BLE001
            continue
        if base.endswith(".client"):
            found.append(f"{base}.{node.attr}")
    return found


def test_business_code_should_not_touch_raw_redis_objects() -> None:
    """`backend/app` 除适配层外不得导入 redis，也不得访问原始客户端。"""

    violations: list[str] = []
    for relative in _iter_business_files():
        tree = ast.parse((BACKEND_APP_ROOT / relative).read_text(encoding="utf-8"))
        modules = _imported_modules(tree)
        if modules & RAW_REDIS_MODULES:
            violations.append(f"{relative}: 直接导入 {sorted(modules & RAW_REDIS_MODULES)}")
        leaks = _raw_client_calls(tree)
        if leaks:
            violations.append(f"{relative}: 原始运行态调用 {leaks}")
        if "InMemoryRuntimeStateBackend" in ast.unparse(tree):
            violations.append(f"{relative}: 业务代码直接引用内存后端实现")

    assert violations == [], "运行态访问必须经 redis_runtime_client facade：" + "；".join(violations)


def test_registered_commands_should_be_implemented_by_both_backends() -> None:
    """已登记命令必须被两种后端同时实现，新增命令会立刻暴露缺失实现。"""

    for backend in (InMemoryRuntimeStateBackend(instance_name="test"), RedisRuntimeStateBackend(client=object())):
        missing = [
            name
            for name in sorted(REGISTERED_RUNTIME_STATE_COMMANDS | RUNTIME_STATE_HELPER_COMMANDS)
            if not callable(getattr(backend, name, None))
        ]
        assert missing == [], f"{backend.kind} 后端缺少已登记命令实现：{missing}"


def test_unregistered_and_forbidden_commands_should_stay_closed() -> None:
    """未登记命令（消息通知、Stream、任意 pipeline）不得出现在后端与批处理面上。"""

    memory_backend = InMemoryRuntimeStateBackend(instance_name="test")
    for name in sorted(FORBIDDEN_RUNTIME_STATE_COMMANDS):
        assert not hasattr(memory_backend, name), f"内存后端不得实现未登记命令：{name}"
        assert not hasattr(memory_backend.batch(), name), f"批处理不得开放未登记命令：{name}"

    allowed_batch_commands = {"set", "hset", "expire", "delete", "execute"}
    batch_surface = {
        name
        for name in dir(memory_backend.batch())
        if not name.startswith("_") and callable(getattr(memory_backend.batch(), name))
    }
    assert batch_surface <= allowed_batch_commands, f"批处理暴露了未登记命令：{batch_surface - allowed_batch_commands}"