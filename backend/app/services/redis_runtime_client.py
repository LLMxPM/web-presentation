"""文件功能：集中创建 Redis 运行态客户端，并提供测试可用的内存实现。"""

from __future__ import annotations

import json
import fnmatch
import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from redis import Redis
from redis.exceptions import AuthenticationError, ConnectionError, TimeoutError

from app.core.config import get_settings
from app.core.exceptions import AppException


class RedisRuntimeError(RuntimeError):
    """表示 Redis 运行态存储当前不可用。"""


@dataclass(slots=True)
class RedisRuntimeClient:
    """封装 Redis 客户端、key 前缀与 JSON 编解码能力。"""

    client: Any
    key_prefix: str

    def key(self, suffix: str) -> str:
        """拼接带仓库命名空间的 Redis key。"""

        return f"{self.key_prefix}:{str(suffix).strip(':')}"

    def dumps(self, value: Any) -> str:
        """把对象编码为 Redis 中保存的 JSON 字符串。"""

        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    def loads(self, value: Any, default: Any = None) -> Any:
        """从 Redis 字符串或字节内容解析 JSON，失败时返回默认值。"""

        if value is None:
            return default
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if not isinstance(value, str):
            return value
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default

    def ping(self) -> None:
        """执行 Redis 健康检查，失败时抛出统一运行态异常。"""

        try:
            self.client.ping()
        except Exception as exc:  # noqa: BLE001
            raise RedisRuntimeError(_format_redis_runtime_error(exc)) from exc


@lru_cache
def get_redis_runtime_client() -> RedisRuntimeClient:
    """读取配置并创建共享 Redis 运行态客户端。"""

    settings = get_settings()
    redis_url = settings.redis_url.strip()
    if redis_url.startswith("memory://"):
        client: Any = InMemoryRedis()
    else:
        client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=settings.redis_healthcheck_timeout_seconds,
            socket_connect_timeout=settings.redis_healthcheck_timeout_seconds,
        )
    return RedisRuntimeClient(client=client, key_prefix=settings.redis_key_prefix)


def reset_redis_runtime_client() -> None:
    """清理缓存的 Redis 客户端，供测试切换环境变量。"""

    get_redis_runtime_client.cache_clear()


def ensure_redis_runtime_available() -> None:
    """校验 Redis 运行态可用，失败时转换为启动期可读错误。"""

    try:
        get_redis_runtime_client().ping()
    except RedisRuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RedisRuntimeError(_format_redis_runtime_error(exc)) from exc


def raise_redis_unavailable() -> None:
    """将 Redis 不可用映射为对外业务错误。"""

    raise AppException(status_code=503, code="REDIS_RUNTIME_UNAVAILABLE", detail="Redis 运行态存储不可用。")


def _format_redis_runtime_error(error: Exception) -> str:
    """把 redis-py 底层异常转换为更容易排查的中文错误。"""

    if isinstance(error, AuthenticationError):
        return "Redis 运行态存储认证失败，请在 REDIS_URL 中配置密码，例如 redis://:密码@host:6379/1。"
    if isinstance(error, TimeoutError):
        return "Redis 运行态存储连接超时，请检查 REDIS_URL、网络连通性和 REDIS_HEALTHCHECK_TIMEOUT_SECONDS。"
    if isinstance(error, ConnectionError):
        return "Redis 运行态存储连接失败，请确认 Redis 服务已启动且 REDIS_URL 地址可访问。"
    return f"Redis 运行态存储不可用：{error}"


