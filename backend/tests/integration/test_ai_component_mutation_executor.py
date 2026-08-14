"""文件功能：验证组件外部任务在慢校验释放会话后仍使用稳定字段完成最终写入。"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select

from app.ai.component_mutation_executor import AiComponentMutationExecutor
from app.ai.tools.shared import calculate_source_hash
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentRun, AiAgentSession
from app.models.ai_external_task import (
    AiAgentExternalBatch,
    AiAgentExternalTask,
    AiComponentMutationTask,
)
from app.models.user import User
from app.models.workspace_component import WorkspaceComponent
from app.services.code_check_service import CodeCheckService


async def test_component_edits_should_not_read_expired_task_after_runtime_check(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """Runtime检查结束后Task和旧组件均可能过期，最终复核必须使用预先保存的标量基线。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件外部任务会话释放", "status": "active"},
    )
    workspace_id = int(workspace_response.json()["id"])
    old_content = "<template><h1>旧标题</h1></template>"
    new_content = '<template><h1 class="leading-snug">新标题</h1></template>'
    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "会话释放测试组件",
            "import_name": "SessionReleaseProbe",
            "component_type": "内容组件",
            "content": old_content,
            "preview_schema": '{"props":{"height":{"type":"number","default":320}}}',
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200, component_response.text
    component_id = int(component_response.json()["id"])
    session_factory = get_session_factory()

    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        session.add(
            AiAgentSession(
                session_id="session-component-executor-expire",
                agent_id="agent-coordinator",
                user_id=user.id,
                workspace_id=workspace_id,
                focus_mode="follow_route",
                work_scope_mode="workspace",
                allowed_project_ids_json=[],
                metadata_json={},
            )
        )
        await session.flush()
        session.add(
            AiAgentRun(
                run_id="run-component-executor-expire",
                session_id="session-component-executor-expire",
                agent_id="agent-coordinator",
                user_id=user.id,
                status="waiting_external",
                scope_type="workspace",
                workspace_id=workspace_id,
                source="test",
                input_payload_json={"message": "更新组件"},
                message_history_json=[],
            )
        )
        await session.flush()
        session.add(
            AiAgentExternalBatch(
                batch_id="batch-component-executor-expire",
                run_id="run-component-executor-expire",
                session_id="session-component-executor-expire",
                sequence_no=1,
                status="waiting_tasks",
            )
        )
        await session.flush()
        session.add(
            AiAgentExternalTask(
                task_id="task-component-executor-expire",
                batch_id="batch-component-executor-expire",
                run_id="run-component-executor-expire",
                session_id="session-component-executor-expire",
                kind="component_mutation",
                tool_call_id="tool-component-executor-expire",
                deferred_tool_call_id="tool-component-executor-expire",
                status="running",
            )
        )
        await session.flush()
        session.add(
            AiComponentMutationTask(
                task_id="task-component-executor-expire",
                operation="apply_component_edits",
                workspace_id=workspace_id,
                component_id=component_id,
                base_draft_hash=calculate_source_hash(old_content),
                base_published_version_no=0,
                arguments_json={
                    "edits": [{"type": "rewrite_file", "content": new_content}],
                    "change_note": "验证会话释放后的最终写入",
                },
            )
        )
        session.add(
            AiAgentExternalTask(
                task_id="task-component-metadata-expire",
                batch_id="batch-component-executor-expire",
                run_id="run-component-executor-expire",
                session_id="session-component-executor-expire",
                kind="component_mutation",
                tool_call_id="tool-component-metadata-expire",
                deferred_tool_call_id="tool-component-metadata-expire",
                status="running",
            )
        )
        await session.flush()
        session.add(
            AiComponentMutationTask(
                task_id="task-component-metadata-expire",
                operation="update_component_metadata",
                workspace_id=workspace_id,
                component_id=component_id,
                arguments_json={
                    "preview_schema": {
                        "props": {"height": {"type": "number", "default": 360}}
                    },
                    "change_note": "验证元数据任务会话释放后的最终写入",
                },
            )
        )
        await session.commit()

    async def fake_check_component_code(self, **kwargs):
        _ = self, kwargs
        return {"success": True, "status": "passed", "diagnostics": []}

    monkeypatch.setattr(
        CodeCheckService, "check_component_code", fake_check_component_code
    )
    async with session_factory() as session:
        detail = await session.get(
            AiComponentMutationTask, "task-component-executor-expire"
        )
        assert detail is not None
        edit_result = await AiComponentMutationExecutor(session).execute(
            detail, operator_id=1
        )
        metadata_detail = await session.get(
            AiComponentMutationTask, "task-component-metadata-expire"
        )
        assert metadata_detail is not None
        metadata_result = await AiComponentMutationExecutor(session).execute(
            metadata_detail, operator_id=1
        )
        await session.commit()

    async with session_factory() as session:
        component = await session.get(WorkspaceComponent, component_id)

    assert edit_result["success"] is True
    assert edit_result["applied"] is True
    assert metadata_result["success"] is True
    assert metadata_result["applied"] is True
    assert component is not None
    assert component.content == new_content
    assert '"default":360' in str(component.preview_schema).replace(" ", "")
