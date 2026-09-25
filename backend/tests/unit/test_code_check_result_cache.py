"""文件功能：验证代码检查结果缓存的命中、失效、in-flight 合并、瞬态不缓存与鉴权先行语义。"""

from __future__ import annotations

import asyncio

import pytest

from app.core.exceptions import AppException
from app.services.code_check_result_cache import (
    CODE_CHECK_RULES_VERSION,
    CodeCheckResultCache,
    compute_check_fingerprint,
    is_transient_check_result,
    is_transient_infrastructure_error,
)

pytestmark = pytest.mark.unit


def _stable_result(marker: str = "ok") -> dict[str, object]:
    """构造稳定可缓存的检查结果。"""

    return {
        "success": True,
        "status": "passed",
        "summary": f"代码检查通过。{marker}",
        "diagnostics": [],
        "stages": {"compile": "passed", "render": "passed"},
        "retryable": False,
    }


def _transient_result() -> dict[str, object]:
    """构造瞬态基础设施失败结果。"""

    return {
        "success": False,
        "status": "unavailable",
        "retryable": True,
        "summary": "Renderer 暂不可用。",
        "diagnostics": [
            {
                "severity": "error",
                "source": "infrastructure",
                "code": "RENDER_SERVICE_UNAVAILABLE",
                "message": "Renderer 暂不可用。",
            }
        ],
        "stages": {"compile": "passed", "render": "unavailable"},
    }


async def test_cache_should_hit_on_same_fingerprint() -> None:
    """相同指纹应命中复用，不重复执行检查。"""

    cache = CodeCheckResultCache(max_entries=8, ttl_seconds=60)
    executions = 0

    async def factory() -> dict[str, object]:
        nonlocal executions
        executions += 1
        return _stable_result()

    first, first_source = await cache.get_or_execute("fp-a", factory)
    second, second_source = await cache.get_or_execute("fp-a", factory)

    assert first_source == "miss"
    assert second_source == "hit"
    assert executions == 1
    assert first["summary"] == second["summary"]
    assert cache.snapshot_metrics()["hits"] == 1
    assert cache.snapshot_metrics()["misses"] == 1
    assert cache.snapshot_metrics()["size"] == 1


async def test_cache_should_invalidate_when_fingerprint_changes() -> None:
    """任一指纹组成变化应导致未命中并重新执行。"""

    cache = CodeCheckResultCache(max_entries=8, ttl_seconds=60)
    executions = 0

    async def factory() -> dict[str, object]:
        nonlocal executions
        executions += 1
        return _stable_result(marker=str(executions))

    await cache.get_or_execute("fp-a", factory)
    await cache.get_or_execute("fp-b", factory)

    assert executions == 2
    assert cache.snapshot_metrics()["hits"] == 0
    assert cache.snapshot_metrics()["misses"] == 2


async def test_cache_should_coalesce_inflight_duplicates() -> None:
    """同一时刻多个相同检查应合并为一次执行。"""

    cache = CodeCheckResultCache(max_entries=8, ttl_seconds=60)
    executions = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def factory() -> dict[str, object]:
        nonlocal executions
        executions += 1
        started.set()
        await release.wait()
        return _stable_result()

    task_a = asyncio.create_task(cache.get_or_execute("fp-inflight", factory))
    await started.wait()
    task_b = asyncio.create_task(cache.get_or_execute("fp-inflight", factory))
    # 让 B 进入等待
    await asyncio.sleep(0)
    release.set()
    result_a, source_a = await task_a
    result_b, source_b = await task_b

    assert executions == 1
    assert {source_a, source_b} == {"miss", "coalesced"}
    assert result_a["summary"] == result_b["summary"] == "代码检查通过。ok"
    metrics = cache.snapshot_metrics()
    assert metrics["coalesced"] == 1
    assert metrics["misses"] == 1


async def test_cache_should_not_store_transient_results() -> None:
    """瞬态基础设施失败不得写入长期缓存。"""

    cache = CodeCheckResultCache(max_entries=8, ttl_seconds=60)
    executions = 0

    async def factory() -> dict[str, object]:
        nonlocal executions
        executions += 1
        return _transient_result()

    first, first_source = await cache.get_or_execute("fp-transient", factory)
    _second, second_source = await cache.get_or_execute("fp-transient", factory)

    assert first_source == "miss"
    assert second_source == "miss"
    assert executions == 2
    assert first["status"] == "unavailable"
    assert cache.snapshot_metrics()["size"] == 0
    assert cache.snapshot_metrics()["skipped_transient"] == 2


async def test_cache_should_not_store_exceptions() -> None:
    """执行异常一律不写入缓存，后续调用可重试。"""

    cache = CodeCheckResultCache(max_entries=8, ttl_seconds=60)
    executions = 0

    async def factory() -> dict[str, object]:
        nonlocal executions
        executions += 1
        raise AppException(status_code=502, code="RUNTIME_DIAGNOSTICS_FAILED", detail="Runtime 不可用。")

    with pytest.raises(AppException):
        await cache.get_or_execute("fp-error", factory)
    with pytest.raises(AppException):
        await cache.get_or_execute("fp-error", factory)

    assert executions == 2
    assert cache.snapshot_metrics()["size"] == 0


