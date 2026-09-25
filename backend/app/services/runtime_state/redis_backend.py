"""文件功能：把真实 Redis 客户端适配为运行态窄命令后端，供 facade 统一调用。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from redis.exceptions import AuthenticationError, ConnectionError, ResponseError, RedisError, TimeoutError

from app.services.runtime_state.contracts import (
    RuntimeStateBatch,
    RuntimeStateStats,
    RuntimeStateTypeError,
    RuntimeStateUnavailableError,
)


class RedisRuntimeStateBackend:
    """真实 Redis 后端：只暴露已登记命令，其余能力不经由本适配器开放。"""

    kind = "redis"
    ephemeral = False
    max_bytes: int | None = None
    max_item_bytes: int | None = None

    def __init__(self, client: Any) -> None:
        self._client = client

    def ping(self) -> None:
        """执行 PING，失败时转成统一运行态不可用错误。"""

        try:
            self._client.ping()
        except RedisError as exc:
            raise RuntimeStateUnavailableError(_format_redis_error(exc)) from exc

    def set(self, key: str, value: Any, *, ex: int | None = None, nx: bool = False) -> bool:
        """写入字符串值；`nx` 已存在时返回 False。"""

        return bool(self._call("set", key, value, ex=ex, nx=nx))

    def get(self, key: str) -> str | None:
        """读取字符串值。"""

        return self._call("get", key)

    def incr(self, key: str) -> int:
        """原子递增计数器。"""

        return int(self._call("incr", key))

    def delete(self, *keys: str) -> int:
        """删除若干 key 并返回删除数量。"""

        if not keys:
            return 0
        return int(self._call("delete", *keys))

    def expire(self, key: str, seconds: int) -> bool:
        """设置 key TTL。"""

        return bool(self._call("expire", key, int(seconds)))

    def ttl(self, key: str) -> int:
        """返回剩余秒数，遵循 Redis 的 -1/-2 约定。"""

        return int(self._call("ttl", key))

    def hset(self, key: str, mapping: Mapping[str, Any]) -> int:
        """写入 Hash 字段并返回新增字段数量。"""

        if not mapping:
            return 0
        return int(self._call("hset", key, mapping=dict(mapping)))

    def hget(self, key: str, field: str) -> str | None:
        """读取 Hash 单字段。"""

        return self._call("hget", key, field)

    def hmget(self, key: str, fields: Sequence[str]) -> list[str | None]:
        """按输入顺序批量读取 Hash 字段。"""

        if not fields:
            return []
        values = self._call("hmget", key, list(fields))
        return [None if value is None else str(value) for value in values]

    def hgetall(self, key: str) -> dict[str, str]:
        """读取完整 Hash。"""

        raw = self._call("hgetall", key)
        return {str(field): str(value) for field, value in dict(raw or {}).items()}

    def batch(self) -> RuntimeStateBatch:
        """创建事务批处理；Redis 侧由 MULTI/EXEC 保证整批可见性。"""

        return _RedisRuntimeStateBatch(self)

    def purge_expired(self) -> int:
        """真实 Redis 自行管理 TTL，无需主动扫描。"""

        return 0

    def record_sweep_failure(self) -> None:
        """真实 Redis 不做进程内清扫，保留命令以对齐接口。"""

        return None

    def stats(self) -> RuntimeStateStats:
        """真实 Redis 由服务端管理容量，这里只报告后端类型。"""

        return RuntimeStateStats(backend_kind=self.kind, ephemeral=self.ephemeral)

    def _execute_batch(self, commands: list[tuple[str, tuple[Any, ...], dict[str, Any]]]) -> list[Any]:
        """以事务 pipeline 执行整批命令。"""

        pipe = self._client.pipeline(transaction=True)
        for name, args, kwargs in commands:
            if name == "hset" and not (kwargs.get("mapping") or args[1:2]):
                continue
            getattr(pipe, name)(*args, **kwargs)
        try:
            return list(pipe.execute())
        except RedisError as exc:
            raise _map_redis_error(exc) from exc

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """执行单个已登记命令，统一转换 Redis 异常。"""

        try:
            return getattr(self._client, name)(*args, **kwargs)
        except RedisError as exc:
            raise _map_redis_error(exc) from exc


class _RedisRuntimeStateBatch:
    """受限事务批处理：只登记已公开命令，由 MULTI/EXEC 一次提交。"""

    def __init__(self, backend: RedisRuntimeStateBackend) -> None:
        self._backend = backend
        self._commands: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def set(self, key: str, value: Any, *, ex: int | None = None) -> "_RedisRuntimeStateBatch":
        return self._enqueue("set", key, value, ex=ex)

    def hset(self, key: str, mapping: Mapping[str, Any]) -> "_RedisRuntimeStateBatch":
        return self._enqueue("hset", key, mapping=dict(mapping))

    def expire(self, key: str, seconds: int) -> "_RedisRuntimeStateBatch":
        return self._enqueue("expire", key, int(seconds))

    def delete(self, *keys: str) -> "_RedisRuntimeStateBatch":
        return self._enqueue("delete", *keys)

    def execute(self) -> list[Any]:
        """提交整批命令并清空队列。"""

        commands = self._commands
        self._commands = []
        return self._backend._execute_batch(commands)

    def _enqueue(self, name: str, *args: Any, **kwargs: Any) -> "_RedisRuntimeStateBatch":
        self._commands.append((name, args, kwargs))
        return self


def _map_redis_error(error: RedisError) -> RuntimeStateUnavailableError | RuntimeStateTypeError:
    """区分类型冲突与连接类故障，避免把业务错误误报为不可用。"""

    if isinstance(error, ResponseError) and "WRONGTYPE" in str(error):
        return RuntimeStateTypeError("运行态 key 类型与命令不匹配。")
    return RuntimeStateUnavailableError(_format_redis_error(error))


def _format_redis_error(error: Exception) -> str:
    """把 redis-py 异常转换为不含连接串与口令的排查提示。"""

    if isinstance(error, AuthenticationError):
        return "运行态存储认证失败，请检查 REDIS_URL 中的密码配置。"
    if isinstance(error, TimeoutError):
        return "运行态存储连接超时，请检查 REDIS_URL、网络连通性和 REDIS_HEALTHCHECK_TIMEOUT_SECONDS。"
    if isinstance(error, ConnectionError):
        return "运行态存储连接失败，请确认 Redis 服务已启动且 REDIS_URL 可访问。"
    return f"运行态存储不可用：{_redact_credentials(str(error)) or type(error).__name__}"


def _redact_credentials(text: str) -> str:
    """移除错误文本里可能出现的连接串凭证片段。"""

    return re.sub(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/@]*@", "", text).strip()