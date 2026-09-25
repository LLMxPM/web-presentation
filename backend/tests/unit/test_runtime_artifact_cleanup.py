"""文件功能：验证 Runtime 临时 artifact 主动删除和内存 TTL 全局清扫。"""

from __future__ import annotations

import pytest

from app.services.redis_runtime_client import RedisRuntimeClient
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.runtime_state import InMemoryRuntimeStateBackend


@pytest.mark.asyncio
async def test_runtime_artifact_should_delete_all_related_keys() -> None:
    """诊断结束后主动删除应覆盖 manifest、配置、模块、资源和元信息。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test")
    runtime = RedisRuntimeClient(backend=backend, key_prefix="test")
    store = RuntimeArtifactStore(runtime_client=runtime)
    artifact_id = await store.put_artifact(
        tenant_id="tenant_1",
        workspace_id=1,
        project_id=2,
        artifact_kind="page-preview",
        manifest={"version": "1"},
        config_bundle={"app": {}},
        modules_data=[{"logical_path": "src/views/demo.vue", "content": "<template />"}],
    )
    await store.put_asset_blobs(
        artifact_id=artifact_id,
        assets={"hash": {"content": b"demo", "content_type": "text/plain"}},
    )

    assert await store.get_manifest(artifact_id) is not None
    assert await store.delete_artifact(artifact_id) == 5
    assert await store.get_manifest(artifact_id) is None
    assert await store.get_module(artifact_id, "src/views/demo.vue") is None
    assert await store.get_asset_blob(artifact_id, "hash") is None
    assert backend.stats().active_keys == 0


def test_memory_runtime_should_sweep_all_expired_keys() -> None:
    """未再次访问旧 key 时，全局 sweep 也必须释放已经过期的内存。"""

    now = 1_000.0
    backend = InMemoryRuntimeStateBackend(instance_name="test", clock=lambda: now)
    backend.set("artifact:a", "a", ex=1)
    backend.hset("artifact:b", {"value": "b"})
    backend.expire("artifact:b", 1)

    now = 1_002.0
    assert backend.purge_expired() == 2
    assert backend.stats().active_keys == 0
    assert backend.stats().sweep_count == 1