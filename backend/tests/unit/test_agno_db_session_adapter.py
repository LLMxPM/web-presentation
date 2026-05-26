"""文件功能：验证 Agno 会话写入适配器对运行历史中 dict 混入的兼容处理。"""

from __future__ import annotations

import pytest
from agno.run.agent import RunEvent, RunOutput
from agno.run.base import RunStatus
from agno.session.agent import AgentSession

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
