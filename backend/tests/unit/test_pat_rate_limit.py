"""文件功能：测试 PAT 限速服务在内存 Redis 运行态下的计数、TTL 与封禁行为。"""

from __future__ import annotations

import pytest

from app.core.exceptions import AppException
from app.services import pat_security_service
from app.services.pat_security_service import PatRateLimitService
from app.services.redis_runtime_client import InMemoryRedis, RedisRuntimeClient


@pytest.fixture
def memory_redis(monkeypatch: pytest.MonkeyPatch) -> InMemoryRedis:
    """为测试注入独立的内存 Redis，避免复用全局运行态客户端。"""

    client = InMemoryRedis()
    monkeypatch.setattr(
        pat_security_service,
        "get_redis_runtime_client",
        lambda: RedisRuntimeClient(client=client, key_prefix="test"),
    )
    return client


def test_memory_redis_incr_preserves_ttl() -> None:
    """验证计数器递增不会清除已有 TTL，并返回 Redis 兼容的 TTL 状态。"""

    client = InMemoryRedis()

    assert client.ttl("counter") == -2
    assert client.incr("counter") == 1
    assert client.ttl("counter") == -1
    assert client.expire("counter", 60) is True
    assert 0 < client.ttl("counter") <= 60
    assert client.incr("counter") == 2
    assert 0 < client.ttl("counter") <= 60


def test_pat_ip_rate_limit_works_with_memory_redis(memory_redis: InMemoryRedis) -> None:
    """验证内存 Redis 不再触发异常降级，且第 61 次请求被限流。"""

    ip = "192.0.2.20"

    for _ in range(60):
        PatRateLimitService.check_ip_rate_limit(ip)

    with pytest.raises(AppException) as exc_info:
        PatRateLimitService.check_ip_rate_limit(ip)

    assert exc_info.value.status_code == 429
    assert memory_redis.ttl("test:pat:rate_limit:ip:192.0.2.20") > 0


def test_pat_auth_failure_lockout_works_with_memory_redis(memory_redis: InMemoryRedis) -> None:
    """验证内存 Redis 能记录失败次数并读取封禁 TTL。"""

    ip = "192.0.2.21"
    public_id = "a1b2c3d4e5f60708"

    for _ in range(5):
        PatRateLimitService.record_auth_failure(ip, public_id)

    with pytest.raises(AppException) as exc_info:
        PatRateLimitService.check_auth_failure_rate_limit(ip, public_id)

    assert exc_info.value.status_code == 429
    assert memory_redis.ttl(f"test:pat:lockout:ip:{ip}:{public_id}") > 0
