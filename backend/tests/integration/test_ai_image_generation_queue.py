"""文件功能：验证图片生成任务幂等、租约执行以及附件与资源双重落库。"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select

from app.ai.image_generation_enqueue import enqueue_image_generation
from app.ai.image_generation_queue import _claim_one_job, _execute_job, _promote_due_provider_jobs
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.ai_agent_attachment import AiAgentImageAttachment
from app.models.ai_agent_runtime import AiAgentRun, AiAgentSession, AiAgentToolCall
from app.models.ai_image_generation import AiImageGenerationJob
from app.models.asset import WorkspaceAsset
from app.models.user import User
from app.services.agent_image_attachment_service import AgentImageAttachmentService
from app.services.image_generation.contracts import GeneratedImage, ImageProviderResult, ProviderTaskCursor

_ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000000020001e221bc330000000049454e44ae426082"
)


async def test_image_generation_job_should_be_idempotent_and_save_asset(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """同一工具调用只创建一个任务，成功结果同时成为工具附件和工作空间资源。"""

    provider = await authenticated_client.post(
        "/api/ai/llm-provider-configs",
        json={
            "name": "图片生成测试供应商",
            "provider_key": "openai_image",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-image-test",
        },
    )
    assert provider.status_code == 201
    model = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "图片生成测试模型",
            "provider_config_id": provider.json()["id"],
            "model_type": "image_generation",
            "model_id": "gpt-image-2",
            "advanced_config_json": {},
        },
    )
    assert model.status_code == 201
    binding = await authenticated_client.put(
        "/api/ai/llm-slots/image_generation",
        json={"llm_config_id": model.json()["id"]},
    )
    assert binding.status_code == 200
    workspace = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "图片生成任务工作空间", "status": "active"},
    )
    assert workspace.status_code == 200
    workspace_id = workspace.json()["id"]
    project = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "图片生成任务项目", "status": "active"},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        user_id = user.id
        session.add(
            AiAgentSession(
                session_id="session-image-generation-1",
                agent_id="agent-coordinator",
                user_id=user_id,
                scope_type="project",
                workspace_id=workspace_id,
                project_id=project_id,
                source="test",
                metadata_json={},
            )
        )
        await session.flush()
        session.add(
            AiAgentRun(
                run_id="run-image-generation-1",
                session_id="session-image-generation-1",
                agent_id="agent-coordinator",
                user_id=user_id,
                status="running",
                scope_type="project",
                workspace_id=workspace_id,
                project_id=project_id,
                source="test",
                input_payload_json={"message": "生成图片"},
                message_history_json=[],
            )
        )
        await session.flush()
        session.add(
            AiAgentToolCall(
                session_id="session-image-generation-1",
                run_id="run-image-generation-1",
                tool_call_id="tool-image-generation-1",
                tool_name="generate_image",
                status="running",
                input_payload_json={"operation": "generate"},
            )
        )
        await session.commit()

    request_payload = {
        "operation": "generate",
        "prompt": "极简蓝色圆形图标",
        "reference_attachment_ids": [],
        "mask_attachment_id": None,
        "aspect_ratio": "1:1",
        "resolution_tier": "standard",
        "quality": "low",
        "count": 1,
        "asset_name_prefix": "blue-orb",
        "description": "测试生成图片",
        "tags": ["generated"],
    }
    first = await enqueue_image_generation(
        session_factory,
        run_id="run-image-generation-1",
        session_id="session-image-generation-1",
        tool_call_id="tool-image-generation-1",
        user_id=user_id,
        workspace_id=workspace_id,
        project_id=project_id,
        request_payload=request_payload,
    )
    duplicate = await enqueue_image_generation(
        session_factory,
        run_id="run-image-generation-1",
        session_id="session-image-generation-1",
        tool_call_id="tool-image-generation-1",
        user_id=user_id,
        workspace_id=workspace_id,
        project_id=project_id,
        request_payload=request_payload,
    )
    assert duplicate == first

    class FakeAdapter:
        """返回确定性 PNG，避免测试访问真实图片供应商。"""

        async def submit(self, config, model, request):  # noqa: ANN001
            _ = model
            return ImageProviderResult(
                status="completed",
                images=[GeneratedImage(content=_ONE_PIXEL_PNG, content_type="image/png")],
            )

        async def resume(self, config, model, cursor):  # noqa: ANN001
            _ = (config, model, cursor)
            raise AssertionError("同步测试不应轮询")

    monkeypatch.setattr("app.ai.image_generation_queue.get_image_generation_adapter", lambda _config: FakeAdapter())
    database_id = await _claim_one_job(session_factory, worker_id="image-worker-test")
    assert database_id is not None
    await _execute_job(session_factory, database_id=database_id, worker_id="image-worker-test")

    async with session_factory() as session:
        jobs = list((await session.scalars(select(AiImageGenerationJob))).all())
        assert len(jobs) == 1
        assert jobs[0].status == "completed"
        assert jobs[0].result_json is not None
        assert jobs[0].deferred_tool_call_id == "tool-image-generation-1"
        assert jobs[0].member_run_id is None
        attachments = list(
            (await session.scalars(
                select(AiAgentImageAttachment).where(AiAgentImageAttachment.run_id == "run-image-generation-1")
            )).all()
        )
        assert len(attachments) == 1
        assert attachments[0].source_kind == "tool_output"
        assert attachments[0].promoted_asset_id is not None
        asset = await session.get(WorkspaceAsset, attachments[0].promoted_asset_id)
        assert asset is not None
        assert asset.name.startswith("blue-orb-")
        attachment_id = attachments[0].id

    async with session_factory() as session:
        await AgentImageAttachmentService(session, user_id=user_id).archive_attachment(
            workspace_id=workspace_id,
            session_id="session-image-generation-1",
            attachment_id=attachment_id,
            operator_id=user_id,
        )
        asset = await session.scalar(select(WorkspaceAsset).where(WorkspaceAsset.name.like("blue-orb-%")))
        assert asset is not None
        assert asset.status == "active"

    async with session_factory() as session:
        session.add(
            AiAgentToolCall(
                session_id="session-image-generation-1",
                run_id="run-image-generation-1",
                tool_call_id="tool-image-generation-async",
                tool_name="generate_image",
                status="running",
                input_payload_json={"operation": "generate"},
            )
        )
        await session.commit()
    await enqueue_image_generation(
        session_factory,
        run_id="run-image-generation-1",
        session_id="session-image-generation-1",
        tool_call_id="tool-image-generation-async",
        user_id=user_id,
        workspace_id=workspace_id,
        project_id=project_id,
        request_payload={**request_payload, "asset_name_prefix": "async-orb"},
    )

    class FakeAsyncAdapter:
        """模拟先提交、Worker 重启后再轮询完成的外部异步任务。"""

        submit_count = 0
        poll_count = 0

        async def submit(self, config, model, request):  # noqa: ANN001
            _ = (config, model, request)
            self.submit_count += 1
            return ImageProviderResult(
                status="waiting",
                cursor=ProviderTaskCursor(
                    task_id="dashscope-task-1",
                    status="PENDING",
                    request_id="request-1",
                    state={"region": "test"},
                    next_poll_after_seconds=2,
                    cancellable=True,
                ),
            )

        async def resume(self, config, model, cursor):  # noqa: ANN001
            _ = (config, model)
            self.poll_count += 1
            assert cursor.task_id == "dashscope-task-1"
            assert cursor.state == {"region": "test"}
            if self.poll_count == 1:
                raise AppException(
                    status_code=503,
                    code="AI_IMAGE_PROVIDER_THROTTLING",
                    detail="供应商限流。",
                    data={"retryable": True},
                )
            return ImageProviderResult(
                status="completed",
                images=[GeneratedImage(content=_ONE_PIXEL_PNG, content_type="image/png")],
                cursor=ProviderTaskCursor(task_id=cursor.task_id, status="SUCCEEDED", request_id=cursor.request_id),
            )

    async_adapter = FakeAsyncAdapter()
    monkeypatch.setattr("app.ai.image_generation_queue.get_image_generation_adapter", lambda _config: async_adapter)
    async_database_id = await _claim_one_job(session_factory, worker_id="image-worker-submit")
    assert async_database_id is not None
    await _execute_job(session_factory, database_id=async_database_id, worker_id="image-worker-submit")

    async with session_factory() as session:
        async_job = await session.get(AiImageGenerationJob, async_database_id)
        assert async_job is not None
        assert async_job.status == "waiting_provider"
        assert async_job.provider_task_id == "dashscope-task-1"
        assert async_job.provider_status == "PENDING"
        assert async_job.provider_state_json["region"] == "test"
        assert async_job.provider_state_json["cancellable"] is True
        assert async_job.next_poll_at is not None
        async_job.next_poll_at = utc_now()
        await session.commit()

    assert await _promote_due_provider_jobs(session_factory) == 1
    reclaimed_id = await _claim_one_job(session_factory, worker_id="image-worker-restarted")
    assert reclaimed_id == async_database_id
    await _execute_job(session_factory, database_id=reclaimed_id, worker_id="image-worker-restarted")
    assert async_adapter.submit_count == 1
    assert async_adapter.poll_count == 1

    async with session_factory() as session:
        async_job = await session.get(AiImageGenerationJob, async_database_id)
        assert async_job is not None
        assert async_job.status == "waiting_provider"
        assert async_job.provider_task_id == "dashscope-task-1"
        async_job.next_poll_at = utc_now()
        await session.commit()

    assert await _promote_due_provider_jobs(session_factory) == 1
    reclaimed_id = await _claim_one_job(session_factory, worker_id="image-worker-after-limit")
    assert reclaimed_id == async_database_id
    await _execute_job(session_factory, database_id=reclaimed_id, worker_id="image-worker-after-limit")
    assert async_adapter.submit_count == 1
    assert async_adapter.poll_count == 2

    async with session_factory() as session:
        async_job = await session.get(AiImageGenerationJob, async_database_id)
        assert async_job is not None
        assert async_job.status == "completed"
        assert async_job.provider_task_id == "dashscope-task-1"
        assert async_job.provider_status == "SUCCEEDED"

        session.add(
            AiAgentToolCall(
                session_id="session-image-generation-1",
                run_id="run-image-generation-1",
                tool_call_id="tool-image-generation-unknown",
                tool_name="generate_image",
                status="running",
                input_payload_json={"operation": "generate"},
            )
        )
        await session.commit()
    await enqueue_image_generation(
        session_factory,
        run_id="run-image-generation-1",
        session_id="session-image-generation-1",
        tool_call_id="tool-image-generation-unknown",
        user_id=user_id,
        workspace_id=workspace_id,
        project_id=project_id,
        request_payload={**request_payload, "asset_name_prefix": "unknown-submit"},
    )

    class UnknownSubmissionAdapter:
        """模拟供应商提交超时且无法确认任务是否创建。"""

        async def submit(self, config, model, request):  # noqa: ANN001
            _ = (config, model, request)
            raise AppException(
                status_code=503,
                code="AI_IMAGE_PROVIDER_SUBMISSION_UNKNOWN",
                detail="无法确认提交结果。",
            )

    monkeypatch.setattr("app.ai.image_generation_queue.get_image_generation_adapter", lambda _config: UnknownSubmissionAdapter())
    unknown_database_id = await _claim_one_job(session_factory, worker_id="image-worker-unknown")
    assert unknown_database_id is not None
    await _execute_job(session_factory, database_id=unknown_database_id, worker_id="image-worker-unknown")
    async with session_factory() as session:
        unknown_job = await session.get(AiImageGenerationJob, unknown_database_id)
        assert unknown_job is not None
        assert unknown_job.status == "error"
        assert unknown_job.error_code == "AI_IMAGE_PROVIDER_SUBMISSION_UNKNOWN"
