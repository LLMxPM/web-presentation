"""文件功能：根据现有应用配置构建 Agno 所需的会话与审批数据库，并修正会话写回前的序列化结构。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from agno.db.postgres import PostgresDb
from agno.db.sqlite import SqliteDb
from agno.models.message import Message
from agno.models.response import ToolExecution
from agno.run.agent import RunInput, RunOutput, run_output_event_from_dict
from agno.run.requirement import RunRequirement
from agno.run.team import TeamRunInput, TeamRunOutput, team_run_output_event_from_dict
from agno.run.workflow import WorkflowRunOutput
from agno.session.agent import AgentSession
from agno.session.team import TeamSession
from agno.session.workflow import WorkflowSession
from sqlalchemy.engine import make_url

from app.core.config import get_settings


class AgnoDbSessionWriteAdapter:
    """代理 Agno DB，并在写 session 前兼容 Agno 运行态中偶发的 dict 混入。"""

    def __init__(self, inner: PostgresDb | SqliteDb) -> None:
        """保存真实 Agno DB；未覆盖的方法全部透传给内部对象。"""

        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        """把 get_session、rename_session 等能力透传给真实 DB。"""

        return getattr(self._inner, name)

    def upsert_session(self, session: Any, *args: Any, **kwargs: Any) -> Any:
        """写入单个 Agno session 前，先修正 runs/events/messages 的对象形态。"""

        return self._inner.upsert_session(_normalize_agno_session_for_upsert(session), *args, **kwargs)

    def upsert_sessions(self, sessions: list[Any], *args: Any, **kwargs: Any) -> Any:
        """批量写入 session 时复用同一套规范化逻辑。"""

        return self._inner.upsert_sessions([_normalize_agno_session_for_upsert(item) for item in sessions], *args, **kwargs)


def build_agno_db() -> AgnoDbSessionWriteAdapter:
    """按主应用数据库配置派生 Agno 会话库，兼容 PostgreSQL 与 SQLite。"""

    settings = get_settings()
    raw_database_url = (settings.ai_db_url or settings.database_url).strip()

    if raw_database_url.startswith("sqlite"):
        return AgnoDbSessionWriteAdapter(_build_sqlite_db(raw_database_url))
    return AgnoDbSessionWriteAdapter(_build_postgres_db(raw_database_url))


def _build_sqlite_db(database_url: str) -> SqliteDb:
    """把主库 SQLite 配置转换为 Agno 独立文件库，避免与业务事务抢占连接。"""

    url = make_url(database_url)
    database_path = Path(url.database or "agno.db")
    agno_database_path = database_path.with_suffix(".agno.db")
    agno_database_path.parent.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    return SqliteDb(
        db_file=str(agno_database_path),
        session_table=settings.ai_session_table,
        approvals_table=settings.ai_approvals_table,
    )


def _build_postgres_db(database_url: str) -> PostgresDb:
    """把 asyncpg/标准 PostgreSQL URL 统一转换为 psycopg 驱动，供 Agno 同步使用。"""

    settings = get_settings()
    resolved_url = database_url
    if resolved_url.startswith("postgresql+asyncpg://"):
        resolved_url = resolved_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    elif resolved_url.startswith("postgresql://"):
        resolved_url = resolved_url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif resolved_url.startswith("postgres://"):
        resolved_url = resolved_url.replace("postgres://", "postgresql+psycopg://", 1)

    return PostgresDb(
        db_url=resolved_url,
        db_schema=settings.ai_db_schema,
        session_table=settings.ai_session_table,
        approvals_table=settings.ai_approvals_table,
    )


def _normalize_agno_session_for_upsert(session: Any) -> Any:
    """把 Agno session 中需要 to_dict/model_dump 的 dict 值还原为对象。"""

    if not isinstance(session, (AgentSession, TeamSession, WorkflowSession)):
        return session
    runs = getattr(session, "runs", None)
    if isinstance(runs, list):
        session.runs = [_normalize_agno_run_for_upsert(run) for run in runs]
    return session


def _normalize_agno_run_for_upsert(run: Any) -> Any:
    """修正单个 Agno run，避免 session.to_dict 因嵌套 dict 缺少 to_dict 失败。"""

    if isinstance(run, dict):
        return _run_from_dict(run)
    _normalize_run_common_fields(run)
    if isinstance(run, TeamRunOutput):
        run.member_responses = [_normalize_agno_run_for_upsert(item) for item in run.member_responses or []]
    return run


def _normalize_run_common_fields(run: Any) -> None:
    """修正 RunOutput 与 TeamRunOutput 共享的易混入 dict 的字段。"""

    _normalize_sequence_attr(run, "messages", _message_from_dict)
    _normalize_sequence_attr(run, "additional_input", _message_from_dict)
    _normalize_sequence_attr(run, "reasoning_messages", _message_from_dict)
    _normalize_sequence_attr(run, "events", _event_from_dict)
    _normalize_sequence_attr(run, "tools", _tool_execution_from_dict)
    _normalize_sequence_attr(run, "requirements", _requirement_from_dict)
    _normalize_input_attr(run)


def _normalize_sequence_attr(target: Any, attr: str, factory: Callable[[dict[str, Any]], Any]) -> None:
    """把列表字段中的 dict 项按指定工厂还原；无法识别时保留可序列化包装。"""

    values = getattr(target, attr, None)
    if not isinstance(values, list):
        return
    normalized = [factory(item) if isinstance(item, dict) else item for item in values]
    setattr(target, attr, normalized)


def _normalize_input_attr(run: Any) -> None:
    """修正 run.input；Agno 写回时会直接调用 input.to_dict。"""

    raw_input = getattr(run, "input", None)
    if not isinstance(raw_input, dict):
        return
    payload = _copy_payload(raw_input)
    try:
        if isinstance(run, TeamRunOutput):
            run.input = TeamRunInput.from_dict(payload)
        else:
            run.input = RunInput.from_dict(payload)
    except Exception:  # noqa: BLE001
        run.input = _SerializableMapping(payload)


def _run_from_dict(payload: dict[str, Any]) -> Any:
    """按 payload 所属类型还原 Agno run；兜底时返回具备 to_dict 的包装。"""

    data = _copy_payload(payload)
    try:
        if data.get("agent_id"):
            return RunOutput.from_dict(data)
        if data.get("team_id"):
            return TeamRunOutput.from_dict(data)
        if data.get("workflow_id"):
            return WorkflowRunOutput.from_dict(data)
        return RunOutput.from_dict(data)
    except Exception:  # noqa: BLE001
        return _SerializableMapping(data)


def _event_from_dict(payload: dict[str, Any]) -> Any:
    """按事件名前缀还原 Agno 事件；未知事件保留原始 payload。"""

    data = _copy_payload(payload)
    try:
        if str(data.get("event") or "").startswith("Team") or data.get("team_id"):
            return team_run_output_event_from_dict(data)
        return run_output_event_from_dict(data)
    except Exception:  # noqa: BLE001
        return _SerializableMapping(data)


def _message_from_dict(payload: dict[str, Any]) -> Any:
    """还原 Agno Message，避免 run.to_dict 对普通 dict 调用 to_dict。"""

    data = _copy_payload(payload)
    try:
        return Message.from_dict(data)
    except Exception:  # noqa: BLE001
        return _SerializableMapping(data)


def _tool_execution_from_dict(payload: dict[str, Any]) -> Any:
    """还原 Agno ToolExecution；失败时仍保证可序列化。"""

    data = _copy_payload(payload)
    try:
        return ToolExecution.from_dict(data)
    except Exception:  # noqa: BLE001
        return _SerializableMapping(data)


def _requirement_from_dict(payload: dict[str, Any]) -> Any:
    """还原 Agno RunRequirement；失败时仍保证可序列化。"""

    data = _copy_payload(payload)
    try:
        return RunRequirement.from_dict(data)
    except Exception:  # noqa: BLE001
        return _SerializableMapping(data)


def _copy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """复制 Agno payload；部分 from_dict 会原地 pop，不能污染调用方对象。"""

    return deepcopy(payload)


class _SerializableMapping:
    """给未知 dict 提供 Agno 需要的 to_dict 形态。"""

    def __init__(self, payload: dict[str, Any]) -> None:
        """保存原始 JSON payload。"""

        self._payload = payload

    def to_dict(self) -> dict[str, Any]:
        """返回可写入 Agno sessions 表的 JSON payload。"""

        return self._payload

