"""文件功能：定义运行态存储的窄命令契约、错误类型与观测快照。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


# 已登记命令的单一事实源：两种后端都必须实现，业务不得使用未登记命令。
REGISTERED_RUNTIME_STATE_COMMANDS: frozenset[str] = frozenset(
    {
        "ping",
        "set",
        "get",
        "incr",
        "delete",
        "expire",
        "ttl",
        "hset",
        "hget",
        "hmget",
        "hgetall",
    }
)

# 封装辅助能力：不是 Redis 命令，但属于运行态 facade 的公开面。
RUNTIME_STATE_HELPER_COMMANDS: frozenset[str] = frozenset(
    {
        "batch",
        "purge_expired",
        "record_sweep_failure",
        "stats",
    }
)

# 明确封闭的 Redis 能力：未登记命令不得被业务静默使用（消息通知与 Stream 不在支持承诺内）。
FORBIDDEN_RUNTIME_STATE_COMMANDS: frozenset[str] = frozenset(
    {
        "publish",
        "pipeline",
        "xadd",
        "xread",
        "xrange",
        "scan_iter",
        "exists",
    }
)


class RuntimeStateUnavailableError(RuntimeError):
    """运行态存储当前不可用：连接失败、认证失败或超时。"""


class RuntimeStateTypeError(RuntimeError):
    """对已有 key 执行了与其类型不匹配的命令，语义对齐 Redis WRONGTYPE。"""


class RuntimeStateCapacityError(RuntimeError):
    """进程内运行态超过 payload 预算或单项上限，写入在生效前被拒绝。"""


@dataclass(slots=True)
class RuntimeStateStats:
    """运行态存储观测快照；字段为 None 表示该后端不提供该项。

    仅供日志、就绪端点与受控指标使用，不得输出 key 内容或连接串。
    """

    backend_kind: str
    ephemeral: bool
    active_keys: int | None = None
    approx_bytes: int | None = None
    max_bytes: int | None = None
    max_item_bytes: int | None = None
    capacity_rejections: int = 0
    sweep_count: int = 0
    sweep_failures: int = 0
    last_sweep_at: str | None = None
    last_sweep_seconds: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """转换为可直接写入日志或 JSON 响应的安全字典。"""

        return {
            "backend_kind": self.backend_kind,
            "ephemeral": self.ephemeral,
            "active_keys": self.active_keys,
            "approx_bytes": self.approx_bytes,
            "max_bytes": self.max_bytes,
            "max_item_bytes": self.max_item_bytes,
            "capacity_rejections": self.capacity_rejections,
            "sweep_count": self.sweep_count,
            "sweep_failures": self.sweep_failures,
            "last_sweep_at": self.last_sweep_at,
            "last_sweep_seconds": self.last_sweep_seconds,
        }


@runtime_checkable
class RuntimeStateBatch(Protocol):
    """受限批处理：只允许已登记命令，且整批对其它读者不可见。"""

    def set(self, key: str, value: Any, *, ex: int | None = None) -> "RuntimeStateBatch": ...

    def hset(self, key: str, mapping: Mapping[str, Any]) -> "RuntimeStateBatch": ...

    def expire(self, key: str, seconds: int) -> "RuntimeStateBatch": ...

    def delete(self, *keys: str) -> "RuntimeStateBatch": ...

    def execute(self) -> list[Any]: ...


@runtime_checkable
class RuntimeStateCommands(Protocol):
    """业务可见的运行态窄命令集。

    新增命令前必须先做设计评审，登记用途、拥有者、TTL、容量上限与重启后的动作；
    无法证明“丢失仍正确”的状态不得进入本接口，只能写主库。
    """

    kind: str
    ephemeral: bool
    max_bytes: int | None
    max_item_bytes: int | None

    def ping(self) -> None: ...

    def set(self, key: str, value: Any, *, ex: int | None = None, nx: bool = False) -> bool: ...

    def get(self, key: str) -> str | None: ...

    def incr(self, key: str) -> int: ...

    def delete(self, *keys: str) -> int: ...

    def expire(self, key: str, seconds: int) -> bool: ...

    def ttl(self, key: str) -> int: ...

    def hset(self, key: str, mapping: Mapping[str, Any]) -> int: ...

    def hget(self, key: str, field: str) -> str | None: ...

    def hmget(self, key: str, fields: Sequence[str]) -> list[str | None]: ...

    def hgetall(self, key: str) -> dict[str, str]: ...

    def batch(self) -> RuntimeStateBatch: ...

    def purge_expired(self) -> int: ...

    def record_sweep_failure(self) -> None: ...

    def stats(self) -> RuntimeStateStats: ...