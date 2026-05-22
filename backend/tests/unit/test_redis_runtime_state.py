"""文件功能：验证 Redis 运行态客户端、Agent run store 与 Runtime artifact store。"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.schemas.agent import AgentRunEvent, AgentScopeContext
from app.services.ai_run_state_store import AiRunStateStore
from app.services.redis_runtime_client import get_redis_runtime_client, reset_redis_runtime_client
from app.services.runtime_artifact_store import RuntimeArtifactStore


@pytest.fixture(autouse=True)
def redis_memory_runtime(monkeypatch: pytest.MonkeyPatch):
    """为运行态单测提供隔离的内存 Redis。"""

    monkeypatch.setenv("REDIS_URL", "memory://unit")
    monkeypatch.setenv("REDIS_KEY_PREFIX", "unit_runtime")
    get_settings.cache_clear()
    reset_redis_runtime_client()
    yield
    reset_redis_runtime_client()
    get_settings.cache_clear()


def test_redis_runtime_client_should_encode_json_and_prefix_keys() -> None:
    """Redis 客户端应统一前缀和 JSON 编解码。"""

    runtime = get_redis_runtime_client()
    assert runtime.key("ai:run:1") == "unit_runtime:ai:run:1"
    payload = {"中文": "可读", "items": [1, 2]}
    assert runtime.loads(runtime.dumps(payload)) == payload


async def test_ai_run_state_store_should_lock_session_and_replay_events() -> None:
    """Agent run store 应抢占 active_run，并按 sequence 回放事件。"""

    scope = AgentScopeContext(scope_type="page", workspace_id=1, project_id=2, page_id=3)
    store = AiRunStateStore()
    record = await store.create_run(
        run_id="run-1",
        session_id="session-1",
        agent_id="agent-1",
        user_id=7,
        backend_session_id="backend-session",
        scope=scope,
        input_summary="hello",
        input_payload_json={"message": "hello"},
        tool_scopes=["page:read"],
    )

    assert record.status == "pending"
    with pytest.raises(AppException) as exc_info:
        await store.create_run(
            run_id="run-2",
            session_id="session-1",
            agent_id="agent-1",
            user_id=7,
            backend_session_id="backend-session",
            scope=scope,
            input_summary="blocked",
            input_payload_json=None,
            tool_scopes=[],
        )
    assert exc_info.value.code == "AI_SESSION_RUN_ACTIVE"

    await store.append_event(
        run_id="run-1",
        user_id=7,
        event=AgentRunEvent(event="run.started", content="start"),
    )
    await store.append_event(
        run_id="run-1",
        user_id=7,
        event=AgentRunEvent(event="message.delta", content="你好"),
    )
    events = await store.list_events_after(run_id="run-1", user_id=7, after_sequence=1)

    assert [event.sequence for event in events] == [2]
    assert events[0].content == "你好"


async def test_ai_run_state_store_should_release_active_lock_on_terminal() -> None:
    """Agent run 进入终态后应释放 session active_run 互斥。"""

    scope = AgentScopeContext(scope_type="project", workspace_id=1, project_id=2)
    store = AiRunStateStore()
    record = await store.create_run(
        run_id="run-terminal",
        session_id="session-terminal",
        agent_id="agent-1",
        user_id=7,
        backend_session_id=None,
        scope=scope,
        input_summary=None,
        input_payload_json=None,
        tool_scopes=[],
    )
    await store.mark_terminal(record=record, status="completed", content="done")

    assert await store.get_latest_active_run(session_id="session-terminal", agent_id="agent-1", user_id=7) is None
    replacement = await store.create_run(
        run_id="run-terminal-2",
        session_id="session-terminal",
        agent_id="agent-1",
        user_id=7,
        backend_session_id=None,
        scope=scope,
        input_summary=None,
        input_payload_json=None,
        tool_scopes=[],
    )
    assert replacement.run_id == "run-terminal-2"


async def test_runtime_artifact_store_should_store_manifest_config_and_modules() -> None:
    """Runtime artifact store 应保存 manifest、配置包和源码模块。"""

    store = RuntimeArtifactStore()
    artifact_id = await store.put_artifact(
        tenant_id="tenant_1",
        workspace_id=1,
        project_id=2,
        artifact_kind="preview_artifact",
        manifest={
            "artifact_kind": "preview_artifact",
            "tenant_id": "tenant_1",
            "preview_kind": "project",
            "modules": {"src/App.vue": {"content_hash": "hash"}},
        },
        config_bundle={"app": {"title": "Demo"}},
        modules_data=[{"logical_path": "src/App.vue", "content": "<template>Demo</template>"}],
    )

    assert artifact_id.startswith("rt_")
    assert (await store.get_manifest(artifact_id))["artifact_id"] == artifact_id
    assert await store.get_config_bundle(artifact_id) == {"app": {"title": "Demo"}}
    assert await store.get_module(artifact_id, "src/App.vue") == "<template>Demo</template>"