class InMemoryRedis:
    """覆盖测试所需 Redis 子集的线程安全内存实现。"""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._hashes: dict[str, dict[str, str]] = defaultdict(dict)
        self._streams: dict[str, list[tuple[str, dict[str, str]]]] = defaultdict(list)
        self._expires: dict[str, float] = {}
        self._stream_sequence = 0
        self._condition = threading.Condition()

    def ping(self) -> bool:
        """模拟 Redis ping。"""

        return True

    def set(self, name: str, value: Any, ex: int | None = None, nx: bool = False) -> bool | None:
        """保存字符串值，并支持 NX 与秒级 TTL。"""

        with self._condition:
            self._purge_expired(name)
            if nx and self.exists(name):
                return None
            self._values[name] = str(value)
            self._set_expire(name, ex)
            self._condition.notify_all()
            return True

    def get(self, name: str) -> str | None:
        """读取字符串值。"""

        with self._condition:
            self._purge_expired(name)
            return self._values.get(name)

    def delete(self, *names: str) -> int:
        """删除一个或多个 key。"""

        deleted = 0
        with self._condition:
            for name in names:
                existed = self.exists(name)
                self._values.pop(name, None)
                self._hashes.pop(name, None)
                self._streams.pop(name, None)
                self._expires.pop(name, None)
                deleted += 1 if existed else 0
            self._condition.notify_all()
        return deleted

    def exists(self, name: str) -> bool:
        """判断 key 是否存在。"""

        self._purge_expired(name)
        return name in self._values or name in self._hashes or name in self._streams

    def expire(self, name: str, time: int) -> bool:
        """设置 key TTL。"""

        with self._condition:
            if not self.exists(name):
                return False
            self._set_expire(name, time)
            return True

    def hset(self, name: str, key: str | None = None, value: Any | None = None, mapping: dict[str, Any] | None = None) -> int:
        """写入 Hash 字段。"""

        with self._condition:
            self._purge_expired(name)
            updates = dict(mapping or {})
            if key is not None:
                updates[str(key)] = value
            target = self._hashes[name]
            added = 0
            for field_name, field_value in updates.items():
                if field_name not in target:
                    added += 1
                target[str(field_name)] = str(field_value)
            self._condition.notify_all()
            return added

    def hget(self, name: str, key: str) -> str | None:
        """读取 Hash 单字段。"""

        with self._condition:
            self._purge_expired(name)
            return self._hashes.get(name, {}).get(key)

    def hgetall(self, name: str) -> dict[str, str]:
        """读取完整 Hash。"""

        with self._condition:
            self._purge_expired(name)
            return dict(self._hashes.get(name, {}))

    def xrange(self, name: str, min: str = "-", max: str = "+", count: int | None = None) -> list[tuple[str, dict[str, str]]]:
        """读取 Stream 条目。"""

        with self._condition:
            self._purge_expired(name)
            items = list(self._streams.get(name, []))
            if count is not None:
                items = items[:count]
            return items

    def xread(
        self,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        """阻塞读取 Stream 新条目，兼容 redis-py xread 子集。"""

        deadline = None if block is None else time.time() + max(0, block) / 1000
        with self._condition:
            while True:
                result: list[tuple[str, list[tuple[str, dict[str, str]]]]] = []
                for stream_name, last_id in streams.items():
                    self._purge_expired(stream_name)
                    items = [
                        item
                        for item in self._streams.get(stream_name, [])
                        if _compare_stream_ids(item[0], last_id) > 0
                    ]
                    if count is not None:
                        items = items[:count]
                    if items:
                        result.append((stream_name, items))
                if result:
                    return result
                if deadline is not None:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        return []
                    self._condition.wait(timeout=remaining)
                else:
                    self._condition.wait()


    def xadd(self, name: str, fields: dict[str, Any], maxlen: int | None = None, approximate: bool = True) -> str:
        """追加 Stream 条目。"""

        _ = approximate
        with self._condition:
            self._stream_sequence += 1
            entry_id = f"{int(time.time() * 1000)}-{self._stream_sequence}"
            self._streams[name].append((entry_id, {str(k): str(v) for k, v in fields.items()}))
            if maxlen is not None and maxlen > 0:
                self._streams[name] = self._streams[name][-maxlen:]
            self._condition.notify_all()
            return entry_id

    def scan_iter(self, match: str | None = None) -> Iterator[str]:
        """按 glob 模式扫描 key。"""

        with self._condition:
            keys = set(self._values) | set(self._hashes) | set(self._streams)
            for key in list(keys):
                self._purge_expired(key)
            keys = set(self._values) | set(self._hashes) | set(self._streams)
        for key in sorted(keys):
            if match is None or fnmatch.fnmatch(key, match):
                yield key

    def publish(self, channel: str, message: str) -> int:
        """模拟发布消息；测试内存实现不维护订阅者。"""

        _ = channel, message
        return 0

    def pipeline(self) -> "InMemoryPipeline":
        """创建简单 pipeline。"""

        return InMemoryPipeline(self)

    def _set_expire(self, name: str, seconds: int | None) -> None:
        if seconds is None:
            self._expires.pop(name, None)
            return
        self._expires[name] = time.time() + max(1, int(seconds))

    def _purge_expired(self, name: str) -> None:
        expires_at = self._expires.get(name)
        if expires_at is None or expires_at > time.time():
            return
        self._values.pop(name, None)
        self._hashes.pop(name, None)
        self._streams.pop(name, None)
        self._expires.pop(name, None)


class InMemoryPipeline:
    """顺序执行命令的内存 pipeline。"""

    def __init__(self, redis_client: InMemoryRedis) -> None:
        self._redis = redis_client
        self._commands: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def hset(self, *args: Any, **kwargs: Any) -> "InMemoryPipeline":
        self._commands.append(("hset", args, kwargs))
        return self

    def expire(self, *args: Any, **kwargs: Any) -> "InMemoryPipeline":
        self._commands.append(("expire", args, kwargs))
        return self

    def xadd(self, *args: Any, **kwargs: Any) -> "InMemoryPipeline":
        self._commands.append(("xadd", args, kwargs))
        return self

    def delete(self, *args: Any, **kwargs: Any) -> "InMemoryPipeline":
        self._commands.append(("delete", args, kwargs))
        return self

    def set(self, *args: Any, **kwargs: Any) -> "InMemoryPipeline":
        self._commands.append(("set", args, kwargs))
        return self

    def execute(self) -> list[Any]:
        """按记录顺序执行所有命令。"""

        results: list[Any] = []
        for name, args, kwargs in self._commands:
            results.append(getattr(self._redis, name)(*args, **kwargs))
        self._commands = []
        return results


def _compare_stream_ids(left: str, right: str) -> int:
    """比较 Redis Stream ID，支持 `$` 作为当前尾部哨兵。"""

    if right == "$":
        return -1

    def parse(value: str) -> tuple[int, int]:
        head, _, tail = str(value or "0-0").partition("-")
        try:
            return int(head), int(tail or 0)
        except ValueError:
            return 0, 0

    left_tuple = parse(left)
    right_tuple = parse(right)
    if left_tuple == right_tuple:
        return 0
    return 1 if left_tuple > right_tuple else -1