async def test_cache_should_expire_entries_by_ttl() -> None:
    """TTL 到期后应失效并重新执行。"""

    cache = CodeCheckResultCache(max_entries=8, ttl_seconds=0.01)
    executions = 0

    async def factory() -> dict[str, object]:
        nonlocal executions
        executions += 1
        return _stable_result()

    await cache.get_or_execute("fp-ttl", factory)
    await asyncio.sleep(0.02)
    _, source = await cache.get_or_execute("fp-ttl", factory)

    assert executions == 2
    assert source == "miss"
    assert cache.snapshot_metrics()["expired"] == 1


async def test_cache_should_evict_when_over_capacity() -> None:
    """超过有界容量时应按 LRU 淘汰。"""

    cache = CodeCheckResultCache(max_entries=2, ttl_seconds=60)

    async def factory() -> dict[str, object]:
        return _stable_result()

    await cache.get_or_execute("fp-1", factory)
    await cache.get_or_execute("fp-2", factory)
    await cache.get_or_execute("fp-3", factory)

    metrics = cache.snapshot_metrics()
    assert metrics["size"] == 2
    assert metrics["evictions"] == 1
    # 最早的 fp-1 被淘汰，应重新执行
    _, source = await cache.get_or_execute("fp-1", factory)
    assert source == "miss"


def test_is_transient_check_result_should_detect_infrastructure_failures() -> None:
    """unavailable/retryable/infrastructure 诊断均视为瞬态。"""

    assert is_transient_check_result(_transient_result()) is True
    assert is_transient_check_result({"status": "unavailable", "diagnostics": []}) is True
    assert is_transient_check_result({"status": "failed", "retryable": True}) is True
    assert is_transient_check_result({"stages": {"render": "unavailable"}}) is True
    assert is_transient_check_result({"diagnostics": [{"source": "infrastructure"}]}) is True
    assert is_transient_check_result(_stable_result()) is False
    assert is_transient_check_result({"status": "failed", "retryable": False, "diagnostics": []}) is False


def test_is_transient_infrastructure_error_should_detect_timeouts_and_5xx() -> None:
    """超时与 502/503 等基础设施异常视为瞬态。"""

    assert is_transient_infrastructure_error(TimeoutError()) is True
    assert is_transient_infrastructure_error(TimeoutError()) is True
    assert is_transient_infrastructure_error(
        AppException(status_code=502, code="RUNTIME_DIAGNOSTICS_FAILED", detail="x")
    ) is True
    assert is_transient_infrastructure_error(
        AppException(status_code=503, code="RENDER_SERVICE_UNAVAILABLE", detail="x")
    ) is True
    assert is_transient_infrastructure_error(
        AppException(status_code=403, code="AI_PAGE_SCOPE_DENIED", detail="x")
    ) is False


def test_compute_check_fingerprint_should_change_for_any_component() -> None:
    """指纹任一组成变化即应改变。"""

    base = {
        "kind": "page",
        "source": "<template><main>a</main></template>",
        "workspace_id": 1,
        "project_id": 2,
        "module_path": "src/views/A.vue",
        "dependency_identity": ["cv:Cmp:v1:abc"],
        "runtime_kit_version": "1.0.0",
        "compile_config": "compile-hash",
        "theme_style": "theme-hash",
        "check_rules_version": CODE_CHECK_RULES_VERSION,
    }
    base_fp = compute_check_fingerprint(base)
    assert base_fp.startswith("sha256:")

    mutations = [
        {"source": "<template><main>b</main></template>"},
        {"dependency_identity": ["cv:Cmp:v2:abc"]},
        {"runtime_kit_version": "1.0.1"},
        {"compile_config": "compile-hash-2"},
        {"theme_style": "theme-hash-2"},
        {"check_rules_version": "code-check-rules.v2"},
        {"module_path": "src/views/B.vue"},
        {"workspace_id": 9},
        {"project_id": 9},
        {"kind": "component"},
    ]
    for mutation in mutations:
        changed = {**base, **mutation}
        assert compute_check_fingerprint(changed) != base_fp, mutation

    # 相同载荷（键序不同）应稳定
    reordered = dict(reversed(list(base.items())))
    assert compute_check_fingerprint(reordered) == base_fp


async def test_auth_must_run_before_cache_lookup() -> None:
    """鉴权失败时不得查找缓存，缓存不能替代权限校验。"""

    class SpyCache(CodeCheckResultCache):
        def __init__(self) -> None:
            super().__init__(max_entries=8, ttl_seconds=60)
            self.lookups = 0

        async def get_or_execute(self, fingerprint, factory):  # type: ignore[no-untyped-def]
            self.lookups += 1
            return await super().get_or_execute(fingerprint, factory)


    from app.services.code_check_service import CodeCheckService

    spy = SpyCache()
    service = CodeCheckService.__new__(CodeCheckService)
    service.session = None  # type: ignore[assignment]
    service.result_cache = spy
    service.fingerprint_builder = None  # type: ignore[assignment]

    class _FakePage:
        id = 1
        workspace_id = 10
        project_id = 2
        file_type = "vue"
        page_content = "<template><main>a</main></template>"
        code = "A"

    class _FakePageService:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def _get_page_or_raise(self, _page_id: int):
            return _FakePage()

    import app.services.code_check_service as code_check_module

    original = code_check_module.PageService
    code_check_module.PageService = _FakePageService  # type: ignore[misc,assignment]
    try:
        with pytest.raises(AppException) as exc_info:
            await service.check_page_code(
                page_id=1,
                user_id=1,
                workspace_id=999,  # 与页面 workspace 不一致
                content="<template><main>a</main></template>",
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "AI_PAGE_SCOPE_DENIED"
        assert spy.lookups == 0
    finally:
        code_check_module.PageService = original  # type: ignore[misc]
