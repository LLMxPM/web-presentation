"""文件功能：验证 Agno 会话写入适配器对运行历史中 dict 混入的兼容处理。"""

from __future__ import annotations

from agno.media import Image
from agno.models.response import ToolExecution
import pytest
from agno.run.agent import RunEvent, RunOutput
from agno.run.base import RunStatus
from agno.run.team import TeamRunOutput, ToolCallCompletedEvent
from agno.session.agent import AgentSession
from agno.session.summary import SessionSummary
from agno.session.team import TeamSession

from app.ai.db import AgnoDbSessionWriteAdapter


class _RecordingAgnoDb:
    """记录适配器传入的 session，并模拟 Agno DB 写入前的 to_dict 序列化。"""

    def __init__(self) -> None:
        """初始化最后一次写入 payload。"""

        self.last_payload: dict | None = None

    def upsert_session(self, session, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        """模拟 Agno DB：写入前必须先成功序列化 session。"""

        _ = args, kwargs
        self.last_payload = session.to_dict()
        return session

    def upsert_sessions(self, sessions, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        """模拟 Agno DB 的批量写入接口。"""

        _ = args, kwargs
        return [self.upsert_session(session) for session in sessions]


def test_adapter_should_restore_dict_run_before_upsert() -> None:
    """runs 中混入 dict 时，适配器应还原为 RunOutput 后再写入。"""

    run_payload = RunOutput(
        run_id="run-1",
        session_id="session-1",
        agent_id="resource-manager",
        status=RunStatus.completed,
        content="已创建图标。",
    ).to_dict()
    session = AgentSession(
        session_id="session-1",
        agent_id="resource-manager",
        user_id="1",
        runs=[run_payload],  # type: ignore[list-item]
    )
    with pytest.raises(AttributeError):
        session.to_dict()

    db = _RecordingAgnoDb()
    AgnoDbSessionWriteAdapter(db).upsert_session(session)  # type: ignore[arg-type]

    assert db.last_payload is not None
    assert db.last_payload["runs"][0]["run_id"] == "run-1"
    assert db.last_payload["runs"][0]["status"] == "COMPLETED"


def test_adapter_should_restore_dict_event_before_upsert() -> None:
    """events 中混入 dict 时，适配器应还原为 Agno 事件对象后再写入。"""

    session = AgentSession(
        session_id="session-1",
        agent_id="resource-manager",
        user_id="1",
        runs=[
            RunOutput(
                run_id="run-1",
                session_id="session-1",
                agent_id="resource-manager",
                status=RunStatus.completed,
                events=[
                    {
                        "event": RunEvent.run_started.value,
                        "run_id": "run-1",
                        "session_id": "session-1",
                        "agent_id": "resource-manager",
                    }
                ],  # type: ignore[list-item]
            )
        ],
    )
    with pytest.raises(AttributeError):
        session.to_dict()

    db = _RecordingAgnoDb()
    AgnoDbSessionWriteAdapter(db).upsert_session(session)  # type: ignore[arg-type]

    assert db.last_payload is not None
    assert db.last_payload["runs"][0]["events"][0]["event"] == RunEvent.run_started.value


def test_adapter_should_restore_dict_session_summary_before_upsert() -> None:
    """summary 中混入 dict 时，适配器应还原为 SessionSummary 后再写入。"""

    summary_payload = SessionSummary(summary="用户正在制作封面页。", topics=["封面"]).to_dict()
    session = AgentSession(
        session_id="session-1",
        agent_id="resource-manager",
        user_id="1",
        summary=summary_payload,  # type: ignore[arg-type]
    )
    with pytest.raises(AttributeError):
        session.to_dict()

    db = _RecordingAgnoDb()
    AgnoDbSessionWriteAdapter(db).upsert_session(session)  # type: ignore[arg-type]

    assert db.last_payload is not None
    assert db.last_payload["summary"]["summary"] == "用户正在制作封面页。"


def test_adapter_should_compact_event_media_before_upsert() -> None:
    """事件图片只保留轻量引用，避免 base64 内容随每个事件重复写入。"""

    session = TeamSession(
        session_id="session-1",
        team_id="agent-coordinator",
        user_id="1",
        runs=[
            TeamRunOutput(
                run_id="run-1",
                session_id="session-1",
                team_id="agent-coordinator",
                status=RunStatus.completed,
                events=[
                    ToolCallCompletedEvent(
                        run_id="run-1",
                        session_id="session-1",
                        team_id="agent-coordinator",
                        tool=ToolExecution(tool_name="get_page_screenshot", tool_call_id="tool-1"),
                        images=[
                            Image(
                                id="image-1",
                                mime_type="image/png",
                                detail="auto",
                                content="x" * 200_000,
                            ),
                            {
                                "id": "image-2",
                                "mime_type": "image/png",
                                "url": f"data:image/png;base64,{'x' * 5_000}",
                            },
                        ],
                    )
                ],
            )
        ],
    )

    db = _RecordingAgnoDb()
    AgnoDbSessionWriteAdapter(db).upsert_session(session)  # type: ignore[arg-type]

    assert db.last_payload is not None
    image_payload = db.last_payload["runs"][0]["events"][0]["images"][0]
    assert image_payload["id"] == "image-1"
    assert image_payload["mime_type"] == "image/png"
    assert image_payload["detail"] == "auto"
    assert len(image_payload["content"]) < 128
    data_url_payload = db.last_payload["runs"][0]["events"][0]["images"][1]
    assert data_url_payload["id"] == "image-2"
    assert "url" not in data_url_payload
    assert len(data_url_payload["content"]) < 128


def test_adapter_should_compact_large_tool_payload_before_upsert() -> None:
    """事件工具参数和结果过大时，应落库为预览摘要而不是完整大对象。"""

    session = TeamSession(
        session_id="session-1",
        team_id="agent-coordinator",
        user_id="1",
        runs=[
            TeamRunOutput(
                run_id="run-1",
                session_id="session-1",
                team_id="agent-coordinator",
                status=RunStatus.completed,
                events=[
                    ToolCallCompletedEvent(
                        run_id="run-1",
                        session_id="session-1",
                        team_id="agent-coordinator",
                        tool=ToolExecution(
                            tool_name="get_page_content",
                            tool_call_id="tool-1",
                            tool_args={"source": "a" * 80_000},
                            result="b" * 80_000,
                        ),
                    )
                ],
            )
        ],
    )

    db = _RecordingAgnoDb()
    AgnoDbSessionWriteAdapter(db).upsert_session(session)  # type: ignore[arg-type]

    assert db.last_payload is not None
    tool_payload = db.last_payload["runs"][0]["events"][0]["tool"]
    assert tool_payload["tool_name"] == "get_page_content"
    assert tool_payload["tool_call_id"] == "tool-1"
    assert tool_payload["tool_args"]["storage_compacted"] is True
    assert "source" in tool_payload["tool_args"]["preview"]
    assert "已截断" in tool_payload["result"]
