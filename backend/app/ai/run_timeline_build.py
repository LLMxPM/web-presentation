"""文件功能：把运行态事件、消息与工具调用投影为前端会话 timeline 项。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import WorkspaceAsset
from app.models.ai_agent_attachment import AiAgentImageAttachment
from app.models.ai_agent_runtime import (
    AiAgentMessage,
    AiAgentRun,
    AiAgentRunEvent,
    AiAgentToolCall,
)
from app.models.enums import RecordStatus
from app.schemas.agent import (
    AgentMessageAttachmentItem,
    AgentRunProjectSummary,
    AgentRunContextSummary,
    AgentRunEvent,
    AgentScopeContext,
    AgentTimelineItem,
    AgentTimelineToolItem,
)
from app.services.agent_image_attachment_service import AgentImageAttachmentService

# 事件投影使用的活动 run 状态，用于 timeline 展示 running 标记。
ACTIVE_RUN_STATUSES = {"pending", "running", "paused", "waiting_external", "cancelling"}


def utc_now():
    """返回 UTC 当前时间。"""

    from datetime import UTC, datetime

    return datetime.now(tz=UTC)


def as_utc(value):
    """把数据库时间统一为 UTC aware datetime，兼容测试库返回的 naive 时间。"""

    from datetime import UTC

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso(value):
    """把 datetime 转为带 UTC 偏移的接口字符串，历史 naive 值直接补 UTC。"""

    from app.core.time_utils import normalize_utc

    return normalize_utc(value).isoformat() if value is not None else None


def timeline_sort_key(
    run_order: dict[str, int],
    *,
    run_id: str,
    event_index: int | None,
    phase: int,
    created_at: str | None,
    fallback_id: str,
) -> tuple[int, int, int, str, str]:
    """生成前端 timeline 的全局排序 key；phase 负责依次放置用户消息、Run 上下文和事件。"""

    max_event_index = 1_000_000_000
    run_position = run_order.get(run_id, max_event_index)
    if event_index is None:
        event_position = -1 if phase < 0 else max_event_index
    else:
        event_position = event_index
    return (run_position, event_position, phase, created_at or "", fallback_id)


def tool_input_attachment_ids(input_payload: Any) -> list[int]:
    """从视觉工具输入中提取真实附件 ID，并保持首次出现顺序。"""

    if not isinstance(input_payload, dict):
        return []
    raw_values: list[Any] = []
    for key in ("image_attachment_ids", "reference_attachment_ids"):
        value = input_payload.get(key)
        if isinstance(value, list):
            raw_values.extend(value)
    if input_payload.get("mask_attachment_id") is not None:
        raw_values.append(input_payload["mask_attachment_id"])
    inputs = input_payload.get("inputs")
    if isinstance(inputs, list):
        raw_values.extend(
            item.get("attachment_id")
            for item in inputs
            if isinstance(item, dict) and item.get("source_type") == "attachment"
        )
    result: list[int] = []
    for value in raw_values:
        try:
            attachment_id = int(value)
        except (TypeError, ValueError):
            continue
        if attachment_id > 0 and attachment_id not in result:
            result.append(attachment_id)
    return result


def first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """按顺序读取第一个存在的 key，保留空 dict、0、False 等合法值。"""

    for key in keys:
        if key in data:
            return data[key]
    return None


def is_meaningful_payload(value: Any) -> bool:
    """判断工具 payload 是否携带真实参数，避免空串覆盖后续完整参数。"""

    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def remove_requirement_timeline_items(
    items: list[AgentTimelineItem],
    *,
    requirement_items_by_run: dict[str, list[AgentTimelineItem]],
    run_id: str,
) -> None:
    """移除已经被继续、取消或终止的 HITL requirement 占位。"""

    stale_items = requirement_items_by_run.pop(run_id, [])
    if not stale_items:
        return
    stale_ids = {item.id for item in stale_items}
    items[:] = [item for item in items if item.id not in stale_ids]


def mark_open_tool_items_failed(
    tool_items: dict[tuple[str, str], AgentTimelineItem],
    *,
    run_id: str,
    message: str,
) -> None:
    """回放到 run.error 时收敛同 run 中仍处于 running 的工具展示项。"""

    for (item_run_id, _), item in tool_items.items():
        if item_run_id != run_id or item.kind != "tool" or item.tool is None:
            continue
        if item.tool.status != "running":
            continue
        item.status = "error"
        item.tool.status = "error"
        item.tool.message = item.tool.message or message


def mark_last_assistant_timeline_item_interrupted(
    items: list[AgentTimelineItem],
    *,
    run_id: str,
) -> None:
    """把失败 Run 最后一段可见助手正文标记为未完成。"""

    for item in reversed(items):
        if item.run_id != run_id or item.kind != "message" or item.role != "assistant":
            continue
        if str(item.content or "").strip():
            item.status = "interrupted"
        return


def run_context_timeline_item(run: AiAgentRun) -> AgentTimelineItem:
    """把 Run 输入快照转换成紧跟本轮用户消息的可回放上下文摘要。"""

    payload = run.input_payload_json or {}
    focus_payload = payload.get("focus") if isinstance(payload.get("focus"), dict) else {}
    focus = AgentScopeContext.model_validate({
        "scope_type": run.scope_type,
        "workspace_id": run.workspace_id,
        "project_id": run.project_id,
        "page_id": run.page_id,
        "component_id": run.component_id,
        "source": run.source,
        **focus_payload,
    })
    raw_projects = payload.get("allowed_projects") if isinstance(payload.get("allowed_projects"), list) else []
    allowed_projects = [
        AgentRunProjectSummary.model_validate(item)
        for item in raw_projects
        if isinstance(item, dict) and item.get("id") is not None
    ]
    if not allowed_projects:
        allowed_projects = [
            AgentRunProjectSummary(id=int(project_id), name=None)
            for project_id in payload.get("allowed_project_ids") or []
        ]
    return AgentTimelineItem(
        id=f"run-context-{run.run_id}",
        session_id=run.session_id,
        run_id=run.run_id,
        kind="run_context",
        role=None,
        event_index=None,
        order_index=0,
        content=None,
        status=run.status,
        tool=None,
        run_context=AgentRunContextSummary(
            focus=focus,
            work_scope_mode=str(payload.get("work_scope_mode") or "workspace"),  # type: ignore[arg-type]
            allowed_projects=allowed_projects,
            focus_version=int(payload.get("focus_version") or 0),
        ),
        source="synthetic",
        created_at=iso(run.created_at),
    )


class RunTimelineProjector:
    """基于会话消息、工具调用与事件流组装 Editor timeline。"""

    def __init__(self, session: AsyncSession, *, user_id: int) -> None:
        """保存数据库会话与当前用户，用于附件与资产投影。"""

        self._session = session
        self._user_id = user_id

    async def build_timeline_items(self, *, session_id: str) -> list[AgentTimelineItem]:
        """基于平台消息、工具调用、requirement 与事件生成会话 timeline。"""

        timeline_entries: list[tuple[tuple[int, int, int, str, str], AgentTimelineItem]] = []
        run_order = await self._run_order_map(session_id=session_id)
        run_result = await self._session.execute(
            select(AiAgentRun)
            .where(AiAgentRun.session_id == session_id)
            .order_by(AiAgentRun.created_at.asc())
        )
        runs = run_result.scalars().all()
        for run in runs:
            run_context_item = run_context_timeline_item(run)
            timeline_entries.append((
                timeline_sort_key(
                    run_order,
                    run_id=run.run_id,
                    event_index=None,
                    phase=-1,
                    created_at=run_context_item.created_at,
                    fallback_id=run_context_item.id,
                ),
                run_context_item,
            ))
        event_output_run_ids: set[str] = set()
        message_result = await self._session.execute(
            select(AiAgentMessage)
            .where(AiAgentMessage.session_id == session_id)
            .order_by(AiAgentMessage.order_index.asc(), AiAgentMessage.id.asc())
        )
        messages = message_result.scalars().all()
        event_result = await self._session.execute(
            select(AiAgentRunEvent)
            .where(AiAgentRunEvent.session_id == session_id)
            .order_by(AiAgentRunEvent.run_id.asc(), AiAgentRunEvent.event_index.asc(), AiAgentRunEvent.id.asc())
        )
        for item in self._timeline_items_from_event_rows(event_result.scalars().all()):
            if item.kind in {"message", "reasoning"}:
                event_output_run_ids.add(item.run_id)
            timeline_entries.append((
                timeline_sort_key(
                    run_order,
                    run_id=item.run_id,
                    event_index=item.event_index,
                    phase=0,
                    created_at=item.created_at,
                    fallback_id=item.id,
                ),
                item,
            ))

        for run in runs:
            if run.run_id in event_output_run_ids:
                continue
            if run.reasoning_content:
                item = AgentTimelineItem(
                    id=f"run-{run.run_id}-reasoning",
                    session_id=run.session_id,
                    run_id=run.run_id,
                    kind="reasoning",
                    role=None,
                    event_index=run.event_index,
                    order_index=0,
                    content=run.reasoning_content,
                    status="running" if run.status in ACTIVE_RUN_STATUSES else None,
                    tool=None,
                    source="event",
                    created_at=iso(run.created_at),
                )
                timeline_entries.append((
                    timeline_sort_key(
                        run_order,
                        run_id=item.run_id,
                        event_index=item.event_index,
                        phase=1,
                        created_at=item.created_at,
                        fallback_id=item.id,
                    ),
                    item,
                ))
            if run.content:
                item = AgentTimelineItem(
                    id=f"run-{run.run_id}-message",
                    session_id=run.session_id,
                    run_id=run.run_id,
                    kind="message",
                    role="assistant",
                    event_index=run.event_index,
                    order_index=0,
                    content=run.content,
                    status="running" if run.status in ACTIVE_RUN_STATUSES else None,
                    tool=None,
                    source="event",
                    created_at=iso(run.created_at),
                )
                timeline_entries.append((
                    timeline_sort_key(
                        run_order,
                        run_id=item.run_id,
                        event_index=item.event_index,
                        phase=2,
                        created_at=item.created_at,
                        fallback_id=item.id,
                    ),
                    item,
                ))

        for message in messages:
            if (
                message.role == "assistant"
                and message.reasoning_content
                and (not message.run_id or message.run_id not in event_output_run_ids)
            ):
                self._append_message_timeline_entry(
                    timeline_entries,
                    run_order=run_order,
                    message=message,
                    kind="reasoning",
                    role=None,
                    content=message.reasoning_content,
                    phase=1,
                )
            if message.role != "assistant" or not message.run_id or message.run_id not in event_output_run_ids:
                self._append_message_timeline_entry(
                    timeline_entries,
                    run_order=run_order,
                    message=message,
                    kind="message",
                    role=message.role if message.role in {"user", "assistant"} else None,  # type: ignore[arg-type]
                    content=message.content,
                    phase=-2 if message.role == "user" else 2,
                )

        sorted_items = [item for _, item in sorted(timeline_entries, key=lambda entry: entry[0])]
        tool_attachments = await self._tool_attachment_summaries(session_id=session_id)
        attachment_lookup = await self._attachment_summary_lookup(session_id=session_id)
        promoted_asset_ids = {
            attachment.promoted_asset_id
            for attachments in tool_attachments.values()
            for attachment in attachments
            if attachment.promoted_asset_id is not None
        }
        promoted_assets: dict[int, WorkspaceAsset] = {}
        if promoted_asset_ids:
            assets = list(
                (
                    await self._session.execute(
                        select(WorkspaceAsset).where(WorkspaceAsset.id.in_(promoted_asset_ids))
                    )
                )
                .scalars()
                .all()
            )
            promoted_assets = {asset.id: asset for asset in assets}
        for order_index, item in enumerate(sorted_items):
            item.order_index = order_index
            if item.kind == "tool" and item.tool is not None:
                key = (item.run_id, item.tool.tool_call_id or "")
                fallback_key = (item.run_id, item.tool.tool_name)
                output_attachments = []
                if item.tool.status == "completed":
                    output_attachments = (
                        tool_attachments.get(key, [])
                        if item.tool.tool_call_id
                        else tool_attachments.get(fallback_key, [])
                    )
                input_attachments = [
                    attachment_lookup[attachment_id]
                    for attachment_id in tool_input_attachment_ids(item.tool.input_payload)
                    if attachment_id in attachment_lookup
                ]
                item.tool.input_attachments = input_attachments
                item.tool.output_attachments = output_attachments
                item.attachments = output_attachments
                if item.tool.tool_name == "generate_image" and item.tool.status == "completed":
                    output_payload = dict(item.tool.output_payload or {})
                    output_payload["assets"] = [
                        {
                            "id": promoted_assets[attachment.promoted_asset_id].id,
                            "name": promoted_assets[attachment.promoted_asset_id].name,
                            "original_name": promoted_assets[attachment.promoted_asset_id].original_name,
                        }
                        for attachment in output_attachments
                        if attachment.promoted_asset_id in promoted_assets
                    ]
                    output_payload["deleted_assets"] = [
                        {
                            "attachment_id": attachment.id,
                            "status": "deleted",
                            "message": "资源库副本已删除，会话原图仍可用并可重新保存。",
                        }
                        for attachment in output_attachments
                        if attachment.promotion_status == "deleted"
                    ]
                    item.tool.output_payload = output_payload
        return sorted_items

    async def _run_order_map(self, *, session_id: str) -> dict[str, int]:
        """按 run 创建顺序建立排序索引，event_index 只在单个 run 内有序。"""

        result = await self._session.execute(
            select(AiAgentRun.run_id)
            .where(AiAgentRun.session_id == session_id)
            .order_by(AiAgentRun.created_at.asc(), AiAgentRun.run_id.asc())
        )
        return {run_id: index for index, run_id in enumerate(result.scalars().all())}

    def _timeline_items_from_event_rows(self, event_rows: list[AiAgentRunEvent]) -> list[AgentTimelineItem]:
        """按事件流重建助手文本、推理、工具和待处理项，保持回放顺序与实时 SSE 一致。"""

        items: list[AgentTimelineItem] = []
        current_text_by_run: dict[str, AgentTimelineItem | None] = {}
        tool_items: dict[tuple[str, str], AgentTimelineItem] = {}
        requirement_items_by_run: dict[str, list[AgentTimelineItem]] = {}
        for event_row in event_rows:
            event = AgentRunEvent.model_validate(event_row.payload_json)
            event.run_id = event.run_id or event_row.run_id
            event.session_id = event.session_id or event_row.session_id
            event.event_index = event.event_index if event.event_index is not None else event_row.event_index
            run_id = event.run_id or event_row.run_id
            if event.event in {"message.delta", "reasoning.delta"}:
                item = self._append_text_event_timeline_item(
                    items,
                    current_text_by_run=current_text_by_run,
                    event_row=event_row,
                    event=event,
                    kind="message" if event.event == "message.delta" else "reasoning",
                )
                if event.content:
                    item.content = f"{item.content or ''}{event.content}"
                continue
            if event.event in {"tool.started", "tool.progress", "tool.completed", "tool.error"}:
                current_text_by_run[run_id] = None
                item = self._upsert_tool_event_timeline_item(
                    items,
                    tool_items=tool_items,
                    event_row=event_row,
                    event=event,
                    status={
                        "tool.started": "running",
                        "tool.progress": "running",
                        "tool.completed": "completed",
                        "tool.error": "interrupted" if event.data.get("outcome") == "unknown" else "error",
                    }[event.event],
                )
                if event.event == "tool.progress" and item.tool is not None:
                    data = event.data if isinstance(event.data, dict) else {}
                    item.tool.progress = {
                        key: data[key]
                        for key in ("phase", "message", "current", "total")
                        if key in data
                    }
                    if data.get("message"):
                        item.tool.message = str(data["message"])
                continue
            if event.event in {"run.paused", "run.waiting"}:
                current_text_by_run[run_id] = None
                requirement = event.data.get("requirement") if isinstance(event.data, dict) else None
                if isinstance(requirement, dict):
                    requirement_item = AgentTimelineItem(
                        id=f"requirement-{requirement.get('id') or event_row.id}",
                        session_id=event_row.session_id,
                        run_id=event_row.run_id,
                        kind="requirement",
                        role=None,
                        event_index=event_row.event_index,
                        order_index=0,
                        content=requirement.get("note"),
                        status="waiting_external" if event.event == "run.waiting" else "paused",
                        tool=None,
                        source="event",
                        created_at=iso(event_row.created_at),
                    )
                    items.append(requirement_item)
                    requirement_items_by_run.setdefault(run_id, []).append(requirement_item)
                continue
            if event.event in {"run.continued", "run.cancelling", "run.cancelled", "run.completed", "run.error"}:
                remove_requirement_timeline_items(
                    items,
                    requirement_items_by_run=requirement_items_by_run,
                    run_id=run_id,
                )
            if event.event in {"run.cancelled", "run.error"}:
                mark_last_assistant_timeline_item_interrupted(items, run_id=run_id)
            if event.event == "run.error":
                current_text_by_run[run_id] = None
                mark_open_tool_items_failed(
                    tool_items,
                    run_id=run_id,
                    message=str(event.data.get("message") or event.content or "运行中断，工具调用未完成。"),
                )
                continue
            if event.event.startswith("run.") or event.event == "model.request.started":
                current_text_by_run[run_id] = None
        return items

    def _append_text_event_timeline_item(
        self,
        items: list[AgentTimelineItem],
        *,
        current_text_by_run: dict[str, AgentTimelineItem | None],
        event_row: AiAgentRunEvent,
        event: AgentRunEvent,
        kind: str,
    ) -> AgentTimelineItem:
        """追加或复用当前 run 的连续文本片段。"""

        run_id = event.run_id or event_row.run_id
        role = "assistant" if kind == "message" else None
        current = current_text_by_run.get(run_id)
        if current is not None and current.kind == kind and current.role == role:
            return current
        item = AgentTimelineItem(
            id=f"event-{event_row.id}-{kind}",
            session_id=event_row.session_id,
            run_id=event_row.run_id,
            kind=kind,  # type: ignore[arg-type]
            role=role,  # type: ignore[arg-type]
            event_index=event_row.event_index,
            order_index=0,
            content="",
            status=None,
            tool=None,
            source="event",
            created_at=iso(event_row.created_at),
        )
        items.append(item)
        current_text_by_run[run_id] = item
        return item

    def _upsert_tool_event_timeline_item(
        self,
        items: list[AgentTimelineItem],
        *,
        tool_items: dict[tuple[str, str], AgentTimelineItem],
        event_row: AiAgentRunEvent,
        event: AgentRunEvent,
        status: str,
    ) -> AgentTimelineItem:
        """按 tool_call_id 合并工具开始、完成和失败事件。"""

        data = event.data if isinstance(event.data, dict) else {}
        run_id = event.run_id or event_row.run_id
        tool_call_id = str(data.get("tool_call_id") or "").strip()
        tool_name = str(data.get("tool_name") or "工具调用").strip()
        key = (run_id, tool_call_id or f"event-{event_row.id}")
        existing = tool_items.get(key)
        if existing is None:
            existing = AgentTimelineItem(
                id=f"tool-{run_id}-{tool_call_id or event_row.id}",
                session_id=event_row.session_id,
                run_id=event_row.run_id,
                kind="tool",
                role=None,
                event_index=event_row.event_index,
                order_index=0,
                content=None,
                status=status,
                tool=AgentTimelineToolItem(
                    tool_call_id=tool_call_id or None,
                    tool_name=tool_name,
                    status=status if status in {"running", "waiting_external", "completed", "error", "cancelled", "interrupted"} else "running",  # type: ignore[arg-type]
                    input_payload=first_present(data, ("tool_args", "arguments", "args")),
                    output_payload=first_present(data, ("result", "output")),
                    message=str(data.get("message") or event.content or ""),
                ),
                source="event",
                created_at=iso(event_row.created_at),
            )
            tool_items[key] = existing
            items.append(existing)
            return existing
        existing.status = status
        if existing.tool is not None:
            existing.tool.status = status if status in {"running", "waiting_external", "completed", "error", "cancelled", "interrupted"} else existing.tool.status  # type: ignore[assignment]
            input_payload = first_present(data, ("tool_args", "arguments", "args"))
            if is_meaningful_payload(input_payload) and not is_meaningful_payload(existing.tool.input_payload):
                existing.tool.input_payload = input_payload
            existing.tool.output_payload = data.get("result") if "result" in data else data.get("output", existing.tool.output_payload)
            if data.get("message") or event.content:
                existing.tool.message = str(data.get("message") or event.content or "")
        return existing

    def _append_message_timeline_entry(
        self,
        timeline_entries: list[tuple[tuple[int, int, int, str, str], AgentTimelineItem]],
        *,
        run_order: dict[str, int],
        message: AiAgentMessage,
        kind: str,
        role: str | None,
        content: str,
        phase: int,
    ) -> None:
        """把消息表记录加入待排序 timeline；主要用于用户消息和事件缺失兜底。"""

        item = AgentTimelineItem(
            id=f"message-{message.id}" if kind == "message" else f"message-{message.id}-{kind}",
            session_id=message.session_id,
            run_id=message.run_id or "",
            kind=kind,  # type: ignore[arg-type]
            role=role,  # type: ignore[arg-type]
            event_index=None,
            order_index=0,
            content=content,
            status=None,
            tool=None,
            attachments=[
                AgentMessageAttachmentItem.model_validate(item)
                for item in (message.attachments_json or [])
                if isinstance(item, dict)
            ] if kind == "message" else [],
            source="message",
            created_at=iso(message.created_at),
        )
        timeline_entries.append((
            timeline_sort_key(
                run_order,
                run_id=item.run_id,
                event_index=item.event_index,
                phase=phase,
                created_at=item.created_at,
                fallback_id=item.id,
            ),
            item,
        ))

    async def _tool_attachment_summaries(self, *, session_id: str) -> dict[tuple[str, str], list[AgentMessageAttachmentItem]]:
        """按 run/tool_call_id 返回工具输出图片附件摘要，用于 timeline 缩略图展示。"""

        result = await self._session.execute(
            select(AiAgentImageAttachment)
            .where(
                AiAgentImageAttachment.session_id == session_id,
                AiAgentImageAttachment.user_id == self._user_id,
                AiAgentImageAttachment.source_kind == "tool_output",
                AiAgentImageAttachment.run_id.is_not(None),
                AiAgentImageAttachment.status == RecordStatus.ACTIVE.value,
            )
            .order_by(AiAgentImageAttachment.id.asc())
        )
        service = AgentImageAttachmentService(self._session, user_id=self._user_id)
        summaries: dict[tuple[str, str], list[AgentMessageAttachmentItem]] = {}
        for attachment in result.scalars().all():
            run_id = str(attachment.run_id or "")
            if not run_id:
                continue
            item = service._to_message_item(attachment)
            summaries.setdefault((run_id, str(attachment.tool_call_id or "")), []).append(item)
            if attachment.tool_name:
                summaries.setdefault((run_id, attachment.tool_name), []).append(item)
        return summaries

    async def _attachment_summary_lookup(self, *, session_id: str) -> dict[int, AgentMessageAttachmentItem]:
        """返回会话 active 图片附件摘要映射，供工具输入缩略图恢复。"""

        result = await self._session.execute(
            select(AiAgentImageAttachment).where(
                AiAgentImageAttachment.session_id == session_id,
                AiAgentImageAttachment.user_id == self._user_id,
                AiAgentImageAttachment.status == RecordStatus.ACTIVE.value,
            )
        )
        service = AgentImageAttachmentService(self._session, user_id=self._user_id)
        return {item.id: service._to_message_item(item) for item in result.scalars().all()}
