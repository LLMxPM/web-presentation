"""文件功能：重建 Agent 多轮消息历史，维护压缩检查点并提供请求前上下文预算守卫。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelRequest, SystemPromptPart
from pydantic_ai.tools import RunContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent.runtime_context import AgentRuntimeContext
from app.ai.history_policy import (
    DEFAULT_COMPRESSION_TARGET_RATIO,
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    MIN_SAFETY_MARGIN_TOKENS,
    SAFETY_MARGIN_RATIO,
    estimate_text_tokens,
)
from app.ai.image_history_hydration import hydrate_agent_image_refs
from app.ai.image_refs import normalize_agent_image_ref, sanitize_message_history_image_refs
from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentRun, AiAgentSession
from app.schemas.agent import AgentContextStatusItem

_SUMMARY_KIND = "agent-message-history-summary.v1"
_SUMMARY_PROMPT_PREFIX = "以下为较早智能体会话历史摘要，已替代压缩边界之前的原始消息："


@dataclass(slots=True)
class AgentHistoryBudget:
    """描述一次模型请求可用于历史消息的粗略预算。"""

    context_window_tokens: int
    max_output_tokens: int
    compression_target_ratio: float
    safety_margin_tokens: int
    fixed_context_tokens: int
    history_budget_tokens: int
    compression_target_tokens: int


@dataclass(slots=True)
class RebuiltAgentMessageHistory:
    """描述从 session delta 重建出的模型历史和压缩边界。"""

    messages: list[ModelMessage]
    message_json: list[dict[str, Any]]
    included_run_ids: list[str]
    covered_until_run_id: str | None
    covered_until_created_at: str | None
    summary_json: dict[str, Any] | None
    estimated_tokens: int


class AgentContextLimitProcessor:
    """Pydantic AI history processor：每次模型请求前按预算压缩旧历史。"""

    def __init__(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        session_id: str,
        agent_id: str,
        budget: AgentHistoryBudget,
        history_prefix_message_count: int,
        history_prefix_run_ids: list[str],
        existing_summary: dict[str, Any] | None,
    ) -> None:
        """保存本次 run 启动前的历史边界；运行中只压缩该边界内的旧历史。"""

        self._session = session
        self._user_id = user_id
        self._session_id = session_id
        self._agent_id = agent_id
        self._budget = budget
        self._history_prefix_message_count = history_prefix_message_count
        self._history_prefix_run_ids = list(history_prefix_run_ids)
        self._existing_summary = existing_summary

    async def process(self, _run_context: RunContext[Any], messages: list[ModelMessage]) -> list[ModelMessage]:
        """检查请求消息体大小；超预算时只压缩 run 启动前的历史前缀。"""

        if self._estimate_request_tokens(messages) <= self._budget.history_budget_tokens:
            return messages
        if self._history_prefix_message_count <= 0 or not self._history_prefix_run_ids:
            raise _context_limit_error()

        prefix = messages[: self._history_prefix_message_count]
        suffix = messages[self._history_prefix_message_count :]
        summary = _summarize_messages(
            prefix,
            existing_summary=self._existing_summary,
            target_tokens=self._budget.compression_target_tokens,
        )
        checkpoint = await self._write_summary_checkpoint(summary)
        summary_messages = _summary_messages_from_checkpoint(checkpoint)
        compressed = [*summary_messages, *suffix]
        self._history_prefix_message_count = len(summary_messages)
        self._existing_summary = checkpoint

        if self._estimate_request_tokens(compressed) > self._budget.history_budget_tokens:
            raise _context_limit_error()
        return compressed

    async def _write_summary_checkpoint(self, summary: str) -> dict[str, Any]:
        """把压缩摘要写入 session.summary_json，并推进到本次 run 启动前的最后一个历史 run。"""

        last_run_id = self._history_prefix_run_ids[-1]
        run_model = await self._session.get(AiAgentRun, last_run_id)
        covered_created_at = _iso(run_model.created_at) if run_model is not None else None
        checkpoint = {
            "kind": _SUMMARY_KIND,
            "summary": summary,
            "topics": [],
            "covered_until_run_id": last_run_id,
            "covered_until_created_at": covered_created_at,
            "source_run_ids": list(self._history_prefix_run_ids),
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        session_model = await _require_session(
            self._session,
            user_id=self._user_id,
            session_id=self._session_id,
            agent_id=self._agent_id,
        )
        session_model.summary_json = checkpoint
        await self._session.commit()
        return checkpoint

    def _estimate_request_tokens(self, messages: list[ModelMessage]) -> int:
        """估算完整请求 token，包含固定运行时上下文预留。"""

        return estimate_message_tokens(messages) + self._budget.fixed_context_tokens


async def rebuild_agent_message_history(
    *,
    session: AsyncSession,
    user_id: int,
    session_id: str,
    agent_id: str,
    include_run_id: str | None = None,
    exclude_run_id: str | None = None,
    hydrate_images: bool = True,
) -> RebuiltAgentMessageHistory:
    """按 session run 顺序拼接 delta；有压缩检查点时跳过已覆盖 run。"""

    session_model = await _require_session(session, user_id=user_id, session_id=session_id, agent_id=agent_id)
    checkpoint = _normalize_summary_checkpoint(session_model.summary_json)
    result = await session.execute(
        select(AiAgentRun)
        .where(
            AiAgentRun.session_id == session_id,
            AiAgentRun.agent_id == agent_id,
            AiAgentRun.user_id == user_id,
        )
        .order_by(AiAgentRun.created_at.asc(), AiAgentRun.run_id.asc())
    )
    message_json: list[dict[str, Any]] = []
    included_run_ids: list[str] = []
    if checkpoint is not None:
        message_json.extend(_summary_message_json_from_checkpoint(checkpoint))
    for run_model in result.scalars().all():
        if exclude_run_id is not None and run_model.run_id == exclude_run_id:
            continue
        if run_model.run_id != include_run_id and run_model.status in {"pending", "running", "cancelling"}:
            continue
        if checkpoint is not None and _is_run_covered_by_checkpoint(run_model, checkpoint):
            continue
        delta = run_model.message_history_json if isinstance(run_model.message_history_json, list) else []
        if not delta:
            continue
        message_json.extend(_message_dicts(delta))
        included_run_ids.append(run_model.run_id)
    covered_until_run_id = str(checkpoint.get("covered_until_run_id") or "") if checkpoint else ""
    covered_until_created_at = str(checkpoint.get("covered_until_created_at") or "") if checkpoint else ""
    validated_message_json = (
        await hydrate_agent_image_refs(
            session=session,
            user_id=user_id,
            session_id=session_id,
            message_json=message_json,
        )
        if hydrate_images
        else _replace_agent_image_refs_with_placeholders(message_json)
    )
    return RebuiltAgentMessageHistory(
        messages=_validate_message_json(validated_message_json),
        message_json=message_json,
        included_run_ids=included_run_ids,
        covered_until_run_id=covered_until_run_id or None,
        covered_until_created_at=covered_until_created_at or None,
        summary_json=checkpoint,
        estimated_tokens=estimate_message_json_tokens(message_json),
    )


def build_history_budget(model_config: Any, *, runtime_context: AgentRuntimeContext) -> AgentHistoryBudget:
    """根据模型配置和固定运行时上下文估算历史可用预算。"""

    context_window_tokens = _positive_int(getattr(model_config, "context_window_tokens", None), DEFAULT_CONTEXT_WINDOW_TOKENS)
    max_output_tokens = _positive_int(getattr(model_config, "max_output_tokens", None), DEFAULT_MAX_OUTPUT_TOKENS)
    compression_target_ratio = _bounded_float(
        getattr(model_config, "compression_target_ratio", None),
        DEFAULT_COMPRESSION_TARGET_RATIO,
        lower=0.02,
        upper=0.5,
    )
    safety_margin_tokens = max(MIN_SAFETY_MARGIN_TOKENS, ceil(context_window_tokens * SAFETY_MARGIN_RATIO))
    fixed_context_tokens = estimate_text_tokens(
        "\n".join(
            str(item or "")
            for item in (
                runtime_context.page_content,
                runtime_context.component_code,
                runtime_context.page_title,
                runtime_context.component_name,
            )
        )
    )
    history_budget_tokens = max(0, context_window_tokens - max_output_tokens - safety_margin_tokens - fixed_context_tokens)
    compression_target_tokens = (
        0
        if history_budget_tokens <= 0
        else max(1, min(ceil(context_window_tokens * compression_target_ratio), history_budget_tokens))
    )
    return AgentHistoryBudget(
        context_window_tokens=context_window_tokens,
        max_output_tokens=max_output_tokens,
        compression_target_ratio=compression_target_ratio,
        safety_margin_tokens=safety_margin_tokens,
        fixed_context_tokens=fixed_context_tokens,
        history_budget_tokens=history_budget_tokens,
        compression_target_tokens=compression_target_tokens,
    )


def build_context_limit_processor(
    *,
    session: AsyncSession,
    user_id: int,
    session_id: str,
    agent_id: str,
    budget: AgentHistoryBudget,
    rebuilt_history: RebuiltAgentMessageHistory,
) -> Any | None:
    """创建请求前压缩处理器；没有旧历史时不需要处理器。"""

    if not rebuilt_history.messages:
        return None
    processor = AgentContextLimitProcessor(
        session=session,
        user_id=user_id,
        session_id=session_id,
        agent_id=agent_id,
        budget=budget,
        history_prefix_message_count=len(rebuilt_history.messages),
        history_prefix_run_ids=rebuilt_history.included_run_ids,
        existing_summary=rebuilt_history.summary_json,
    )

    async def process(run_context: RunContext[Any], messages: list[ModelMessage]) -> list[ModelMessage]:
        """Pydantic AI history processor 包装函数，显式声明 RunContext 参数。"""

        return await processor.process(run_context, messages)

    return process


def build_context_status_item(
    *,
    session_id: str,
    agent_id: str,
    budget: AgentHistoryBudget,
    rebuilt_history: RebuiltAgentMessageHistory,
) -> AgentContextStatusItem:
    """把重建历史和预算转换为前端上下文状态。"""

    estimated = rebuilt_history.estimated_tokens + budget.fixed_context_tokens
    summary = rebuilt_history.summary_json or {}
    return AgentContextStatusItem(
        session_id=session_id,
        agent_id=agent_id,
        compression_enabled=True,
        compression_required=estimated > budget.history_budget_tokens,
        summary_available=bool(summary.get("summary")),
        summary=str(summary.get("summary") or "") or None,
        topics=[str(item) for item in summary.get("topics", [])] if isinstance(summary.get("topics"), list) else [],
        summary_updated_at=str(summary.get("updated_at") or "") or None,
        context_window_tokens=budget.context_window_tokens,
        max_output_tokens=budget.max_output_tokens,
        history_token_ratio=1.0,
        compression_target_ratio=budget.compression_target_ratio,
        safety_margin_tokens=budget.safety_margin_tokens,
        current_input_tokens=0,
        fixed_context_tokens=budget.fixed_context_tokens,
        history_budget_tokens=budget.history_budget_tokens,
        compression_target_tokens=budget.compression_target_tokens,
        estimated_history_tokens=estimated,
        retained_recent_history_tokens=rebuilt_history.estimated_tokens,
        retained_recent_message_count=len(rebuilt_history.messages),
    )


def estimate_message_tokens(messages: list[ModelMessage]) -> int:
    """估算 Pydantic AI 消息 token 数，用于预算守卫。"""

    dumped = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
    sanitized = sanitize_message_history_image_refs(dumped if isinstance(dumped, list) else [])
    return estimate_message_json_tokens(sanitized if isinstance(sanitized, list) else [])


def estimate_message_json_tokens(messages: list[dict[str, Any]]) -> int:
    """估算 JSON 消息 token 数；保留图片和工具结果对预算的影响。"""

    if not messages:
        return 0
    return estimate_text_tokens(json.dumps(messages, ensure_ascii=False, default=str))


def _summarize_messages(messages: list[ModelMessage], *, existing_summary: dict[str, Any] | None, target_tokens: int) -> str:
    """生成压缩摘要；当前使用确定性文本摘要，避免额外模型调用导致递归上下文问题。"""

    previous = str((existing_summary or {}).get("summary") or "").strip()
    dumped = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
    sanitized = sanitize_message_history_image_refs(dumped)
    text = json.dumps(sanitized, ensure_ascii=False, default=str)
    prefix = f"既有摘要：\n{previous}\n\n" if previous else ""
    limit = max(600, target_tokens * 3)
    return (prefix + "原始历史压缩摘录：\n" + text)[:limit]


def _summary_messages_from_checkpoint(checkpoint: dict[str, Any]) -> list[ModelMessage]:
    """把检查点转换为模型可接收的 system summary 消息。"""

    return _validate_message_json(_summary_message_json_from_checkpoint(checkpoint))


def _summary_message_json_from_checkpoint(checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    """把检查点转换为可序列化消息 JSON。"""

    summary = str(checkpoint.get("summary") or "").strip()
    if not summary:
        return []
    message = ModelRequest(
        parts=[
            SystemPromptPart(
                content=f"{_SUMMARY_PROMPT_PREFIX}\n{summary}",
            )
        ]
    )
    dumped = ModelMessagesTypeAdapter.dump_python([message], mode="json")
    return dumped if isinstance(dumped, list) else []


def _normalize_summary_checkpoint(value: Any) -> dict[str, Any] | None:
    """读取有效的压缩检查点。"""

    if not isinstance(value, dict) or value.get("kind") != _SUMMARY_KIND:
        return None
    if not str(value.get("summary") or "").strip():
        return None
    return dict(value)


def _is_run_covered_by_checkpoint(run_model: AiAgentRun, checkpoint: dict[str, Any]) -> bool:
    """判断 run delta 是否已经被摘要覆盖。"""

    covered_run_id = str(checkpoint.get("covered_until_run_id") or "").strip()
    covered_created_at = _parse_datetime(checkpoint.get("covered_until_created_at"))
    if not covered_run_id:
        return False
    if run_model.run_id == covered_run_id:
        return True
    if covered_created_at is None or run_model.created_at is None:
        return False
    run_created_at = _align_datetime(run_model.created_at, covered_created_at)
    if run_created_at < covered_created_at:
        return True
    if run_created_at == covered_created_at and run_model.run_id <= covered_run_id:
        return True
    return False


async def _require_session(session: AsyncSession, *, user_id: int, session_id: str, agent_id: str) -> AiAgentSession:
    """读取当前用户可见 session；不存在时抛出平台异常。"""

    result = await session.execute(
        select(AiAgentSession).where(
            AiAgentSession.session_id == session_id,
            AiAgentSession.agent_id == agent_id,
            AiAgentSession.user_id == user_id,
            AiAgentSession.deleted_at.is_(None),
        )
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise AppException(status_code=404, code="AI_SESSION_NOT_FOUND", detail="指定智能体会话不存在。")
    return model


def _validate_message_json(messages: list[dict[str, Any]]) -> list[ModelMessage]:
    """把消息 JSON 校验为 Pydantic AI 消息对象。"""

    if not messages:
        return []
    return list(ModelMessagesTypeAdapter.validate_python(messages))


def _message_dicts(value: list[Any]) -> list[dict[str, Any]]:
    """过滤非 dict 消息，避免坏数据污染重建链路。"""

    return [dict(item) for item in value if isinstance(item, dict)]


def _replace_agent_image_refs_with_placeholders(value: Any) -> Any:
    """把图片引用替换为文本占位，供非入模的历史估算路径使用。"""

    if isinstance(value, dict):
        ref = normalize_agent_image_ref(value)
        if ref is not None:
            name = str(ref.get("original_name") or "图片")
            return f"[图片引用：{name}]"
        return {str(key): _replace_agent_image_refs_with_placeholders(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_replace_agent_image_refs_with_placeholders(item) for item in value]
    return value


def _parse_datetime(value: Any) -> datetime | None:
    """解析检查点时间游标。"""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _align_datetime(value: datetime, reference: datetime) -> datetime:
    """对齐 aware/naive datetime，兼容测试数据库返回的朴素时间。"""

    if value.tzinfo is None and reference.tzinfo is not None:
        return value.replace(tzinfo=reference.tzinfo)
    if value.tzinfo is not None and reference.tzinfo is None:
        return value.replace(tzinfo=None)
    return value


def _positive_int(value: Any, fallback: int) -> int:
    """把配置值归一为正整数。"""

    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return fallback
    return normalized if normalized > 0 else fallback


def _bounded_float(value: Any, fallback: float, *, lower: float, upper: float) -> float:
    """把比例值约束到指定范围。"""

    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return fallback
    return min(upper, max(lower, normalized))


def _context_limit_error() -> AppException:
    """构造上下文超限异常。"""

    return AppException(
        status_code=409,
        code="AI_CONTEXT_LIMIT_EXCEEDED",
        detail="当前会话上下文超过模型可用窗口，已尝试压缩但仍无法安全提交，请新建会话或减少输入后重试。",
    )


def _iso(value: datetime | None) -> str | None:
    """把 datetime 转换为 JSON 友好字符串。"""

    return value.isoformat() if value is not None else None
