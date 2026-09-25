"""文件功能：实现进程内运行态后端，提供 String/Hash 子集、TTL、原子批处理与 payload 预算。"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, NoReturn

from app.services.runtime_state.contracts import (
    RuntimeStateBatch,
    RuntimeStateCapacityError,
    RuntimeStateStats,
    RuntimeStateTypeError,
)


def _byte_size(text: str) -> int:
    """按 UTF-8 计算近似 payload 字节数，用于进程内配额统计。"""

    return len(text.encode("utf-8"))


class _InMemoryState:
    """单实例内存状态容器，所有读写都必须在后端锁内进行。"""

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.expires: dict[str, float] = {}
        self.bytes: int = 0


class InMemoryRuntimeStateBackend:
    """覆盖平台已登记命令的线程安全内存运行态后端。

    与真实 Redis 对齐的关键语义：类型冲突拒绝、`INCR` 保留原 TTL、
    `TTL` 的 -1/-2 约定、`HSET` 返回新增字段数、缺失 key 的幂等删除。
    超出 payload 预算或单项上限时在写入生效前抛出稳定容量错误。
    """

    kind = "memory"
    ephemeral = True

    def __init__(
        self,
        *,
        instance_name: str = "memory",
        max_bytes: int | None = None,
        max_item_bytes: int | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.instance_name = instance_name
        self.max_bytes = max_bytes if max_bytes and max_bytes > 0 else None
        self.max_item_bytes = max_item_bytes if max_item_bytes and max_item_bytes > 0 else None
        self._state = _InMemoryState()
        self._lock = threading.RLock()
        self._clock = clock or time.time
        self._capacity_rejections = 0
        self._sweep_count = 0
        self._sweep_failures = 0
        self._last_sweep_at: str | None = None
        self._last_sweep_seconds: float | None = None

    def ping(self) -> None:
        """进程内后端始终可用；保留命令以对齐连接检查。"""

        return None

    def set(self, key: str, value: Any, *, ex: int | None = None, nx: bool = False) -> bool:
        """写入字符串值；`nx` 已存在时返回 False，不覆盖原值。"""

        if ex is not None and ex <= 0:
            raise ValueError("运行态 set 的 ex 必须为正整数秒。")
        text = str(value)
        with self._lock:
            self._purge_key(key)
            if nx and self._exists(key):
                return False
            self._ensure_type_is_string(key)
            item_size = _byte_size(key) + _byte_size(text)
            self._ensure_item_size(item_size)
            previous = self._state.strings.get(key)
            delta = item_size - (_byte_size(key) + _byte_size(previous)) if previous is not None else item_size
            self._ensure_total_bytes(self._state.bytes + delta)
            self._state.strings[key] = text
            self._state.bytes += delta
            self._set_expire(key, ex)
            return True

    def get(self, key: str) -> str | None:
        """读取字符串值；key 不存在时返回 None。"""

        with self._lock:
            self._purge_key(key)
            self._ensure_type_is_string(key)
            return self._state.strings.get(key)

    def incr(self, key: str) -> int:
        """原子递增计数器并保留已有 TTL。"""

        with self._lock:
            self._purge_key(key)
            self._ensure_type_is_string(key)
            raw = self._state.strings.get(key, "0")
            try:
                current = int(raw) + 1
            except (TypeError, ValueError) as exc:
                raise ValueError(f"运行态 INCR 的目标值不是整数：{raw}") from exc
            text = str(current)
            previous_size = _byte_size(key) + _byte_size(raw) if key in self._state.strings else 0
            delta = _byte_size(key) + _byte_size(text) - previous_size
            self._ensure_total_bytes(self._state.bytes + delta)
            self._state.strings[key] = text
            self._state.bytes += delta
            return current

    def delete(self, *keys: str) -> int:
        """删除若干 key，返回实际删除数量。"""

        deleted = 0
        with self._lock:
            for key in keys:
                self._purge_key(key)
                if not self._exists(key):
                    continue
                self._drop_key(key)
                deleted += 1
        return deleted

    def expire(self, key: str, seconds: int) -> bool:
        """设置 key TTL；非正数按 Redis 语义立即删除。"""

        with self._lock:
            self._purge_key(key)
            if not self._exists(key):
                return False
            if seconds <= 0:
                self._drop_key(key)
                return True
            self._state.expires[key] = self._clock() + int(seconds)
            return True

    def ttl(self, key: str) -> int:
        """返回剩余秒数：-2 表示 key 不存在，-1 表示无 TTL。"""

        with self._lock:
            self._purge_key(key)
            if not self._exists(key):
                return -2
            expires_at = self._state.expires.get(key)
            if expires_at is None:
                return -1
            return max(0, int(expires_at - self._clock()))

    def hset(self, key: str, mapping: Mapping[str, Any]) -> int:
        """写入 Hash 字段，返回新增字段数量。"""

        with self._lock:
            self._purge_key(key)
            self._ensure_type_is_hash(key)
            updates = {str(field): str(value) for field, value in mapping.items()}
            delta = self._plan_hash_updates(key, updates)
            self._ensure_total_bytes(self._state.bytes + delta)
            return self._apply_hash_updates(key, updates)

    def hget(self, key: str, field: str) -> str | None:
        """读取 Hash 单字段。"""

        with self._lock:
            self._purge_key(key)
            self._ensure_type_is_hash(key)
            return self._state.hashes.get(key, {}).get(field)

    def hmget(self, key: str, fields: Sequence[str]) -> list[str | None]:
        """按输入顺序批量读取 Hash 字段，缺失字段以 None 占位。"""

        with self._lock:
            self._purge_key(key)
            self._ensure_type_is_hash(key)
            target = self._state.hashes.get(key, {})
            return [target.get(field) for field in fields]

    def hgetall(self, key: str) -> dict[str, str]:
        """读取完整 Hash；key 不存在时返回空字典。"""

        with self._lock:
            self._purge_key(key)
            self._ensure_type_is_hash(key)
            return dict(self._state.hashes.get(key, {}))

    def batch(self) -> RuntimeStateBatch:
        """创建受限批处理；整批在同一把锁内生效，对其它线程不可见。"""

        return _InMemoryRuntimeStateBatch(self)

    def purge_expired(self) -> int:
        """主动释放全部已过期 key；惰性过期仍由各读命令兜底。"""

        started_at = self._clock()
        started_monotonic = time.monotonic()
        with self._lock:
            expired_keys = [key for key, deadline in self._state.expires.items() if deadline <= started_at]
            for key in expired_keys:
                self._drop_key(key)
            self._sweep_count += 1
            self._last_sweep_at = _format_timestamp(started_at)
            self._last_sweep_seconds = round(time.monotonic() - started_monotonic, 6)
            return len(expired_keys)

    def record_sweep_failure(self) -> None:
        """登记一次清扫失败，供清扫循环按有界间隔重试时观测。"""

        with self._lock:
            self._sweep_failures += 1

    def stats(self) -> RuntimeStateStats:
        """返回进程内运行态的 key 数、近似字节与清扫统计。"""

        with self._lock:
            return RuntimeStateStats(
                backend_kind=self.kind,
                ephemeral=self.ephemeral,
                active_keys=len(self._state.strings) + len(self._state.hashes),
                approx_bytes=self._state.bytes,
                max_bytes=self.max_bytes,
                max_item_bytes=self.max_item_bytes,
                capacity_rejections=self._capacity_rejections,
                sweep_count=self._sweep_count,
                sweep_failures=self._sweep_failures,
                last_sweep_at=self._last_sweep_at,
                last_sweep_seconds=self._last_sweep_seconds,
            )

    def _execute_batch(self, commands: list[tuple[str, tuple[Any, ...], dict[str, Any]]]) -> list[Any]:
        """在同一把锁内执行整批命令；失败时回滚本批触碰的 key。"""

        with self._lock:
            touched: set[str] = set()
            for name, args, _ in commands:
                if name == "delete":
                    touched.update(args)
                elif args:
                    touched.add(str(args[0]))
            snapshot = {key: self._snapshot_key(key) for key in touched}
            try:
                results = [getattr(self, name)(*args, **kwargs) for name, args, kwargs in commands]
                self._ensure_total_bytes(self._state.bytes)
            except RuntimeStateCapacityError:
                self._restore_keys(snapshot)
                raise
            return results

    def _plan_hash_updates(self, key: str, updates: Mapping[str, str]) -> int:
        """校验各字段大小并计算 Hash 写入后的字节增量。"""

        target = self._state.hashes.get(key)
        base = 0 if target is not None else _byte_size(key)
        delta = base
        for field, value in updates.items():
            item_size = _byte_size(field) + _byte_size(value)
            self._ensure_item_size(item_size)
            previous = target.get(field) if target is not None else None
            delta += item_size if previous is None else item_size - (_byte_size(field) + _byte_size(previous))
        return delta

    def _apply_hash_updates(self, key: str, updates: Mapping[str, str]) -> int:
        """应用已校验的 Hash 写入并维护字节统计。"""

        target = self._state.hashes.get(key)
        if target is None:
            target = {}
            self._state.hashes[key] = target
            self._state.bytes += _byte_size(key)
        added = 0
        for field, value in updates.items():
            previous = target.get(field)
            if previous is None:
                added += 1
                self._state.bytes += _byte_size(field) + _byte_size(value)
            else:
                self._state.bytes += _byte_size(value) - _byte_size(previous)
            target[field] = value
        return added

    def _set_expire(self, key: str, seconds: int | None) -> None:
        """写入或清除 TTL。"""

        if seconds is None:
            self._state.expires.pop(key, None)
            return
        self._state.expires[key] = self._clock() + int(seconds)

    def _exists(self, key: str) -> bool:
        return key in self._state.strings or key in self._state.hashes

    def _purge_key(self, key: str) -> None:
        """惰性过期：命中已过期 key 时立即释放。"""

        deadline = self._state.expires.get(key)
        if deadline is None or deadline > self._clock():
            return
        self._drop_key(key)

    def _drop_key(self, key: str) -> None:
        """释放 key 并同步字节统计。"""

        self._state.bytes -= self._entry_size(key)
        self._state.strings.pop(key, None)
        self._state.hashes.pop(key, None)
        self._state.expires.pop(key, None)
        if self._state.bytes < 0:
            self._state.bytes = 0

    def _entry_size(self, key: str) -> int:
        """计算单个 key 当前占用的近似字节数。"""

        text = self._state.strings.get(key)
        if text is not None:
            return _byte_size(key) + _byte_size(text)
        fields = self._state.hashes.get(key)
        if fields is not None:
            return _byte_size(key) + sum(_byte_size(field) + _byte_size(value) for field, value in fields.items())
        return 0

    def _ensure_type_is_string(self, key: str) -> None:
        if key in self._state.hashes:
            raise RuntimeStateTypeError(f"运行态 key 保存的是 Hash，不能按字符串操作：{key}")

    def _ensure_type_is_hash(self, key: str) -> None:
        if key in self._state.strings:
            raise RuntimeStateTypeError(f"运行态 key 保存的是字符串，不能按 Hash 操作：{key}")

    def _ensure_item_size(self, item_size: int) -> None:
        """拒绝超过单项上限的 payload。"""

        if self.max_item_bytes is None or item_size <= self.max_item_bytes:
            return
        self._reject_capacity(
            f"运行态单项 payload 约 {item_size} 字节，超过上限 {self.max_item_bytes} 字节。"
        )

    def _ensure_total_bytes(self, projected_bytes: int) -> None:
        """拒绝会让进程内运行态突破总预算的写入。"""

        if self.max_bytes is None or projected_bytes <= self.max_bytes:
            return
        self._reject_capacity(
            f"运行态 payload 约 {projected_bytes} 字节，超过进程内预算 {self.max_bytes} 字节。"
        )

    def _reject_capacity(self, message: str) -> NoReturn:
        """登记容量拒绝并抛出稳定错误。"""

        self._capacity_rejections += 1
        raise RuntimeStateCapacityError(message)

    def _snapshot_key(self, key: str) -> tuple[str | None, dict[str, str] | None, float | None]:
        return (
            self._state.strings.get(key),
            dict(self._state.hashes[key]) if key in self._state.hashes else None,
            self._state.expires.get(key),
        )

    def _restore_keys(self, snapshot: Mapping[str, tuple[str | None, dict[str, str] | None, float | None]]) -> None:
        """把批处理触碰过的 key 还原到批次开始时的状态。"""

        for key, (text, fields, deadline) in snapshot.items():
            self._state.strings.pop(key, None)
            self._state.hashes.pop(key, None)
            self._state.expires.pop(key, None)
            if text is not None:
                self._state.strings[key] = text
            if fields is not None:
                self._state.hashes[key] = dict(fields)
            if deadline is not None:
                self._state.expires[key] = deadline
        self._state.bytes = sum(self._entry_size(key) for key in self._live_keys())

    def _live_keys(self) -> list[str]:
        return list(set(self._state.strings) | set(self._state.hashes))


class _InMemoryRuntimeStateBatch:
    """受限内存批处理：只登记已公开命令，由后端整批加锁执行。"""

    def __init__(self, backend: InMemoryRuntimeStateBackend) -> None:
        self._backend = backend
        self._commands: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def set(self, key: str, value: Any, *, ex: int | None = None) -> "_InMemoryRuntimeStateBatch":
        return self._enqueue("set", key, value, ex=ex)

    def hset(self, key: str, mapping: Mapping[str, Any]) -> "_InMemoryRuntimeStateBatch":
        return self._enqueue("hset", key, mapping=mapping)

    def expire(self, key: str, seconds: int) -> "_InMemoryRuntimeStateBatch":
        return self._enqueue("expire", key, seconds)

    def delete(self, *keys: str) -> "_InMemoryRuntimeStateBatch":
        return self._enqueue("delete", *keys)

    def execute(self) -> list[Any]:
        """整批执行并清空命令队列。"""

        commands = self._commands
        self._commands = []
        return self._backend._execute_batch(commands)

    def _enqueue(self, name: str, *args: Any, **kwargs: Any) -> "_InMemoryRuntimeStateBatch":
        self._commands.append((name, args, kwargs))
        return self


def _format_timestamp(epoch_seconds: float) -> str:
    """把时钟读数格式化为 UTC ISO 时间戳。"""

    from datetime import UTC, datetime

    return datetime.fromtimestamp(epoch_seconds, tz=UTC).isoformat()