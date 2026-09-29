"""文件功能：构造关联完整的非空队列样本，保留真实表约束用于聚合指标对账。"""

from datetime import datetime, timedelta

from app.models.ai_agent_runtime import AiAgentRun, AiAgentSession
from app.models.ai_external_task import AiAgentExternalBatch, AiAgentExternalTask
from app.models.ai_image_generation import AiImageGenerationJob
from app.models.ai_image_model import AiImageModelConfig, AiImageProviderConfig
from app.models.render_attempt import RenderAttempt
from app.models.render_request import RenderRequest
from app.models.workspace import Workspace
from sqlalchemy.ext.asyncio import AsyncSession


async def seed_metrics(session: AsyncSession, now: datetime) -> None:
    """覆盖领域、投影、续跑与执行槽位；过期、缺租约和供应商等待均单独留样本。"""
    old = now - timedelta(seconds=90)
    expired = now - timedelta(seconds=10)
    future = now + timedelta(seconds=10)
    workspace = Workspace(code="metrics", name="指标测试")
    provider = AiImageProviderConfig(
        name="指标供应商", provider_key="openai_image", user_id=1
    )
    session.add_all([workspace, provider])
    await session.flush()
    model = AiImageModelConfig(
        name="指标模型", provider_config_id=provider.id, model_id="test"
    )
    session.add(model)
    session.add(
        AiAgentSession(
            session_id="metrics-session",
            agent_id="agent-coordinator",
            user_id=1,
            workspace_id=workspace.id,
        )
    )
    await session.flush()
    session.add(
        AiAgentRun(
            run_id="metrics-run",
            session_id="metrics-session",
            agent_id="agent-coordinator",
            user_id=1,
            status="waiting_external",
            scope_type="workspace",
            workspace_id=workspace.id,
            source="test",
        )
    )
    await session.flush()
    for number, status in enumerate(["ready", "resuming"]):
        session.add(
            AiAgentExternalBatch(
                batch_id=f"metrics-{number}",
                run_id="metrics-run",
                session_id="metrics-session",
                sequence_no=number,
                status=status,
                lease_expires_at=expired,
                created_at=old,
            )
        )
    await session.flush()
    image_cases = [
        ("pending", None, None),
        ("running", expired, None),
        ("running", None, None),
        ("waiting_provider", None, expired),
        ("waiting_provider", None, future),
        ("waiting_provider", None, None),
        ("succeeded", expired, None),
    ]
    for number, (status, lease, poll) in enumerate(image_cases):
        session.add(
            AiImageGenerationJob(
                job_id=f"image-{number}",
                run_id="metrics-run",
                session_id="metrics-session",
                tool_call_id=f"image-call-{number}",
                deferred_tool_call_id=f"image-call-{number}",
                user_id=1,
                workspace_id=workspace.id,
                model_config_id=model.id,
                operation="generate",
                status=status,
                lease_expires_at=lease,
                next_poll_at=poll,
                created_at=old,
            )
        )
        session.add(
            AiAgentExternalTask(
                task_id=f"image-task-{number}",
                batch_id="metrics-0",
                run_id="metrics-run",
                session_id="metrics-session",
                kind="image_generation",
                tool_call_id=f"image-call-{number}",
                deferred_tool_call_id=f"image-call-{number}",
                status=status,
                lease_expires_at=lease,
                created_at=old,
            )
        )
    for status in ["pending", "running"]:
        session.add(
            AiAgentExternalTask(
                task_id=f"component-{status}",
                batch_id="metrics-0",
                run_id="metrics-run",
                session_id="metrics-session",
                kind="component_mutation",
                tool_call_id=f"component-{status}",
                deferred_tool_call_id=f"component-{status}",
                status=status,
                created_at=old,
            )
        )
    for number, status in enumerate(["queued", "retry_wait", "executing", "succeeded"]):
        request = RenderRequest(
            request_key=f"request-{number}",
            logical_owner_key=f"owner-{number}",
            business_stage="screenshot",
            operation="page_screenshot",
            workspace_id=workspace.id,
            status=status,
            input_digest="input",
            render_digest="render",
            request_digest="request",
            render_profile_digest="profile",
            trace_id="trace",
            deadline_at=future,
            created_at=old,
        )
        session.add(request)
        await session.flush()
        # 不占槽的终态租约不能被算入活跃执行统计。
        session.add(
            RenderAttempt(
                attempt_uid=f"attempt-{number}",
                request_id=request.id,
                attempt_no=1,
                status="running" if number < 3 else "succeeded",
                active_occupancy=1 if number < 3 else 0,
                reserved_at=old,
                lease_expires_at=[expired, future, None, expired][number],
            )
        )
    await session.commit()
