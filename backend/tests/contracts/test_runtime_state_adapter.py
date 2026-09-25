"""文件功能：在 memory:// 与真实 Redis 上执行同一组业务操作，对拍归一化结果。

两种后端各自与同一份期望值比较，等价于彼此对拍，同时把可观察语义固定在契约里；
TTL 只比较合法区间，避免依赖毫秒级时钟偶然性。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from typing import Any
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services import pat_security_service
from app.services.pat_security_service import PatRateLimitService
from app.services.redis_runtime_client import RedisRuntimeClient, create_runtime_state_client
from app.services.runtime_artifact_store import RuntimeArtifactStore


PARITY_REDIS_URL_ENV = "RUNTIME_STATE_PARITY_REDIS_URL"
PARITY_REQUIRED_ENV = "RUNTIME_STATE_PARITY_REQUIRED"
# 对拍必须使用独立的非 0、非 E2E(15) 库，避免触碰部署与 E2E 数据。
DISALLOWED_REDIS_DATABASES = {0, 15}


def _parity_redis_url() -> str:
    """读取对拍 Redis 地址；缺失时按门禁要求显式跳过或失败。"""

    raw = os.environ.get(PARITY_REDIS_URL_ENV, "").strip()
    if not raw:
        if os.environ.get(PARITY_REQUIRED_ENV, "").strip() == "1":
            pytest.fail(
                f"发布门禁要求配置 {PARITY_REDIS_URL_ENV}：缺少独立对拍 Redis 时不得视为对拍通过。"
            )
        return ""
    if not raw.startswith(("redis://", "rediss://")):
        pytest.fail(f"{PARITY_REDIS_URL_ENV} 必须是 redis:// 或 rediss:// 地址。")
    database = raw.rstrip("/").rsplit("/", 1)[-1]
    if not database.isdigit() or int(database) in DISALLOWED_REDIS_DATABASES:
        pytest.fail(
            f"{PARITY_REDIS_URL_ENV} 必须使用独立的非 0/非 15 库号，避免触碰部署环境与 E2E 数据。"
        )
    if raw == str(get_settings().redis_url or "").strip():
        pytest.fail(f"{PARITY_REDIS_URL_ENV} 不能与部署环境 REDIS_URL 指向同一实例。")
    return raw


def _purge_parity_prefix(url: str, prefix: str) -> None:
    """只清理本次对拍随机前缀下的 key，不触碰其它前缀。"""

    from redis import Redis

    client = Redis.from_url(url, decode_responses=True)
    try:
        keys = list(client.scan_iter(match=f"{prefix}:*", count=200))
        if keys:
            client.delete(*keys)
    finally:
        client.close()


@pytest.fixture(params=["memory", "redis"])
def parity_runtime(request: pytest.FixtureRequest) -> Iterator[tuple[str, RedisRuntimeClient]]:
    """为两种后端分别提供隔离实例；缺少对拍 Redis 时显式跳过。"""

    prefix = f"parity_{uuid4().hex[:10]}"
    if request.param == "memory":
        yield "memory", create_runtime_state_client(redis_url="memory://parity", key_prefix=prefix)
        return
    url = _parity_redis_url()
    if not url:
        pytest.skip(f"未配置 {PARITY_REDIS_URL_ENV}：本机跳过真实 Redis 对拍，CI 发布门禁必须执行本用例。")
    client = create_runtime_state_client(redis_url=url, key_prefix=prefix)
    try:
        yield "redis", client
    finally:
        _purge_parity_prefix(url, prefix)


def _capture_limited(call: Callable[..., None], *args: Any) -> tuple[int, int]:
    """捕获限流异常并返回状态码与 Retry-After 秒数。"""

    with pytest.raises(AppException) as exc_info:
        call(*args)
    retry_after = str(exc_info.value.headers.get("Retry-After") or "0")
    return exc_info.value.status_code, int(retry_after)


async def _artifact_lifecycle(store: RuntimeArtifactStore) -> dict[str, Any]:
    """执行预览 artifact 的写入、读取、删除完整生命周期。"""

    artifact_id = f"parity_{uuid4().hex[:10]}"
    created = await store.put_artifact(
        tenant_id="tenant_parity",
        workspace_id=7,
        project_id=11,
        artifact_kind="page-preview",
        manifest={"preview_kind": "project", "version": "1"},
        config_bundle={"app": {"title": "parity"}},
        modules_data=[{"logical_path": "src/views/index.vue", "content": "<template />"}],
        ttl_seconds=600,
        artifact_id=artifact_id,
    )
    manifest = await store.get_manifest(created)
    config = await store.get_config_bundle(created)
    modules = await store.get_modules(created, ["src/views/index.vue", "src/views/missing.vue"])
    single_module = await store.get_module(created, "src/views/index.vue")
    deleted_keys = await store.delete_artifact(created)
    return {
        "artifact_id_stable": created == artifact_id,
        "manifest_kind": (manifest or {}).get("preview_kind"),
        "manifest_version": (manifest or {}).get("version"),
        "config_title": (config or {}).get("app", {}).get("title"),
        "single_module": single_module,
        "batch_module_missing_is_none": modules is None,
        "deleted_keys": deleted_keys,
        "manifest_after_delete": await store.get_manifest(created),
        "module_after_delete": await store.get_module(created, "src/views/index.vue"),
    }


async def _artifact_ttl_window(client: RedisRuntimeClient, store: RuntimeArtifactStore) -> dict[str, Any]:
    """预览 artifact 的 manifest 与 meta 必须同时带上合法 TTL。"""

    artifact_id = f"parity_{uuid4().hex[:10]}"
    await store.put_artifact(
        tenant_id="tenant_parity",
        workspace_id=7,
        project_id=None,
        artifact_kind="page-preview",
        manifest={"preview_kind": "page"},
        config_bundle={},
        modules_data=[],
        ttl_seconds=600,
        artifact_id=artifact_id,
    )
    manifest_ttl = client.ttl(client.key(f"runtime:artifact:{artifact_id}:manifest"))
    meta_ttl = client.ttl(client.key(f"runtime:artifact:{artifact_id}:meta"))
    missing_ttl = client.ttl(client.key("runtime:artifact:absent:manifest"))
    await store.delete_artifact(artifact_id)
    return {
        "manifest_ttl_in_window": 0 < manifest_ttl <= 600,
        "meta_ttl_in_window": 0 < meta_ttl <= 600,
        "missing_key_ttl": missing_ttl,
    }


async def _build_state_hash(client: RedisRuntimeClient, store: RuntimeArtifactStore) -> dict[str, Any]:
    """构建任务运行态缓存使用 Hash 与 TTL，读取结果必须一致。"""

    job_id = int(uuid4().int % 1_000_000) + 1
    await store.put_build_state(
        job_id=job_id,
        mapping={"status": "running", "project_id": 3, "error_message": "", "runtime_dispatch_at": None},
        ttl_seconds=120,
    )
    state = await _to_thread(client.hgetall, client.key(f"runtime:build:{job_id}"))
    ttl = await _to_thread(client.ttl, client.key(f"runtime:build:{job_id}"))
    await _to_thread(client.delete, client.key(f"runtime:build:{job_id}"))
    return {
        "status": state.get("status"),
        "project_id": state.get("project_id"),
        "error_message": state.get("error_message"),
        "null_normalized_to_empty": state.get("runtime_dispatch_at"),
        "ttl_in_window": 0 < ttl <= 120,
    }


async def _empty_hset_and_bad_incr(client: RedisRuntimeClient) -> dict[str, Any]:
    """空 HSET 不建 key；INCR 非整数必须是取值错误而不是后端不可用。"""

    empty_key = client.key("parity_empty_hset")
    added = await _to_thread(client.hset, empty_key, {})
    empty_ttl = await _to_thread(client.ttl, empty_key)
    text_key = client.key("parity_bad_incr")
    await _to_thread(client.set, text_key, "abc")
    try:
        await _to_thread(client.incr, text_key)
        incr_error = "none"
    except ValueError:
        incr_error = "value"
    except Exception as exc:  # noqa: BLE001
        incr_error = type(exc).__name__
    await _to_thread(client.delete, empty_key, text_key)
    return {
        "empty_hset_added": added,
        "empty_hset_creates_key": empty_ttl != -2,
        "incr_error_kind": incr_error,
    }


async def _nx_and_delete(client: RedisRuntimeClient) -> dict[str, Any]:
    """SET NX 与 DELETE 计数在两种后端上必须给出相同结论。"""

    throttle_key = client.key("pat:last_used_throttle:parity")
    first = await _to_thread(client.set, throttle_key, "1", ex=300, nx=True)
    second = await _to_thread(client.set, throttle_key, "1", ex=300, nx=True)
    kept = await _to_thread(client.get, throttle_key)
    deleted = await _to_thread(client.delete, throttle_key, client.key("pat:absent"))
    return {
        "first_claim": first,
        "second_claim": second,
        "value_kept": kept,
        "delete_count": deleted,
        "value_after_delete": await _to_thread(client.get, throttle_key),
    }


async def _pat_limits(client: RedisRuntimeClient, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """PAT 限流、封禁与失败计数在两种后端上必须给出相同可观察结果。"""

    monkeypatch.setattr(pat_security_service, "get_redis_runtime_client", lambda: client)
    ip = "198.51.100.77"
    public_id = "0123456789abcdef"
    for _ in range(60):
        await _to_thread(PatRateLimitService.check_ip_rate_limit, ip)
    limit_status, limit_retry_after = _capture_limited(PatRateLimitService.check_ip_rate_limit, ip)
    window_ttl = client.ttl(client.key(f"pat:rate_limit:ip:{ip}"))

    for _ in range(5):
        await _to_thread(PatRateLimitService.record_auth_failure, ip, public_id)
    lock_status, lock_retry_after = _capture_limited(
        PatRateLimitService.check_auth_failure_rate_limit, ip, public_id
    )
    lock_ttl = client.ttl(client.key(f"pat:lockout:ip:{ip}:{public_id}"))
    return {
        "rate_limit_status": limit_status,
        "rate_limit_retry_positive": limit_retry_after > 0,
        "window_ttl_in_range": 0 < window_ttl <= 60,
        "lockout_status": lock_status,
        "lockout_retry_positive": lock_retry_after > 0,
        "lockout_ttl_in_range": 0 < lock_ttl <= 900,
        "failure_bucket_cleared": (
            await _to_thread(client.get, client.key(f"pat:auth_fail:ip:{ip}:{public_id}")) is None
        ),
    }


async def _to_thread(call: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """把同步命令放到线程执行，贴合业务侧对同步后端的调用方式。"""

    import asyncio

    return await asyncio.to_thread(call, *args, **kwargs)


@pytest.mark.asyncio
async def test_artifact_lifecycle_should_match_expected_contract(
    parity_runtime: tuple[str, RedisRuntimeClient],
) -> None:
    """预览 artifact 生命周期在两种后端上必须产生同一组可观察结果。"""

    _, client = parity_runtime
    result = await _artifact_lifecycle(RuntimeArtifactStore(runtime_client=client))

    assert result == {
        "artifact_id_stable": True,
        "manifest_kind": "project",
        "manifest_version": "1",
        "config_title": "parity",
        "single_module": "<template />",
        "batch_module_missing_is_none": True,
        "deleted_keys": 4,
        "manifest_after_delete": None,
        "module_after_delete": None,
    }


@pytest.mark.asyncio
async def test_artifact_ttl_should_land_in_legal_window(
    parity_runtime: tuple[str, RedisRuntimeClient],
) -> None:
    """artifact 主 key、元信息与缺失 key 的 TTL 语义必须一致。"""

    _, client = parity_runtime
    result = await _artifact_ttl_window(client, RuntimeArtifactStore(runtime_client=client))

    assert result == {
        "manifest_ttl_in_window": True,
        "meta_ttl_in_window": True,
        "missing_key_ttl": -2,
    }


@pytest.mark.asyncio
async def test_build_state_hash_should_match(
    parity_runtime: tuple[str, RedisRuntimeClient],
) -> None:
    """构建运行态 Hash 的字段归一化与 TTL 必须一致。"""

    _, client = parity_runtime
    result = await _build_state_hash(client, RuntimeArtifactStore(runtime_client=client))

    assert result == {
        "status": "running",
        "project_id": "3",
        "error_message": "",
        "null_normalized_to_empty": "",
        "ttl_in_window": True,
    }


@pytest.mark.asyncio
async def test_empty_hset_and_bad_incr_should_match(
    parity_runtime: tuple[str, RedisRuntimeClient],
) -> None:
    """空 HSET 不建 key，INCR 非整数必须归类为取值错误。"""

    _, client = parity_runtime
    result = await _empty_hset_and_bad_incr(client)

    assert result == {
        "empty_hset_added": 0,
        "empty_hset_creates_key": False,
        "incr_error_kind": "value",
    }


@pytest.mark.asyncio
async def test_set_nx_and_delete_should_match(
    parity_runtime: tuple[str, RedisRuntimeClient],
) -> None:
    """短锁与节流依赖的 SET NX、DELETE 计数必须一致。"""

    _, client = parity_runtime
    result = await _nx_and_delete(client)

    assert result == {
        "first_claim": True,
        "second_claim": False,
        "value_kept": "1",
        "delete_count": 1,
        "value_after_delete": None,
    }


@pytest.mark.asyncio
async def test_pat_limits_should_match(
    parity_runtime: tuple[str, RedisRuntimeClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PAT 限流、封禁与失败计数窗口必须一致。"""

    _, client = parity_runtime
    result = await _pat_limits(client, monkeypatch)

    assert result == {
        "rate_limit_status": 429,
        "rate_limit_retry_positive": True,
        "window_ttl_in_range": True,
        "lockout_status": 429,
        "lockout_retry_positive": True,
        "lockout_ttl_in_range": True,
        "failure_bucket_cleared": True,
    }


@pytest.mark.asyncio
async def test_artifact_write_should_be_atomic_on_both_backends(
    parity_runtime: tuple[str, RedisRuntimeClient],
) -> None:
    """artifact 写入完成后，主 key、模块与 TTL 必须同时可用。"""

    _, client = parity_runtime
    store = RuntimeArtifactStore(runtime_client=client)
    artifact_id = f"parity_{uuid4().hex[:10]}"
    await store.put_artifact(
        tenant_id="tenant_parity",
        workspace_id=1,
        project_id=1,
        artifact_kind="component-preview",
        manifest={"preview_kind": "component"},
        config_bundle={"app": {}},
        modules_data=[{"logical_path": "src/a.vue", "content": "a"}, {"logical_path": "src/b.vue", "content": "b"}],
        ttl_seconds=600,
        artifact_id=artifact_id,
    )

    assert await store.get_manifest(artifact_id) is not None
    assert await store.get_modules(artifact_id, ["src/a.vue", "src/b.vue"]) == {"src/a.vue": "a", "src/b.vue": "b"}
    assert client.ttl(client.key(f"runtime:artifact:{artifact_id}:modules")) > 0
    assert await store.delete_artifact(artifact_id) == 4