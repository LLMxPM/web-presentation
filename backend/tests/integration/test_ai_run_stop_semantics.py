"""文件功能：验证普通智能体 Run 的停机语义与用户可理解恢复路径所依赖的终态收敛。"""

from __future__ import annotations

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.ai.run_recovery import recover_interrupted_agent_runs_on_startup
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentRun, AiAgentRunEvent, AiAgentSession
from app.models.user import User


async def _seed_run(
    client: AsyncClient,
    *,
    suffix: str,
    status: str,
    cancel_requested: bool = False,
    process_owner: str | None = None,
) -> tuple[int, str, str]:
    """创建最小可恢复 Run，并返回 (workspace_id, session_id, run_id)。"""

    response = await client.post(
        "/api/workspaces",
        json={"name": f"停机语义-{suffix}", "status": "active"},
    )
    assert response.status_code == 200
    workspace_id = int(response.json()["id"])
    session_id = f"session-stop-{suffix}"
    run_id = f"run-stop-{suffix}"
    now = utc_now()
    async with get_session_factory()() as db:
        user = await db.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        db.add(AiAgentSession(
            session_id=session_id,
            agent_id="agent-coordinator",
            user_id=user.id,
            workspace_id=workspace_id,
            focus_mode="follow_route",
            work_scope_mode="workspace",
            allowed_project_ids_json=[],
            metadata_json={},
        ))
        await db.flush()
        db.add(AiAgentRun(
            run_id=run_id,
            session_id=session_id,
            agent_id="agent-coordinator",
            user_id=user.id,
            status=status,
            scope_type="workspace",
            workspace_id=workspace_id,
            source="test",
            input_payload_json={"message": f"停机语义测试-{suffix}"},
            message_history_json=[],
            cancel_requested_at=(now - timedelta(seconds=1)) if cancel_requested else None,
            started_at=now - timedelta(minutes=1),
            updated_at=now - timedelta(minutes=1),
            process_owner=process_owner,
        ))
        await db.commit()
    return workspace_id, session_id, run_id


async def _read_run(run_id: str) -> AiAgentRun:
    """读取 Run 持久化状态。"""

    async with get_session_factory()() as session:
        run = await session.get(AiAgentRun, run_id)
        assert run is not None
        return run


async def test_startup_recovery_should_fail_running_run_with_process_stopped(
    authenticated_client: AsyncClient,
) -> None:
    """进程退出遗留的 running Run 必须收敛为 AI_RUN_PROCESS_STOPPED。"""

    _, _, run_id = await _seed_run(authenticated_client, suffix="running", status="running")

    recovered = await recover_interrupted_agent_runs_on_startup(get_session_factory())
    assert recovered == 1

    run = await _read_run(run_id)
    assert run.status == "failed"
    assert run.error_code == "AI_RUN_PROCESS_STOPPED"
    assert run.finished_at is not None
    assert "无法继续执行" in (run.error_message or "")


async def test_startup_recovery_should_cancel_cancelling_run(
    authenticated_client: AsyncClient,
) -> None:
    """用户已请求取消的 Run 在停机恢复后应写入 cancelled 而不是 AI_RUN_PROCESS_STOPPED。"""

    _, _, run_id = await _seed_run(
        authenticated_client,
        suffix="cancelling",
        status="cancelling",
        cancel_requested=True,
    )

    recovered = await recover_interrupted_agent_runs_on_startup(get_session_factory())
    assert recovered == 1

    run = await _read_run(run_id)
    assert run.status == "cancelled"
    assert run.error_code is None
    assert run.finished_at is not None


async def test_startup_recovery_should_fail_pending_run(
    authenticated_client: AsyncClient,
) -> None:
    """尚未开始执行的 pending Run 同样按 AI_RUN_PROCESS_STOPPED 收敛。"""

    _, _, run_id = await _seed_run(authenticated_client, suffix="pending", status="pending")

    recovered = await recover_interrupted_agent_runs_on_startup(get_session_factory())
    assert recovered == 1

    run = await _read_run(run_id)
    assert run.status == "failed"
    assert run.error_code == "AI_RUN_PROCESS_STOPPED"


