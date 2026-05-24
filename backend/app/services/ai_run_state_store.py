"""文件功能：用 Redis 管理智能体 run 的运行态、事件流、互斥锁与工具短租约。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.schemas.agent import AgentPendingRequirement, AgentRunEvent, AgentScopeContext
from app.services.redis_runtime_client import RedisRuntimeClient, get_redis_runtime_client

AI_RUN_ACTIVE_STATUSES = {"pending", "running", "paused", "cancelling"}
AI_RUN_TERMINAL_STATUSES = {"completed", "cancelled", "failed"}
AI_TOOL_AUTH_RUN_STATUSES = {"pending", "running"}


@dataclass(slots=True)
class AiRunRecord:
    """Redis 中一次智能体 run 的标准化运行态记录。"""

    task_id: str
    run_id: str
    session_id: str
    agent_id: str
    user_id: int
    backend_session_id: str | None
    scope_type: str
    workspace_id: int
    project_id: int | None
    page_id: int | None
    component_id: int | None
    source: str
    status: str
    input_summary: str | None
    input_payload_json: dict[str, Any] | None
    tool_scopes_json: list[str] | None
    tool_auth_expires_at: datetime | None
    tool_auth_max_expires_at: datetime | None
    error_code: str | None
    error_message: str | None
    pending_requirement_json: dict[str, Any] | None
    event_sequence: int
    cancel_requested_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class AiRunStateStore:
    """封装 Redis 中 Agent run 运行态的读写协议。"""

    def __init__(self, runtime_client: RedisRuntimeClient | None = None) -> None:
        self.runtime = runtime_client or get_redis_runtime_client()

    async def create_run(
        self,
        *,
        run_id: str,
        session_id: str,
        agent_id: str,
        user_id: int,
        backend_session_id: str | None,
        scope: AgentScopeContext,
        input_summary: str | None,
        input_payload_json: dict[str, Any] | None,
        tool_scopes: list[str],
    ) -> AiRunRecord:
        """创建 run 运行态，并用 Redis SET NX 抢占会话 active_run。"""

        settings = get_settings()
        now = utc_now()
        active_key = self._active_run_key(user_id=user_id, agent_id=agent_id, session_id=session_id)
        acquired = await asyncio.to_thread(
            self.runtime.client.set,
            active_key,
            run_id,
            ex=settings.ai_run_active_ttl_seconds,
            nx=True,
        )
        if not acquired:
            raise AppException(status_code=409, code="AI_SESSION_RUN_ACTIVE", detail="当前会话已有运行中的智能体任务。")

        record_payload = {
            "task_id": run_id,
            "run_id": run_id,
            "session_id": session_id,
            "agent_id": agent_id,
            "user_id": str(user_id),
            "backend_session_id": backend_session_id or "",
            "scope_type": scope.scope_type,
            "workspace_id": str(scope.workspace_id),
            "project_id": "" if scope.project_id is None else str(scope.project_id),
            "page_id": "" if scope.page_id is None else str(scope.page_id),
            "component_id": "" if scope.component_id is None else str(scope.component_id),
            "source": scope.source,
            "status": "pending",
            "input_summary": _trim_input_summary(input_summary) or "",
            "input_payload_json": self.runtime.dumps(input_payload_json or {}),
            "tool_scopes_json": self.runtime.dumps(tool_scopes),
            "tool_auth_expires_at": _format_datetime(now + timedelta(seconds=settings.ai_tool_auth_window_seconds)),
            "tool_auth_max_expires_at": _format_datetime(now + timedelta(seconds=settings.ai_tool_auth_max_seconds)),
            "error_code": "",
            "error_message": "",
            "pending_requirement_json": "",
            "event_sequence": "0",
            "cancel_requested_at": "",
            "started_at": "",
            "finished_at": "",
            "created_at": _format_datetime(now),
            "updated_at": _format_datetime(now),
        }
        await asyncio.to_thread(self._write_hash_with_ttl, self._run_key(run_id), record_payload, settings.ai_run_active_ttl_seconds)
        record = await self.get_run(run_id=run_id, user_id=user_id)
        if record is None:
            raise AppException(status_code=503, code="AI_RUN_STATE_CREATE_FAILED", detail="智能体运行态创建失败。")
        return record

    async def get_run(self, *, run_id: str, user_id: int | None = None) -> AiRunRecord | None:
        """按 run_id 读取运行态，可选校验所属用户。"""

        payload = await asyncio.to_thread(self.runtime.client.hgetall, self._run_key(run_id))
        record = self._record_from_hash(payload)
        if record is None:
            return None
        if user_id is not None and record.user_id != user_id:
            return None
        return record

    async def get_latest_run(self, *, session_id: str, agent_id: str, user_id: int) -> AiRunRecord | None:
        """读取当前会话最近一次 run，终态记录也参与排序。"""

        records = await self._list_runs_for_session(session_id=session_id, agent_id=agent_id, user_id=user_id)
        if not records:
            return None
        return max(records, key=lambda item: (item.created_at or datetime.fromtimestamp(0, tz=UTC), item.run_id))

    async def get_latest_active_run(self, *, session_id: str, agent_id: str, user_id: int) -> AiRunRecord | None:
        """读取当前会话 active run；active key 缺失时扫描 Redis run 兜底。"""

        active_run_id = await asyncio.to_thread(
            self.runtime.client.get,
            self._active_run_key(user_id=user_id, agent_id=agent_id, session_id=session_id),
        )
        if active_run_id:
            record = await self.get_run(run_id=str(active_run_id), user_id=user_id)
            if record is not None and record.agent_id == agent_id and record.session_id == session_id and record.status in AI_RUN_ACTIVE_STATUSES:
                return record

        records = [
            record
            for record in await self._list_runs_for_session(session_id=session_id, agent_id=agent_id, user_id=user_id)
            if record.status in AI_RUN_ACTIVE_STATUSES
        ]
        if not records:
            return None
        return max(records, key=lambda item: (item.updated_at or item.created_at or datetime.fromtimestamp(0, tz=UTC), item.run_id))

    async def append_event(self, *, run_id: str, user_id: int | None, event: AgentRunEvent) -> AgentRunEvent | None:
        """追加标准事件并同步 run 状态。"""

        record = await self.get_run(run_id=run_id, user_id=user_id)
        if record is None:
            raise RuntimeError(f"AI run state not found: {run_id}")
        if record.status in AI_RUN_TERMINAL_STATUSES:
            return None
        if await self._is_replayed_pause_event_after_continue(record=record, event=event):
            return None

        sequence = int(record.event_sequence or 0) + 1
        event.sequence = sequence
        event.run_id = event.run_id or run_id
        event.session_id = event.session_id or record.session_id
        next_updates = self._build_event_state_updates(record=record, event=event, sequence=sequence)
        ttl = self._ttl_for_status(str(next_updates.get("status") or record.status))
        payload_json = event.model_dump(mode="json")

        def write() -> None:
            pipe = self.runtime.client.pipeline()
            pipe.xadd(
                self._events_key(run_id),
                {
                    "sequence": str(sequence),
                    "event": event.event,
                    "payload_json": self.runtime.dumps(payload_json),
                },
                maxlen=get_settings().ai_run_event_maxlen,
                approximate=True,
            )
            pipe.hset(self._run_key(run_id), mapping=next_updates)
            pipe.expire(self._run_key(run_id), ttl)
            pipe.expire(self._events_key(run_id), ttl)
            if _is_terminal_status(str(next_updates.get("status") or "")):
                pipe.delete(self._active_run_key(user_id=record.user_id, agent_id=record.agent_id, session_id=record.session_id))
            else:
                pipe.set(
                    self._active_run_key(user_id=record.user_id, agent_id=record.agent_id, session_id=record.session_id),
                    run_id,
                    ex=ttl,
                )
            pipe.execute()

        await asyncio.to_thread(write)
        return event

    async def list_events_after(self, *, run_id: str, user_id: int, after_sequence: int) -> list[AgentRunEvent]:
        """按 sequence 顺序读取指定 run 的历史事件。"""

        record = await self.get_run(run_id=run_id, user_id=user_id)
        if record is None:
            return []
        raw_events = await asyncio.to_thread(self.runtime.client.xrange, self._events_key(run_id))
        events: list[AgentRunEvent] = []
        for _, fields in raw_events:
            sequence = _coerce_int(fields.get("sequence"), default=0) or 0
            if sequence <= after_sequence:
                continue
            payload = self.runtime.loads(fields.get("payload_json"), default={})
            if not isinstance(payload, dict):
                continue
            event = AgentRunEvent.model_validate(payload)
            event.sequence = sequence
            events.append(event)
        events.sort(key=lambda item: int(item.sequence or 0))
        return events

    async def wait_events_after(
        self,
        *,
        run_id: str,
        user_id: int,
        after_sequence: int,
        block_ms: int = 1000,
    ) -> list[AgentRunEvent]:
        """阻塞等待 Redis Stream 新事件，并返回指定 sequence 之后的事件。"""

        record = await self.get_run(run_id=run_id, user_id=user_id)
        if record is None:
            return []
        last_stream_id = await self._stream_id_at_or_before_sequence(run_id=run_id, sequence=after_sequence)
        await asyncio.to_thread(
            self.runtime.client.xread,
            {self._events_key(run_id): last_stream_id},
            count=1,
            block=max(1, block_ms),
        )
        return await self.list_events_after(run_id=run_id, user_id=user_id, after_sequence=after_sequence)

    async def mark_running(self, *, record: AiRunRecord, reset_tool_auth: bool = False) -> AiRunRecord:
        """把 run 预先标记为运行中，必要时重置工具授权窗口。"""

        if record.status in AI_RUN_TERMINAL_STATUSES:
            return record
        now = utc_now()
        updates: dict[str, str] = {
            "status": "running",
            "pending_requirement_json": "",
            "started_at": _format_datetime(record.started_at or now),
            "updated_at": _format_datetime(now),
        }
        if reset_tool_auth:
            max_expires_at = now + timedelta(seconds=get_settings().ai_tool_auth_max_seconds)
            updates["tool_auth_max_expires_at"] = _format_datetime(max_expires_at)
            updates["tool_auth_expires_at"] = _format_datetime(
                min(now + timedelta(seconds=get_settings().ai_tool_auth_window_seconds), max_expires_at)
            )
        await asyncio.to_thread(self._write_hash_with_ttl, self._run_key(record.run_id), updates, get_settings().ai_run_active_ttl_seconds)
        await asyncio.to_thread(
            self.runtime.client.set,
            self._active_run_key(user_id=record.user_id, agent_id=record.agent_id, session_id=record.session_id),
            record.run_id,
            ex=get_settings().ai_run_active_ttl_seconds,
        )
        return await self.get_run(run_id=record.run_id, user_id=record.user_id) or record

    async def mark_paused(
        self,
        *,
        record: AiRunRecord,
        pending_requirement: AgentPendingRequirement,
        append_event: bool = True,
        allow_terminal_restore: bool = False,
    ) -> AiRunRecord:
        """把 run 收敛到暂停态，并按需补写暂停事件。"""

        record = await self.get_run(run_id=record.run_id, user_id=record.user_id) or record
        if record.status in AI_RUN_TERMINAL_STATUSES and not allow_terminal_restore:
            return record
        requirement_payload = pending_requirement.model_dump(mode="json")
        already_paused = (
            record.status == "paused"
            and _pending_requirement_identity(record.pending_requirement_json)
            == _pending_requirement_identity(requirement_payload)
        )
        updates = {
            "status": "paused",
            "pending_requirement_json": self.runtime.dumps(requirement_payload),
            "error_code": "",
            "error_message": "",
            "finished_at": "",
            "updated_at": _format_datetime(utc_now()),
        }
        await asyncio.to_thread(self._write_hash_with_ttl, self._run_key(record.run_id), updates, get_settings().ai_run_paused_ttl_seconds)
        await asyncio.to_thread(
            self.runtime.client.set,
            self._active_run_key(user_id=record.user_id, agent_id=record.agent_id, session_id=record.session_id),
            record.run_id,
            ex=get_settings().ai_run_paused_ttl_seconds,
        )
        updated = await self.get_run(run_id=record.run_id, user_id=record.user_id) or record
        if append_event and not already_paused:
            await self.append_event(
                run_id=record.run_id,
                user_id=record.user_id,
                event=AgentRunEvent(
                    event="run.paused",
                    run_id=record.run_id,
                    session_id=record.session_id,
                    data={"requirement": requirement_payload},
                ),
            )
            updated = await self.get_run(run_id=record.run_id, user_id=record.user_id) or updated
        return updated

    async def mark_terminal(
        self,
        *,
        record: AiRunRecord,
        status: str,
        content: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> AgentRunEvent:
        """强制把 run 推进终态，并补写终态事件。"""

        event_name = {
            "completed": "run.completed",
            "cancelled": "run.cancelled",
            "failed": "run.error",
        }.get(status, "run.error")
        event = AgentRunEvent(
            event=event_name,
            run_id=record.run_id,
            session_id=record.session_id,
            content=content,
            data={"message": error_message or content or "", "code": error_code} if status == "failed" else {"message": content or ""},
        )
        persisted = await self.append_event(run_id=record.run_id, user_id=record.user_id, event=event)
        return persisted or event

    async def authorize_tool_call(
        self,
        *,
        run_id: str,
        user_id: int,
        session_id: str,
        agent_id: str,
        backend_session_id: str | None,
        source: str,
        required_scopes: list[str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """按 Redis run 校验工具授权，并刷新滑动窗口。"""

        record = await self.get_run(run_id=run_id, user_id=user_id)
        if record is None:
            raise AppException(status_code=401, code="AI_TOOL_CONTEXT_REQUIRED", detail="当前工具缺少有效运行上下文。")
        if record.status not in AI_TOOL_AUTH_RUN_STATUSES:
            raise AppException(status_code=403, code="AI_TOOL_RUN_INACTIVE", detail="当前运行状态不允许继续调用工具。")
        _ensure_tool_context_matches(
            record,
            session_id=session_id,
            agent_id=agent_id,
            backend_session_id=backend_session_id,
            source=source,
        )
        now = utc_now()
        if record.tool_auth_expires_at is None or _ensure_aware(record.tool_auth_expires_at) <= now:
            raise AppException(status_code=401, code="AI_TOOL_AUTH_EXPIRED", detail="工具授权已过期，请重新发起智能体运行。")
        if record.tool_auth_max_expires_at is None or _ensure_aware(record.tool_auth_max_expires_at) <= now:
            raise AppException(status_code=401, code="AI_TOOL_AUTH_EXPIRED", detail="工具授权已超过最长有效时间，请重新发起智能体运行。")

        granted_scopes = _normalize_tool_scopes(record.tool_scopes_json)
        missing_scopes = [scope for scope in required_scopes if scope not in granted_scopes]
        if missing_scopes:
            raise AppException(
                status_code=403,
                code="AI_TOOL_SCOPE_DENIED",
                detail=f"当前运行缺少必要工具权限：{', '.join(missing_scopes)}。",
            )

        next_expires_at = min(
            now + timedelta(seconds=get_settings().ai_tool_auth_window_seconds),
            _ensure_aware(record.tool_auth_max_expires_at),
        )
        await asyncio.to_thread(
            self.runtime.client.hset,
            self._run_key(run_id),
            mapping={
                "tool_auth_expires_at": _format_datetime(next_expires_at),
                "updated_at": _format_datetime(now),
            },
        )
        tool_context = {
            "run_id": record.run_id,
            "session_id": record.session_id,
            "agent_id": record.agent_id,
            "user_id": record.user_id,
            "user_id": str(record.user_id),
            "backend_session_id": record.backend_session_id,
            "scope_type": record.scope_type,
            "workspace_id": record.workspace_id,
            "project_id": record.project_id,
            "page_id": record.page_id,
            "component_id": record.component_id,
            "role": "admin",
            "source": record.source,
            "scopes": granted_scopes,
        }
        return tool_context, {"sub": f"user:{record.user_id}", **tool_context}

    async def update_run_fields(self, *, run_id: str, user_id: int, fields: dict[str, Any]) -> AiRunRecord:
        """按字段更新 run Hash，供迁移脚本和测试精确调整运行态。"""

        record = await self.get_run(run_id=run_id, user_id=user_id)
        if record is None:
            raise RuntimeError(f"AI run state not found: {run_id}")
        normalized: dict[str, str] = {"updated_at": _format_datetime(utc_now())}
        for key, value in fields.items():
            if isinstance(value, datetime):
                normalized[key] = _format_datetime(value)
            elif isinstance(value, (dict, list)):
                normalized[key] = self.runtime.dumps(value)
            else:
                normalized[key] = "" if value is None else str(value)
        ttl = self._ttl_for_status(str(normalized.get("status") or record.status))
        await asyncio.to_thread(self._write_hash_with_ttl, self._run_key(run_id), normalized, ttl)
        return await self.get_run(run_id=run_id, user_id=user_id) or record

    async def publish_cancel(self, *, run_id: str, force: bool) -> None:
        """发布取消请求，供持有本地 Agno stream 的进程响应。"""

        await asyncio.to_thread(
            self.runtime.client.publish,
            self.runtime.key(f"ai:run:{run_id}:cancel"),
            self.runtime.dumps({"run_id": run_id, "force": force, "created_at": _format_datetime(utc_now())}),
        )

    async def iter_active_orphan_runs(self) -> list[AiRunRecord]:
        """扫描 Redis 中所有非终态 run，供启动恢复使用。"""

        keys = await asyncio.to_thread(list, self.runtime.client.scan_iter(match=self.runtime.key("ai:run:*")))
        records: list[AiRunRecord] = []
        for key in keys:
            if str(key).endswith(":events") or ":cancel" in str(key):
                continue
            payload = await asyncio.to_thread(self.runtime.client.hgetall, key)
            record = self._record_from_hash(payload)
            if record is not None and record.status in {"pending", "running", "cancelling"}:
                records.append(record)
        return records

    async def list_runs_for_session(self, *, session_id: str, agent_id: str, user_id: int) -> list[AiRunRecord]:
        """列出当前会话在 Redis TTL 内仍可查询的 run 记录。"""

        return await self._list_runs_for_session(
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
        )

    async def _list_runs_for_session(self, *, session_id: str, agent_id: str, user_id: int) -> list[AiRunRecord]:
        """扫描当前会话的 run 记录。"""

        keys = await asyncio.to_thread(list, self.runtime.client.scan_iter(match=self.runtime.key("ai:run:*")))
        records: list[AiRunRecord] = []
        for key in keys:
            if str(key).endswith(":events") or ":cancel" in str(key):
                continue
            payload = await asyncio.to_thread(self.runtime.client.hgetall, key)
            record = self._record_from_hash(payload)
            if (
                record is not None
                and record.session_id == session_id
                and record.agent_id == agent_id
                and record.user_id == user_id
            ):
                records.append(record)
        return records

    async def _stream_id_at_or_before_sequence(self, *, run_id: str, sequence: int) -> str:
        """查找指定 sequence 对应或之前的 Redis Stream ID，供 XREAD BLOCK 使用。"""

        if sequence <= 0:
            return "0-0"
        raw_events = await asyncio.to_thread(self.runtime.client.xrange, self._events_key(run_id))
        last_stream_id = "0-0"
        for stream_id, fields in raw_events:
            event_sequence = _coerce_int(fields.get("sequence"), default=0) or 0
            if event_sequence > sequence:
                break
            last_stream_id = str(stream_id)
        return last_stream_id

    async def _is_replayed_pause_event_after_continue(self, *, record: AiRunRecord, event: AgentRunEvent) -> bool:
        """继续运行后忽略 Agno 回放的上一条 pause。"""

        if record.status != "running" or event.event != "run.paused":
            return False
        current_identity = _pending_requirement_identity(_extract_event_requirement(event.data))
        if current_identity is None:
            return False
        previous_events = await self.list_events_after(run_id=record.run_id, user_id=record.user_id, after_sequence=0)
        for previous_event in reversed(previous_events):
            if previous_event.event != "run.paused":
                continue
            return current_identity == _pending_requirement_identity(_extract_event_requirement(previous_event.data))
        return False

    def _build_event_state_updates(self, *, record: AiRunRecord, event: AgentRunEvent, sequence: int) -> dict[str, str]:
        """根据事件名称推导 run Hash 更新字段。"""

        now = utc_now()
        updates = {
            "event_sequence": str(sequence),
            "updated_at": _format_datetime(now),
        }
        if event.event in {"run.started", "run.continued"}:
            updates["status"] = "running"
            updates["started_at"] = _format_datetime(record.started_at or now)
            updates["pending_requirement_json"] = ""
            updates["error_code"] = ""
            updates["error_message"] = ""
        elif event.event == "run.cancelling":
            updates["status"] = "cancelling"
            updates["cancel_requested_at"] = _format_datetime(now)
            updates["pending_requirement_json"] = ""
        elif event.event == "run.paused":
            updates["status"] = "paused"
            requirement = _extract_event_requirement(event.data)
            updates["pending_requirement_json"] = self.runtime.dumps(requirement) if requirement else ""
            updates["finished_at"] = ""
        elif event.event == "run.completed":
            updates["status"] = "completed"
            updates["finished_at"] = _format_datetime(now)
            updates["pending_requirement_json"] = ""
            updates["error_code"] = ""
            updates["error_message"] = ""
        elif event.event == "run.cancelled":
            updates["status"] = "cancelled"
            updates["finished_at"] = _format_datetime(now)
            updates["pending_requirement_json"] = ""
            updates["error_message"] = event.content or str(event.data.get("message") or "")
        elif event.event == "run.error":
            updates["status"] = "failed"
            updates["finished_at"] = _format_datetime(now)
            updates["pending_requirement_json"] = ""
            updates["error_code"] = str(event.data.get("code") or "")
            updates["error_message"] = str(event.data.get("message") or event.content or "")
        return updates

    def _write_hash_with_ttl(self, key: str, mapping: dict[str, Any], ttl_seconds: int) -> None:
        """写入 Hash 并同步设置 TTL。"""

        pipe = self.runtime.client.pipeline()
        pipe.hset(key, mapping={str(k): "" if v is None else str(v) for k, v in mapping.items()})
        pipe.expire(key, ttl_seconds)
        pipe.execute()

    def _ttl_for_status(self, status: str) -> int:
        """按状态选择 Redis TTL。"""

        settings = get_settings()
        if status == "paused":
            return settings.ai_run_paused_ttl_seconds
        if status in AI_RUN_TERMINAL_STATUSES:
            return settings.ai_run_terminal_ttl_seconds
        return settings.ai_run_active_ttl_seconds

    def _record_from_hash(self, payload: dict[str, Any]) -> AiRunRecord | None:
        """把 Redis Hash 转换为内部记录对象。"""

        if not payload:
            return None
        try:
            run_id = str(payload.get("run_id") or "")
            if not run_id:
                return None
            return AiRunRecord(
                task_id=str(payload.get("task_id") or run_id),
                run_id=run_id,
                session_id=str(payload.get("session_id") or ""),
                agent_id=str(payload.get("agent_id") or ""),
                user_id=int(payload.get("user_id") or 0),
                backend_session_id=_optional_str(payload.get("backend_session_id")),
                scope_type=str(payload.get("scope_type") or "page"),
                workspace_id=int(payload.get("workspace_id") or 0),
                project_id=_optional_int(payload.get("project_id")),
                page_id=_optional_int(payload.get("page_id")),
                component_id=_optional_int(payload.get("component_id")),
                source=str(payload.get("source") or ""),
                status=str(payload.get("status") or "pending"),
                input_summary=_optional_str(payload.get("input_summary")),
                input_payload_json=self.runtime.loads(payload.get("input_payload_json"), default={}) or {},
                tool_scopes_json=_normalize_tool_scopes(self.runtime.loads(payload.get("tool_scopes_json"), default=[])),
                tool_auth_expires_at=_parse_datetime(payload.get("tool_auth_expires_at")),
                tool_auth_max_expires_at=_parse_datetime(payload.get("tool_auth_max_expires_at")),
                error_code=_optional_str(payload.get("error_code")),
                error_message=_optional_str(payload.get("error_message")),
                pending_requirement_json=self.runtime.loads(payload.get("pending_requirement_json"), default=None),
                event_sequence=int(payload.get("event_sequence") or 0),
                cancel_requested_at=_parse_datetime(payload.get("cancel_requested_at")),
                started_at=_parse_datetime(payload.get("started_at")),
                finished_at=_parse_datetime(payload.get("finished_at")),
                created_at=_parse_datetime(payload.get("created_at")),
                updated_at=_parse_datetime(payload.get("updated_at")),
            )
        except (TypeError, ValueError):
            return None

    def _run_key(self, run_id: str) -> str:
        return self.runtime.key(f"ai:run:{run_id}")

    def _events_key(self, run_id: str) -> str:
        return self.runtime.key(f"ai:run:{run_id}:events")

    def _active_run_key(self, *, user_id: int, agent_id: str, session_id: str) -> str:
        return self.runtime.key(f"ai:session:{user_id}:{agent_id}:{session_id}:active_run")


def _ensure_tool_context_matches(
    record: AiRunRecord,
    *,
    session_id: str,
    agent_id: str,
    backend_session_id: str | None,
    source: str,
) -> None:
    """校验工具调用定位字段与 run 运行态一致。"""

    expected_values = {
        "session_id": record.session_id,
        "agent_id": record.agent_id,
        "backend_session_id": record.backend_session_id,
        "source": record.source,
    }
    actual_values = {
        "session_id": session_id,
        "agent_id": agent_id,
        "backend_session_id": backend_session_id,
        "source": source,
    }
    for field_name, expected_value in expected_values.items():
        actual_value = actual_values[field_name]
        if expected_value is None and actual_value is None:
            continue
        if str(expected_value) != str(actual_value):
            raise AppException(
                status_code=403,
                code="AI_TOOL_CONTEXT_MISMATCH",
                detail=f"工具上下文校验失败：{field_name} 不匹配。",
            )


def _pending_requirement_identity(requirement: dict[str, Any] | None) -> tuple[str, str, str, str] | None:
    """生成 HITL requirement 身份，优先使用 tool_call_id。"""

    if not isinstance(requirement, dict):
        return None
    tool_execution = requirement.get("tool_execution")
    if not isinstance(tool_execution, dict):
        tool_execution = {}
    member_agent_id = _optional_str(requirement.get("member_agent_id") or tool_execution.get("member_agent_id")) or ""
    member_run_id = _optional_str(requirement.get("member_run_id") or tool_execution.get("member_run_id")) or ""
    tool_call_id = _optional_str(tool_execution.get("tool_call_id"))
    if tool_call_id:
        return ("tool_call_id", tool_call_id, member_agent_id, member_run_id)
    requirement_id = _optional_str(requirement.get("id"))
    if requirement_id:
        return ("requirement_id", requirement_id, member_agent_id, member_run_id)
    tool_name = _optional_str(requirement.get("tool_name") or tool_execution.get("tool_name"))
    if tool_name:
        return ("tool_name", tool_name, member_agent_id, member_run_id)
    return None


def _extract_event_requirement(data: Any) -> dict[str, Any] | None:
    """从标准事件 data 中取出待处理 requirement。"""

    if not isinstance(data, dict):
        return None
    requirement = data.get("requirement")
    return requirement if isinstance(requirement, dict) else None


def _normalize_tool_scopes(value: Any) -> list[str]:
    """把工具权限快照规整为字符串列表。"""

    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _ensure_aware(value: datetime) -> datetime:
    """将时间规整为 UTC aware datetime。"""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_datetime(value: Any) -> datetime | None:
    """从 Redis 字符串解析 ISO 时间。"""

    text = _optional_str(value)
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        result = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return _ensure_aware(result)


def _format_datetime(value: datetime | None) -> str:
    """统一输出 ISO 时间字符串。"""

    if value is None:
        return ""
    return _ensure_aware(value).isoformat()


def _optional_str(value: Any) -> str | None:
    """把空字符串与 None 统一为 None。"""

    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_int(value: Any) -> int | None:
    """把 Redis 中的可选整数字段转换为 int。"""

    text = _optional_str(value)
    if text is None:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any, *, default: int | None = None) -> int | None:
    """安全转换整数。"""

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _trim_input_summary(value: str | None) -> str | None:
    """限制任务输入摘要长度。"""

    if value is None:
        return None
    normalized = value.strip()
    return normalized[:500] if normalized else None


def _is_terminal_status(status: str) -> bool:
    """判断状态是否为终态。"""

    return status in AI_RUN_TERMINAL_STATUSES


def build_scope_from_run_record(record: AiRunRecord) -> AgentScopeContext:
    """从 Redis run 记录恢复 Agent scope。"""

    return AgentScopeContext(
        scope_type=record.scope_type,  # type: ignore[arg-type]
        workspace_id=record.workspace_id,
        project_id=record.project_id,
        page_id=record.page_id,
        component_id=record.component_id,
        source=record.source,
    )
