"""文件功能：测试 PAT 限速服务在进程内运行态下的计数、TTL 与封禁行为。"""

from __future__ import annotations

import pytest

from app.core.exceptions import AppException
from app.services import pat_security_service
from app.services.pat_security_service import PatRateLimitService
from app.services.redis_runtime_client import RedisRuntimeClient
from app.services.runtime_state import InMemoryRuntimeStateBackend


@pytest.fixture
def memory_runtime(monkeypatch: pytest.MonkeyPatch) -> InMemoryRuntimeStateBackend:
    """为测试注入独立的内存运行态后端，避免复用全局客户端。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test")
    monkeypatch.setattr(
        pat_security_service,
        "get_redis_runtime_client",
        lambda: RedisRuntimeClient(backend=backend, key_prefix="test"),
    )
    return backend


def test_memory_runtime_incr_preserves_ttl() -> None:
    """验证计数器递增不会清除已有 TTL，并返回兼容的 TTL 状态。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test")

    assert backend.ttl("counter") == -2
    assert backend.incr("counter") == 1
    assert backend.ttl("counter") == -1
    assert backend.expire("counter", 60) is True
    assert 0 < backend.ttl("counter") <= 60
    assert backend.incr("counter") == 2
    assert 0 < backend.ttl("counter") <= 60


def test_pat_ip_rate_limit_works_with_memory_runtime(memory_runtime: InMemoryRuntimeStateBackend) -> None:
    """验证进程内运行态不触发异常降级，且第 61 次请求被限流。"""

    ip = "192.0.2.20"

    for _ in range(60):
        PatRateLimitService.check_ip_rate_limit(ip)

    with pytest.raises(AppException) as exc_info:
        PatRateLimitService.check_ip_rate_limit(ip)

    assert exc_info.value.status_code == 429
    assert int(exc_info.value.headers["Retry-After"]) > 0
    assert memory_runtime.ttl("test:pat:rate_limit:ip:192.0.2.20") > 0


def test_pat_auth_failure_lockout_works_with_memory_runtime(memory_runtime: InMemoryRuntimeStateBackend) -> None:
    """验证进程内运行态能记录失败次数并读取封禁 TTL。"""

    ip = "192.0.2.21"
    public_id = "a1b2c3d4e5f60708"

    for _ in range(5):
        PatRateLimitService.record_auth_failure(ip, public_id)

    with pytest.raises(AppException) as exc_info:
        PatRateLimitService.check_auth_failure_rate_limit(ip, public_id)

    assert exc_info.value.status_code == 429
    assert int(exc_info.value.headers["Retry-After"]) > 0
    assert memory_runtime.ttl(f"test:pat:lockout:ip:{ip}:{public_id}") > 0


def test_pat_rate_limit_should_fail_open_when_runtime_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """运行态后端故障必须按既有策略放行，不能把缓存故障升级为鉴权失败。"""

    def _raise() -> None:
        raise RuntimeError("runtime state down")

    monkeypatch.setattr(pat_security_service, "get_redis_runtime_client", _raise)

    PatRateLimitService.check_ip_rate_limit("192.0.2.22")
    PatRateLimitService.check_auth_failure_rate_limit("192.0.2.22", "deadbeefdeadbeef")
    PatRateLimitService.record_auth_failure("192.0.2.22", "deadbeefdeadbeef")