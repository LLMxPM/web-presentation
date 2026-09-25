"""文件功能：提供运行态存储 facade、后端工厂与部署组合校验。

业务只经由 `get_redis_runtime_client()` 返回的 facade 访问短生命周期运行态；
`memory://` 与 `redis://` / `rediss://` 在 §已登记命令范围内提供一致可观察结果。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from redis import Redis
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.sqlite_single_process import read_explicit_worker_count
from app.services.runtime_state import (
    FORBIDDEN_RUNTIME_STATE_COMMANDS,
    REGISTERED_RUNTIME_STATE_COMMANDS,
    RUNTIME_STATE_HELPER_COMMANDS,
    InMemoryRuntimeStateBackend,
    RedisRuntimeStateBackend,
    RuntimeStateBatch,
    RuntimeStateCapacityError,
    RuntimeStateCommands,
    RuntimeStateStats,
    RuntimeStateTypeError,
    RuntimeStateUnavailableError,
)

logger = logging.getLogger(__name__)

MEMORY_RUNTIME_STATE_SCHEME = "memory"
REDIS_RUNTIME_STATE_SCHEMES = ("redis", "rediss")
SUPPORTED_RUNTIME_STATE_SCHEMES = (MEMORY_RUNTIME_STATE_SCHEME, *REDIS_RUNTIME_STATE_SCHEMES)


class RuntimeStateConfigurationError(RuntimeError):
    """运行态存储 URL 或部署组合不受支持，启动必须直接失败。"""


@dataclass(slots=True)
class RedisRuntimeClient:
    """运行态存储 facade：暴露有类型的窄命令与 JSON 编解码辅助能力。"""

    backend: RuntimeStateCommands
    key_prefix: str

    @property
    def backend_kind(self) -> str:
        """返回后端类型标识（memory / redis），供日志与就绪元数据使用。"""

        return self.backend.kind

    @property
    def ephemeral(self) -> bool:
        """返回运行态是否随进程重启丢失。"""

        return self.backend.ephemeral

    def key(self, suffix: str) -> str:
        """拼接带仓库命名空间的运行态 key。"""

        return f"{self.key_prefix}:{str(suffix).strip(':')}"

    def dumps(self, value: Any) -> str:
        """把对象编码为运行态中保存的 JSON 字符串。"""

        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    def loads(self, value: Any, default: Any = None) -> Any:
        """从运行态字符串或字节内容解析 JSON，失败时返回默认值。"""

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
        """执行后端健康检查，失败时抛出统一运行态异常。"""

        self.backend.ping()

    def set(self, key: str, value: Any, *, ex: int | None = None, nx: bool = False) -> bool:
        """写入字符串值；`nx` 已存在时返回 False。"""

        return self.backend.set(key, value, ex=ex, nx=nx)

    def get(self, key: str) -> str | None:
        """读取字符串值。"""

        return self.backend.get(key)

    def incr(self, key: str) -> int:
        """原子递增计数器并保留已有 TTL。"""

        return self.backend.incr(key)

    def delete(self, *keys: str) -> int:
        """删除若干 key 并返回删除数量。"""

        return self.backend.delete(*keys)

    def expire(self, key: str, seconds: int) -> bool:
        """设置 key TTL。"""

        return self.backend.expire(key, seconds)

    def ttl(self, key: str) -> int:
        """返回剩余秒数：-2 表示 key 不存在，-1 表示无 TTL。"""

        return self.backend.ttl(key)

    def hset(self, key: str, mapping: Mapping[str, Any]) -> int:
        """写入 Hash 字段并返回新增字段数量。"""

        return self.backend.hset(key, mapping)

    def hget(self, key: str, field: str) -> str | None:
        """读取 Hash 单字段。"""

        return self.backend.hget(key, field)

    def hmget(self, key: str, fields: Sequence[str]) -> list[str | None]:
        """按输入顺序批量读取 Hash 字段。"""

        return self.backend.hmget(key, fields)

    def hgetall(self, key: str) -> dict[str, str]:
        """读取完整 Hash。"""

        return self.backend.hgetall(key)

    def batch(self) -> RuntimeStateBatch:
        """创建受限批处理；整批对其它读者不可见。"""

        return self.backend.batch()

    def sweep_expired(self) -> int:
        """主动清扫进程内过期 key；真实 Redis 由服务端 TTL 负责。"""

        return self.backend.purge_expired()

    def record_sweep_failure(self) -> None:
        """登记一次清扫失败，供清扫循环观测与重试。"""

        self.backend.record_sweep_failure()

    def stats(self) -> RuntimeStateStats:
        """返回运行态观测快照。"""

        return self.backend.stats()


def create_runtime_state_client(
    *,
    redis_url: str | None = None,
    key_prefix: str | None = None,
) -> RedisRuntimeClient:
    """按显式配置创建运行态客户端；测试与对拍用它注入独立实例与前缀。"""

    settings = get_settings()
    resolved_url = (redis_url if redis_url is not None else settings.redis_url).strip()
    resolved_prefix = (key_prefix if key_prefix is not None else settings.redis_key_prefix).strip().strip(":")
    scheme, instance_name = parse_runtime_state_url(resolved_url)
    if scheme == MEMORY_RUNTIME_STATE_SCHEME:
        backend: RuntimeStateCommands = InMemoryRuntimeStateBackend(
            instance_name=instance_name,
            max_bytes=settings.runtime_state_memory_max_bytes,
            max_item_bytes=settings.runtime_state_memory_max_item_bytes,
        )
    else:
        backend = RedisRuntimeStateBackend(
            Redis.from_url(
                resolved_url,
                decode_responses=True,
                socket_timeout=settings.redis_healthcheck_timeout_seconds,
                socket_connect_timeout=settings.redis_healthcheck_timeout_seconds,
            )
        )
    return RedisRuntimeClient(backend=backend, key_prefix=resolved_prefix or "runtime_state")


@lru_cache
def get_redis_runtime_client() -> RedisRuntimeClient:
    """读取配置并创建共享运行态客户端；保留为业务唯一入口。"""

    return create_runtime_state_client()


def reset_redis_runtime_client() -> None:
    """清理缓存的运行态客户端，供测试切换环境变量。"""

    get_redis_runtime_client.cache_clear()


def ensure_redis_runtime_available() -> None:
    """校验运行态后端可用，失败时转换为启动期可读错误。"""

    client = get_redis_runtime_client()
    try:
        client.ping()
        logger.info(
            "运行态存储健康检查通过。",
            extra={
                "event": "redis.runtime.health.ok",
                "runtime_state_backend": client.backend_kind,
                "runtime_state_ephemeral": client.ephemeral,
            },
        )
    except RuntimeStateUnavailableError:
        logger.error(
            "运行态存储健康检查失败。",
            extra={"event": "redis.runtime.health.failed", "runtime_state_backend": client.backend_kind},
        )
        raise


def parse_runtime_state_url(redis_url: str) -> tuple[str, str]:
    """严格解析 `REDIS_URL`，返回后端 scheme 与 `memory://<name>` 实例标识。"""

    normalized = str(redis_url or "").strip()
    if not normalized:
        raise RuntimeStateConfigurationError("REDIS_URL 不能为空，请配置 redis:// 或 memory://<name>。")
    scheme = normalized.partition("://")[0].strip().lower()
    if scheme not in SUPPORTED_RUNTIME_STATE_SCHEMES:
        raise RuntimeStateConfigurationError(
            "REDIS_URL 只支持 redis://、rediss:// 或 memory://<name>，当前 scheme 不受支持。"
        )
    if scheme != MEMORY_RUNTIME_STATE_SCHEME:
        return scheme, ""
    parsed = urlparse(normalized)
    instance_name = (parsed.netloc or parsed.path).strip().strip("/")
    if not instance_name:
        raise RuntimeStateConfigurationError(
            "memory:// 必须带实例标识，请使用 memory://lite；该标识只是本进程的配置名，不提供跨进程共享。"
        )
    if parsed.path.strip("/"):
        raise RuntimeStateConfigurationError("memory:// 标识只允许出现在主机位置，例如 memory://lite。")
    return scheme, instance_name


def resolve_runtime_state_profile(redis_url: str) -> tuple[str, bool]:
    """静态判定后端类型与临时性，不建立连接、不输出 URL。"""

    scheme = str(redis_url or "").strip().partition("://")[0].strip().lower()
    if scheme == MEMORY_RUNTIME_STATE_SCHEME:
        return "memory", True
    if scheme in REDIS_RUNTIME_STATE_SCHEMES:
        return "redis", False
    return "invalid", False


def validate_runtime_state_deployment(settings: Any | None = None) -> None:
    """拒绝正式运行中可识别的错误组合，仅由应用生命周期调用。

    迁移脚本等仅为了不连接 Redis 而设置 `memory://` 的场景不经过本校验。
    """

    resolved = settings or get_settings()
    scheme, instance_name = parse_runtime_state_url(resolved.redis_url)
    if scheme != MEMORY_RUNTIME_STATE_SCHEME:
        return
    if is_postgresql_database_url(resolved.database_url):
        raise RuntimeStateConfigurationError(
            "memory:// 只适用于 SQLite Lite 单进程部署；PostgreSQL 部署必须配置真实 redis:// 或 rediss://。"
        )
    workers = read_explicit_worker_count()
    if workers is not None:
        worker_key, worker_count = workers
        raise RuntimeStateConfigurationError(
            f"memory:// 是进程内运行态，不允许 {worker_key}={worker_count}：请保持单 Backend 进程，"
            "或改用真实 Redis 承载运行态。"
        )
    logger.info(
        "运行态后端为进程内实例。",
        extra={
            "event": "runtime_state.deployment.memory",
            "runtime_state_backend": MEMORY_RUNTIME_STATE_SCHEME,
            "runtime_state_ephemeral": True,
            "runtime_state_instance": instance_name,
        },
    )


def is_postgresql_database_url(database_url: str) -> bool:
    """判断数据库连接串是否指向 PostgreSQL。"""

    try:
        return make_url(str(database_url or "")).drivername.startswith("postgresql")
    except Exception:  # noqa: BLE001
        return False


__all__ = [
    "FORBIDDEN_RUNTIME_STATE_COMMANDS",
    "InMemoryRuntimeStateBackend",
    "MEMORY_RUNTIME_STATE_SCHEME",
    "REDIS_RUNTIME_STATE_SCHEMES",
    "REGISTERED_RUNTIME_STATE_COMMANDS",
    "RUNTIME_STATE_HELPER_COMMANDS",
    "RedisRuntimeClient",
    "RedisRuntimeStateBackend",
    "RuntimeStateBatch",
    "RuntimeStateCapacityError",
    "RuntimeStateCommands",
    "RuntimeStateConfigurationError",
    "RuntimeStateStats",
    "RuntimeStateTypeError",
    "RuntimeStateUnavailableError",
    "create_runtime_state_client",
    "ensure_redis_runtime_available",
    "get_redis_runtime_client",
    "is_postgresql_database_url",
    "parse_runtime_state_url",
    "reset_redis_runtime_client",
    "resolve_runtime_state_profile",
    "validate_runtime_state_deployment",
]