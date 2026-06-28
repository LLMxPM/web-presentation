"""文件功能：验证 AI run 诊断脚本的只读收集逻辑与摘要输出。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from httpx import AsyncClient

from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentSession
from app.schemas.agent import AgentPendingRequirement, AgentRunEvent, AgentScopeContext
from app.scripts.diagnose_ai_run import (
    async_main,
    collect_ai_run_diagnostics,
    collect_ai_session_diagnostics,
    format_ai_run_diagnostics_summary,
    format_ai_session_diagnostics_summary,
    load_backend_env_for_cli,
)


async def test_ai_run_diagnostics_should_collect_runtime_state(
    authenticated_client: AsyncClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """诊断函数应支持 run/session 收集，并能通过 CLI 写入文件。"""

    from app.core.config import get_settings

    monkeypatch.setenv("SESSION_COOKIE_NAME", get_settings().session_cookie_name)
    monkeypatch.setenv("SESSION_SECURE", str(get_settings().session_secure).lower())

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "AI 诊断工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    llm_config_id = await _create_diagnostics_llm_config(authenticated_client)
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "component-manager",
            "session_name": "AI 诊断会话",
            "scope": scope.model_dump(mode="json"),
            "llm_config_id": llm_config_id,
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="diagnostics-run-1",
            message="需要诊断",
            image_attachment_ids=[],
        )
        run_model = run_start.run_model
        await store.append_event(
            run_model,
            AgentRunEvent(
                event="reasoning.delta",
                run_id=run_model.run_id,
                session_id=session_id,
                content="先检查上下文。",
            ),
        )
        await store.append_event(
            run_model,
            AgentRunEvent(
                event="tool.started",
                run_id=run_model.run_id,
                session_id=session_id,
                data={
                    "tool_name": "ask_user",
                    "tool_call_id": "tool-ask-diagnostics",
                    "tool_args": {
                        "questions": [
                            {
                                "question": "采用哪种处理方式？",
                                "options": [{"label": "继续"}],
                            }
                        ]
                    },
                },
            ),
        )
        requirement = AgentPendingRequirement(
            id="req-diagnostics",
            kind="user_feedback",
            run_id=run_model.run_id,
            session_id=session_id,
            tool_name="ask_user",
            tool_execution={
                "tool_name": "ask_user",
                "tool_call_id": "tool-ask-diagnostics",
                "tool_args": {
                    "questions": [
                        {
                            "question": "采用哪种处理方式？",
                            "options": [{"label": "继续"}],
                        }
                    ]
                },
            },
            user_feedback_schema=[
                {
                    "question": "采用哪种处理方式？",
                    "options": [{"label": "继续"}],
                    "multi_select": False,
                }
            ],
        )
        await store.pause_for_requirement(run_model, requirement=requirement)
        pending_requirement = await store.get_pending_requirement(run_id=run_model.run_id)
        assert pending_requirement is not None
        await store.resolve_requirement(
            pending_requirement,
            payload={"feedback_selections": [{"question": "采用哪种处理方式？", "selected_label": "继续"}]},
        )
        run_model.status = "running"
        run_model.pending_requirement_json = None
        await store.append_event(
            run_model,
            AgentRunEvent(
                event="tool.completed",
                run_id=run_model.run_id,
                session_id=session_id,
                data={
                    "tool_name": "ask_user",
                    "tool_call_id": "tool-ask-diagnostics",
                    "result": 'User feedback received: [{"question": "采用哪种处理方式？", "selected": ["继续"]}]',
                },
            ),
        )
        await store.append_assistant_message(
            run_model,
            content="诊断完成。",
            reasoning_content="先检查上下文。",
            message_history=[
                {"kind": "request", "parts": [{"part_kind": "user-prompt"}]},
                {"kind": "response", "parts": [{"part_kind": "text"}]},
            ],
        )
        await store.mark_terminal(run_model, status="completed", content="诊断完成。")
        session_model = await db_session.get(AiAgentSession, session_id)
        assert session_model is not None
        session_model.summary_json = {
            "kind": "agent-message-history-summary.v1",
            "summary": "诊断会话的压缩摘要。",
            "covered_until_run_id": run_model.run_id,
            "covered_until_created_at": run_model.created_at.isoformat(),
            "source_run_ids": [run_model.run_id],
        }
        await db_session.commit()
        await db_session.refresh(session_model)

        payload = await collect_ai_run_diagnostics(db_session, run_model.run_id)
        session_payload = await collect_ai_session_diagnostics(db_session, session_id)

    assert payload is not None
    assert payload["run"]["status"] == "completed"
    assert [item["event"] for item in payload["events"]] == [
        "run.started",
        "reasoning.delta",
        "tool.started",
        "run.paused",
        "tool.completed",
        "run.completed",
    ]
    assert len(payload["tool_calls"]) == 1
    tool_call = payload["tool_calls"][0]
    assert tool_call["tool_call_id"] == "tool-ask-diagnostics"
    assert tool_call["tool_name"] == "ask_user"
    assert tool_call["status"] == "completed"
    assert payload["requirements"][0]["status"] == "resolved"
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][1]["role"] == "assistant"
    assert payload["message_history_summary"] == {
        "count": 2,
        "kinds": ["request", "response"],
        "part_kinds": ["user-prompt", "text"],
    }
    summary = format_ai_run_diagnostics_summary(payload)
    assert "AI run: diagnostics-run-1" in summary
    assert "Tool calls (1):" in summary
    assert "Requirements (1):" in summary
    assert session_payload is not None
    assert session_payload["session"]["session_id"] == session_id
    assert session_payload["session"]["summary"]["covered_until_run_id"] == "diagnostics-run-1"
    assert [item["run"]["run_id"] for item in session_payload["runs"]] == ["diagnostics-run-1"]
    session_summary = format_ai_session_diagnostics_summary(session_payload)
    assert f"AI session: {session_id}" in session_summary
    assert "compression_checkpoint: agent-message-history-summary.v1 covered_until_run_id=diagnostics-run-1" in session_summary
    assert "Runs (1):" in session_summary

    output_path = tmp_path / "diagnostics" / "session.json"
    exit_code = await async_main([
        "--session-id",
        session_id,
        "--format",
        "json",
        "--output",
        str(output_path),
    ])
    assert exit_code == 0
    output_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert output_payload["session"]["session_id"] == session_id
    assert output_payload["runs"][0]["run"]["run_id"] == "diagnostics-run-1"


async def _create_diagnostics_llm_config(authenticated_client: AsyncClient) -> int:
    """创建诊断测试会话使用的显式模型配置。"""

    provider_response = await authenticated_client.post(
        "/api/ai/llm-provider-configs",
        json={
            "name": "诊断测试供应商",
            "provider_key": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-diagnostics",
        },
    )
    assert provider_response.status_code == 201
    provider_id = provider_response.json()["id"]

    response = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "诊断测试模型",
            "provider_config_id": provider_id,
            "model_id": "gpt-4.1-mini",
            "advanced_config_json": {},
        },
    )
    assert response.status_code == 201
    return int(response.json()["id"])


async def test_ai_run_diagnostics_should_return_none_when_run_missing(
    authenticated_client: AsyncClient,
) -> None:
    """run 不存在时核心收集函数应返回 None，CLI 可据此退出非 0。"""

    _ = authenticated_client
    async with get_session_factory()() as db_session:
        payload = await collect_ai_run_diagnostics(db_session, "missing-run")

    assert payload is None


def test_ai_run_diagnostics_cli_should_load_env_without_overriding(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """CLI 从根仓运行时应能补读 backend/.env，但不覆盖已有环境变量。"""

    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join([
            "# comment",
            "DATABASE_URL=postgresql+asyncpg://file:file@127.0.0.1:5432/file_db",
            "export DIAGNOSE_AI_RUN_TEST_VALUE=\"from-file\"",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///already-set.db")
    monkeypatch.delenv("DIAGNOSE_AI_RUN_TEST_VALUE", raising=False)

    loaded_path = load_backend_env_for_cli(env_path)

    assert loaded_path == env_path
    assert os.environ["DATABASE_URL"] == "sqlite+aiosqlite:///already-set.db"
    assert os.environ["DIAGNOSE_AI_RUN_TEST_VALUE"] == "from-file"
