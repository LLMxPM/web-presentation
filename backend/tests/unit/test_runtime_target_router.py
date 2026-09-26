"""文件功能：验证 Runtime 计算角色多副本选址（轮询/冷却）、全链路准入与满载错误映射。"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import AppSettings, parse_runtime_target_list
from app.core.exceptions import AppException
from app.services.runtime_target_router import (
    RUNTIME_ADMISSION_FULL,
    RUNTIME_CAPACITY_EXCEEDED,
    RuntimeTargetRouter,
    request_runtime_role_json,
)


def _settings(**overrides: object) -> AppSettings:
    """构造选址与准入相关测试配置。"""

    base: dict[str, object] = {
        "runtime_base_url": "http://runtime:7373",
        "runtime_preview_base_url": "",
        "runtime_build_base_url": "",
        "runtime_check_base_url": "",
        "runtime_build_base_urls": "",
        "runtime_check_base_urls": "",
        "runtime_target_failure_threshold": 2,
        "runtime_target_cooldown_seconds": 10.0,
        "runtime_build_max_inflight": 2,
        "runtime_check_max_inflight": 2,
        "runtime_light_max_inflight": 2,
    }
    base.update(overrides)
    return AppSettings(**base)  # type: ignore[arg-type]


class _FakeClock:
    """可控单调时钟，便于验证冷却到期行为。"""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ---------------------------------------------------------------------------
# 目标列表解析与回退
# ---------------------------------------------------------------------------


def test_parse_runtime_target_list_comma_separated() -> None:
    """逗号分隔配置应解析为去重、去尾斜杠的地址列表。"""

    assert parse_runtime_target_list("http://a:7373/, http://b:7373,http://a:7373") == [
        "http://a:7373",
        "http://b:7373",
    ]


def test_parse_runtime_target_list_json_array() -> None:
    """JSON 数组配置应解析为地址列表。"""

    assert parse_runtime_target_list('["http://a:7373","http://b:7373/"]') == [
        "http://a:7373",
        "http://b:7373",
    ]


def test_parse_runtime_target_list_rejects_invalid_json() -> None:
    """以 [ 开头但非法的 JSON 应在启动期报错。"""

    with pytest.raises(ValueError):
        parse_runtime_target_list("[http://a:7373")


def test_resolve_role_base_urls_prefers_plural_then_singular() -> None:
    """回退顺序：多副本列表 → 单地址 → runtime_base_url。"""

    multi = _settings(
        runtime_check_base_urls="http://c1:7373,http://c2:7373",
        runtime_check_base_url="http://check:7373",
    )
    assert multi.resolve_runtime_role_base_urls("check") == ["http://c1:7373", "http://c2:7373"]

    single = _settings(runtime_check_base_url="http://check:7373")
    assert single.resolve_runtime_role_base_urls("check") == ["http://check:7373"]

    fallback = _settings()
    assert fallback.resolve_runtime_role_base_urls("check") == ["http://runtime:7373"]


def test_resolve_role_base_url_returns_first_of_plural() -> None:
    """单地址解析在多副本配置下返回首个目标，保持旧调用兼容。"""

    settings = _settings(runtime_build_base_urls="http://b1:7373,http://b2:7373")
    assert settings.resolve_runtime_role_base_url("build") == "http://b1:7373"
    assert settings.resolve_runtime_role_base_urls("build") == ["http://b1:7373", "http://b2:7373"]


# ---------------------------------------------------------------------------
# 轮询与冷却
# ---------------------------------------------------------------------------


def test_ordered_candidates_rotates_round_robin() -> None:
    """连续选址应轮询推进起点，均匀分摊到各副本。"""

    clock = _FakeClock()
    router = RuntimeTargetRouter(settings_provider=lambda: _settings(), clock=clock)
    targets = ["http://a:7373", "http://b:7373", "http://c:7373"]

    first = router.ordered_candidates("check", targets)
    second = router.ordered_candidates("check", targets)
    third = router.ordered_candidates("check", targets)

    assert first[0] == "http://a:7373"
    assert second[0] == "http://b:7373"
    assert third[0] == "http://c:7373"


def test_consecutive_failures_enter_cooldown_then_recover() -> None:
    """连续失败达到阈值后目标进入冷却并排后，冷却到期后重新参与轮询。"""

    clock = _FakeClock()
    settings = _settings(runtime_target_failure_threshold=2, runtime_target_cooldown_seconds=10.0)
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=clock)
    targets = ["http://a:7373", "http://b:7373"]

    router.mark_failure("check", "http://a:7373")
    assert router.ordered_candidates("check", targets)[0] == "http://a:7373"

    router.mark_failure("check", "http://a:7373")
    cooled = router.ordered_candidates("check", targets)
    assert cooled[0] == "http://b:7373"
    assert cooled[-1] == "http://a:7373"

    clock.advance(11.0)
    recovered = router.ordered_candidates("check", targets)
    assert recovered[0] == "http://a:7373"


def test_success_resets_failure_streak() -> None:
    """目标成功后清零连续失败，不再进入冷却。"""

    clock = _FakeClock()
    settings = _settings(runtime_target_failure_threshold=2, runtime_target_cooldown_seconds=10.0)
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=clock)
    targets = ["http://a:7373", "http://b:7373"]

    router.mark_failure("check", "http://a:7373")
    router.mark_success("check", "http://a:7373")
    router.mark_failure("check", "http://a:7373")
    assert router.ordered_candidates("check", targets)[0] == "http://a:7373"


def test_all_targets_cooled_still_returns_candidates() -> None:
    """全部目标冷却时仍返回完整列表作为兜底，不产生选址黑洞。"""

    clock = _FakeClock()
    settings = _settings(runtime_target_failure_threshold=1, runtime_target_cooldown_seconds=30.0)
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=clock)
    targets = ["http://a:7373", "http://b:7373"]

    router.mark_failure("check", "http://a:7373", overloaded=True)
    router.mark_failure("check", "http://b:7373", overloaded=True)

    candidates = router.ordered_candidates("check", targets)
    assert sorted(candidates) == sorted(targets)


# ---------------------------------------------------------------------------
# 全链路准入
# ---------------------------------------------------------------------------


def test_admission_rejects_when_inflight_reaches_limit() -> None:
    """在途调用达到角色上限时立即返回稳定准入错误，释放后可继续接单。"""

    settings = _settings(runtime_check_max_inflight=1)
    router = RuntimeTargetRouter(settings_provider=lambda: settings)

    with router.admission("check"):
        with pytest.raises(AppException) as exc_info:
            with router.admission("check"):
                pass
    assert exc_info.value.code == RUNTIME_ADMISSION_FULL
    assert exc_info.value.status_code == 503

    with router.admission("check"):
        assert router.inflight_count("check") == 1


def test_admission_unlimited_when_limit_non_positive() -> None:
    """上限 <=0 表示不限制，多路在途均可进入。"""

    settings = _settings(runtime_build_max_inflight=0)
    router = RuntimeTargetRouter(settings_provider=lambda: settings)
    with router.admission("build"):
        with router.admission("build"):
            assert router.inflight_count("build") == 2


# ---------------------------------------------------------------------------
# 请求选址与 429/503 映射
# ---------------------------------------------------------------------------


def _routing_transport(
    handler_by_host: dict[str, httpx.Response | Exception],
) -> httpx.MockTransport:
    """按目标主机返回预设响应或抛出预设异常的 Mock transport。"""

    def handler(request: httpx.Request) -> httpx.Response:
        result = handler_by_host.get(request.url.host or "")
        if isinstance(result, Exception):
            raise result
        if result is None:
            return httpx.Response(502, json={"code": "UNREACHABLE", "message": "no handler"})
        return result

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_request_fails_over_to_idle_replica_on_overload() -> None:
    """首副本 429 满载时自动切换到空闲副本并成功返回。"""

    settings = _settings(runtime_check_base_urls="http://busy:7373,http://idle:7373")
    clock = _FakeClock()
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=clock)
    transport = _routing_transport(
        {
            "busy": httpx.Response(429, json={"code": "RUNTIME_VITE_QUEUE_FULL", "message": "busy"}),
            "idle": httpx.Response(200, json={"status": "passed"}),
        }
    )

    result = await request_runtime_role_json(
        role="check",
        method="POST",
        path="/__runtime_internal/v1/diagnostics/artifact",
        settings=settings,
        headers={},
        timeout_seconds=5.0,
        default_error_code="RUNTIME_DIAGNOSTICS_FAILED",
        json_payload={"artifact_id": "a"},
        transport=transport,
        router=router,
    )
    assert result == {"status": "passed"}


@pytest.mark.asyncio
async def test_request_maps_all_overloaded_to_stable_capacity_error() -> None:
    """全部副本满载时映射为稳定可重试容量错误码，而不是透传某个副本的业务码。"""

    settings = _settings(runtime_check_base_urls="http://busy1:7373,http://busy2:7373")
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=_FakeClock())
    transport = _routing_transport(
        {
            "busy1": httpx.Response(429, json={"code": "RUNTIME_VITE_QUEUE_FULL", "message": "busy"}),
            "busy2": httpx.Response(503, json={"code": "RUNTIME_VITE_QUEUE_FULL", "message": "busy"}),
        }
    )

    with pytest.raises(AppException) as exc_info:
        await request_runtime_role_json(
            role="check",
            method="POST",
            path="/__runtime_internal/v1/diagnostics/artifact",
            settings=settings,
            headers={},
            timeout_seconds=5.0,
            default_error_code="RUNTIME_DIAGNOSTICS_FAILED",
            json_payload={"artifact_id": "a"},
            transport=transport,
            router=router,
        )
    assert exc_info.value.code == RUNTIME_CAPACITY_EXCEEDED
    assert exc_info.value.status_code == 503
    assert (exc_info.value.headers or {}).get("Retry-After") == "5"


@pytest.mark.asyncio
async def test_request_should_not_map_config_error_503_to_capacity_exceeded() -> None:
    """配置/鉴权类 503 必须保留真实错误码，不得伪装成副本满载（M3）。"""

    settings = _settings(runtime_check_base_urls="http://a:7373,http://b:7373")
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=_FakeClock())
    transport = _routing_transport(
        {
            "a": httpx.Response(503, json={"code": "JWKS_URL_MISSING", "message": "未配置 JWKS"}),
            "b": httpx.Response(200, json={"status": "passed"}),
        }
    )

    with pytest.raises(AppException) as exc_info:
        await request_runtime_role_json(
            role="check",
            method="POST",
            path="/__runtime_internal/v1/diagnostics/artifact",
            settings=settings,
            headers={},
            timeout_seconds=5.0,
            default_error_code="RUNTIME_DIAGNOSTICS_FAILED",
            json_payload={"artifact_id": "a"},
            transport=transport,
            router=router,
        )
    assert exc_info.value.code == "JWKS_URL_MISSING"
    assert exc_info.value.code != RUNTIME_CAPACITY_EXCEEDED


@pytest.mark.asyncio
async def test_request_does_not_fail_over_on_business_error() -> None:
    """业务 4xx 直接返回，不消耗其它副本容量。"""

    settings = _settings(runtime_check_base_urls="http://a:7373,http://b:7373")
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=_FakeClock())
    transport = _routing_transport(
        {
            "a": httpx.Response(400, json={"code": "BAD_ARTIFACT", "message": "invalid"}),
            "b": httpx.Response(200, json={"status": "passed"}),
        }
    )

    with pytest.raises(AppException) as exc_info:
        await request_runtime_role_json(
            role="check",
            method="POST",
            path="/__runtime_internal/v1/diagnostics/artifact",
            settings=settings,
            headers={},
            timeout_seconds=5.0,
            default_error_code="RUNTIME_DIAGNOSTICS_FAILED",
            json_payload={"artifact_id": "a"},
            transport=transport,
            router=router,
        )
    assert exc_info.value.code == "BAD_ARTIFACT"
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_request_fails_over_on_unavailable_replica() -> None:
    """首副本不可达时切换到健康副本；不可达副本连续失败后被冷却。"""

    settings = _settings(
        runtime_build_base_urls="http://down:7373,http://up:7373",
        runtime_target_failure_threshold=1,
        runtime_target_cooldown_seconds=60.0,
    )
    clock = _FakeClock()
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=clock)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "down":
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json={"artifact_id": "a", "message": "ok"})

    result = await request_runtime_role_json(
        role="build",
        method="POST",
        path="/__runtime_internal/v1/builds/project",
        settings=settings,
        headers={},
        timeout_seconds=5.0,
        default_error_code="RUNTIME_REQUEST_FAILED",
        content=b"{}",
        transport=httpx.MockTransport(handler),
        router=router,
    )
    assert result["artifact_id"] == "a"

    # 故障副本进入冷却：下一轮选址把健康副本排在前面。
    ordered = router.ordered_candidates("build", settings.resolve_runtime_role_base_urls("build"))
    assert ordered[0] == "http://up:7373"


@pytest.mark.asyncio
async def test_build_post_should_not_failover_on_read_error() -> None:
    """构建 POST 在 ReadError（请求可能已到达）后禁止换副本重发（P1）。"""

    settings = _settings(runtime_build_base_urls="http://a:7373,http://b:7373")
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=_FakeClock())
    transport = _routing_transport(
        {
            "a": httpx.ReadError("connection reset while reading response"),
            "b": httpx.Response(200, json={"artifact_id": "a"}),
        }
    )

    with pytest.raises(AppException) as exc_info:
        await request_runtime_role_json(
            role="build",
            method="POST",
            path="/__runtime_internal/v1/builds/project",
            settings=settings,
            headers={},
            timeout_seconds=5.0,
            default_error_code="RUNTIME_REQUEST_FAILED",
            content=b"{}",
            transport=transport,
            router=router,
        )
    # 不得把非幂等构建 POST 重发到 b：b 不应被触及。
    assert exc_info.value.code == "RUNTIME_REQUEST_FAILED"


@pytest.mark.asyncio
async def test_build_post_should_not_failover_on_5xx() -> None:
    """构建 POST 在 5xx 后禁止换副本：第一副本可能已执行并上传。"""

    settings = _settings(runtime_build_base_urls="http://a:7373,http://b:7373")
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=_FakeClock())
    transport = _routing_transport(
        {
            "a": httpx.Response(500, json={"code": "BUILD_INTERNAL", "message": "boom"}),
            "b": httpx.Response(200, json={"artifact_id": "a"}),
        }
    )

    with pytest.raises(AppException) as exc_info:
        await request_runtime_role_json(
            role="build",
            method="POST",
            path="/__runtime_internal/v1/builds/project",
            settings=settings,
            headers={},
            timeout_seconds=5.0,
            default_error_code="RUNTIME_REQUEST_FAILED",
            content=b"{}",
            transport=transport,
            router=router,
        )
    assert exc_info.value.code == "BUILD_INTERNAL"
    assert (exc_info.value.data or {}).get("dispatch_may_have_started") is True


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [429, 503])
async def test_build_post_should_not_failover_on_ambiguous_capacity_response(status_code: int) -> None:
    """构建中回源或上传返回 429/503 时，不得误判为执行前满载并重发。"""

    settings = _settings(runtime_build_base_urls="http://a:7373,http://b:7373")
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=_FakeClock())
    transport = _routing_transport(
        {
            "a": httpx.Response(status_code, json={"code": "BUILD_ARTIFACT_UPLOAD_FAILED", "message": "upload failed"}),
            "b": httpx.Response(200, json={"artifact_id": "duplicate"}),
        }
    )

    with pytest.raises(AppException) as exc_info:
        await request_runtime_role_json(
            role="build",
            method="POST",
            path="/__runtime_internal/v1/builds/project",
            settings=settings,
            headers={},
            timeout_seconds=5.0,
            default_error_code="RUNTIME_REQUEST_FAILED",
            content=b"{}",
            transport=transport,
            router=router,
        )
    assert exc_info.value.code == "BUILD_ARTIFACT_UPLOAD_FAILED"
    assert (exc_info.value.data or {}).get("dispatch_may_have_started") is True


@pytest.mark.asyncio
async def test_build_post_can_failover_on_pre_dispatch_queue_full() -> None:
    """Runtime 明确在执行前拒绝构建时，允许将 POST 发给空闲副本。"""

    settings = _settings(runtime_build_base_urls="http://a:7373,http://b:7373")
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=_FakeClock())
    transport = _routing_transport(
        {
            "a": httpx.Response(429, json={"code": "RUNTIME_VITE_QUEUE_FULL", "message": "busy"}),
            "b": httpx.Response(200, json={"artifact_id": "built"}),
        }
    )

    result = await request_runtime_role_json(
        role="build",
        method="POST",
        path="/__runtime_internal/v1/builds/project",
        settings=settings,
        headers={},
        timeout_seconds=5.0,
        default_error_code="RUNTIME_REQUEST_FAILED",
        content=b"{}",
        transport=transport,
        router=router,
    )
    assert result == {"artifact_id": "built"}


@pytest.mark.asyncio
async def test_check_post_should_still_failover_on_read_error() -> None:
    """幂等/可重试角色的 ReadError 仍可换副本。"""

    settings = _settings(runtime_check_base_urls="http://a:7373,http://b:7373")
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=_FakeClock())
    transport = _routing_transport(
        {
            "a": httpx.ReadError("connection reset"),
            "b": httpx.Response(200, json={"status": "passed"}),
        }
    )

    result = await request_runtime_role_json(
        role="check",
        method="POST",
        path="/__runtime_internal/v1/diagnostics/artifact",
        settings=settings,
        headers={},
        timeout_seconds=5.0,
        default_error_code="RUNTIME_DIAGNOSTICS_FAILED",
        json_payload={"artifact_id": "a"},
        transport=transport,
        router=router,
    )
    assert result == {"status": "passed"}


@pytest.mark.asyncio
async def test_light_admission_zero_means_unlimited() -> None:
    """RUNTIME_LIGHT_MAX_INFLIGHT=0 表示不限制，不得回退为 check 上限（P2）。"""

    settings = _settings(runtime_check_max_inflight=1, runtime_light_max_inflight=0)
    router = RuntimeTargetRouter(settings_provider=lambda: settings, clock=_FakeClock())

    # light 0 = 不限制：连续进入两次均成功。
    with router.admission("light"):
        pass
    with router.admission("light"):
        pass

    # check 上限为 1：第二次并发进入应被拒绝。
    with router.admission("check"):
        with pytest.raises(AppException) as exc_info:
            with router.admission("check"):
                pass
        assert exc_info.value.code == RUNTIME_ADMISSION_FULL