async def test_startup_recovery_should_leave_parked_and_terminal_runs_untouched(
    authenticated_client: AsyncClient,
) -> None:
    """paused / waiting_external 与已终态 Run 不属于停机收敛范围。"""

    _, _, paused_id = await _seed_run(authenticated_client, suffix="paused", status="paused")
    _, _, waiting_id = await _seed_run(
        authenticated_client,
        suffix="waiting",
        status="waiting_external",
    )

    recovered = await recover_interrupted_agent_runs_on_startup(get_session_factory())
    assert recovered == 0

    paused = await _read_run(paused_id)
    waiting = await _read_run(waiting_id)
    assert paused.status == "paused"
    assert waiting.status == "waiting_external"


async def test_startup_recovery_should_be_idempotent(
    authenticated_client: AsyncClient,
) -> None:
    """重复执行启动恢复不得再次改写已收敛 Run，也不得产生重复终态事件。"""

    _, _, run_id = await _seed_run(authenticated_client, suffix="idempotent", status="running")

    assert await recover_interrupted_agent_runs_on_startup(get_session_factory()) == 1
    assert await recover_interrupted_agent_runs_on_startup(get_session_factory()) == 0

    run = await _read_run(run_id)
    assert run.status == "failed"
    assert run.error_code == "AI_RUN_PROCESS_STOPPED"

    async with get_session_factory()() as session:
        events = list(
            (
                await session.scalars(
                    select(AiAgentRunEvent).where(AiAgentRunEvent.run_id == run_id)
                )
            ).all()
        )
    terminal_events = [event for event in events if event.event == "run.error"]
    assert len(terminal_events) == 1
    assert terminal_events[0].payload_json.get("data", {}).get("code") == "AI_RUN_PROCESS_STOPPED"


async def test_startup_recovery_should_skip_other_replica_active_run(
    authenticated_client: AsyncClient,
) -> None:
    """其它副本（其它主机）正在执行的 Run 不得被本副本启动恢复误杀。"""

    _, _, run_id = await _seed_run(
        authenticated_client,
        suffix="other-replica",
        status="running",
        process_owner="other-replica-host:99999:deadbeef",
    )

    recovered = await recover_interrupted_agent_runs_on_startup(
        get_session_factory(),
        include_unowned=False,
    )
    assert recovered == 0

    run = await _read_run(run_id)
    assert run.status == "running"
    assert run.error_code is None


async def test_startup_recovery_should_skip_unowned_when_multi_instance(
    authenticated_client: AsyncClient,
) -> None:
    """多副本语义下无主遗留不被全局收敛，避免滚动升级误杀。"""

    _, _, run_id = await _seed_run(
        authenticated_client,
        suffix="unowned-multi",
        status="running",
    )

    recovered = await recover_interrupted_agent_runs_on_startup(
        get_session_factory(),
        include_unowned=False,
    )
    assert recovered == 0

    run = await _read_run(run_id)
    assert run.status == "running"


async def test_startup_recovery_should_recover_dead_local_process_owner(
    authenticated_client: AsyncClient,
) -> None:
    """本机已死进程遗留的 Run 应被收敛为 AI_RUN_PROCESS_STOPPED。"""

    dead_pid = 2**22 + 22222
    _, _, run_id = await _seed_run(
        authenticated_client,
        suffix="dead-local",
        status="running",
        process_owner=f"local-test-host:{dead_pid}:cafebabe",
    )

    recovered = await recover_interrupted_agent_runs_on_startup(
        get_session_factory(),
        include_unowned=False,
        local_hostname="local-test-host",
    )
    assert recovered == 1

    run = await _read_run(run_id)
    assert run.status == "failed"
    assert run.error_code == "AI_RUN_PROCESS_STOPPED"
