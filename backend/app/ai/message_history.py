"""文件功能：重建 Agent 多轮消息历史，并基于真实 usage 高水位维护请求前压缩。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.tools import RunContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent.runtime_context import AgentRuntimeContext
from app.ai.context_usage import AgentContextUsageSnapshot, usage_snapshot_from_messages
from app.ai.image_history_hydration import hydrate_agent_image_refs
from app.ai.image_refs import normalize_agent_image_ref, sanitize_message_history_image_refs
from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentRun, AiAgentSession
from app.schemas.agent import AgentContextStatusItem

DEFAULT_CONTEXT_WINDOW_TOKENS = 128_000
DEFAULT_MAX_OUTPUT_TOKENS = 32_000
DEFAULT_COMPRESSION_TARGET_RATIO = 0.25
SAFETY_MARGIN_RATIO = 0.08
MIN_SAFETY_MARGIN_TOKENS = 512

_SUMMARY_KIND = "agent-message-history-summary.v1"
_SUMMARY_PROMPT_PREFIX = "以下为较早智能体会话历史摘要，已替代压缩边界之前的原始消息："


@dataclass(slots=True)
class AgentHistoryBudget:
    """描述模型上下文窗口、输出预留和压缩触发线。"""

    context_window_tokens: int
    max_output_tokens: int
    compression_target_ratio: float
    safety_margin_tokens: int
    context_input_budget_tokens: int
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
    latest_usage: AgentContextUsageSnapshot


class AgentContextLimitProcessor:
    """Pydantic AI history processor：每次模型请求前按真实 usage 高水位压缩旧历史。"""

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
        latest_usage: AgentContextUsageSnapshot,
    ) -> None:
        """保存压缩边界和最近一次真实 usage；运行中按高水位触发压缩。"""

        self._session = session
        self._user_id = user_id
        self._session_id = session_id
        self._agent_id = agent_id
        self._budget = budget
        self._history_prefix_message_count = history_prefix_message_count
        self._history_prefix_run_ids = list(history_prefix_run_ids)
        self._existing_summary = existing_summary
        self._latest_usage = latest_usage

    @property
    def summary_json(self) -> dict[str, Any] | None:
        """返回当前已写入或继承的摘要检查点。"""

        return self._existing_summary

    @property
    def latest_usage(self) -> AgentContextUsageSnapshot:
        """返回最近一次模型响应的真实 usage。"""

        return self._latest_usage

    @property
    def session(self) -> AsyncSession:
        """返回压缩处理器绑定的数据库会话。"""

        return self._session

    @property
    def user_id(self) -> int:
        """返回压缩处理器绑定的用户 ID。"""

        return self._user_id

    @property
    def session_id(self) -> str:
        """返回压缩处理器绑定的智能体会话 ID。"""

        return self._session_id

    @property
    def agent_id(self) -> str:
        """返回压缩处理器绑定的智能体 ID。"""

        return self._agent_id

    @property
    def budget(self) -> AgentHistoryBudget:
        """返回压缩处理器使用的上下文预算。"""

        return self._budget

    @property
    def history_prefix_message_count(self) -> int:
        """返回当前压缩前缀中的模型消息数量。"""

        return self._history_prefix_message_count

    @property
    def history_prefix_run_ids(self) -> list[str]:
        """返回当前可写入持久压缩检查点的历史 run ID。"""

        return list(self._history_prefix_run_ids)

    def record_message_history(self, message_history: list[dict[str, Any]]) -> AgentContextUsageSnapshot:
        """从最新 run 消息快照中刷新真实 usage 高水位。"""

        self._latest_usage = usage_snapshot_from_messages(message_history)
        return self._latest_usage

    async def __call__(self, run_context: RunContext[Any], messages: list[ModelMessage]) -> list[ModelMessage]:
        """让处理器对象可直接作为 Pydantic AI history processor 使用。"""

        return await self.process(run_context, messages)

    async def process(
        self,
        _run_context: RunContext[Any] | None,
        messages: list[ModelMessage],
        *,
        compression_service: Any | None = None,
    ) -> list[ModelMessage]:
        """按上一轮 input + output 高水位判断是否压缩；不做本地 token 估算。"""

        if self._latest_usage.context_used_tokens <= 0:
            return messages
        if self._latest_usage.context_used_tokens < self._budget.context_input_budget_tokens:
            return messages

        suffix_start = _preserved_suffix_start(messages)
        if suffix_start <= 0:
            raise _context_limit_error()

        persistent = bool(self._history_prefix_run_ids and suffix_start >= self._history_prefix_message_count)
        if persistent:
            # 持久检查点只能覆盖 run 启动前已稳定的历史，当前 run 内容继续作为后缀保留。
            prefix = messages[: self._history_prefix_message_count]
            suffix = messages[self._history_prefix_message_count :]
        else:
            prefix = messages[:suffix_start]
            suffix = messages[suffix_start:]
        checkpoint = await self._compress_prefix(
            prefix=prefix,
            persistent=persistent,
            compression_service=compression_service,
        )
        if checkpoint is None:
            raise _context_limit_error()
        summary_messages = _summary_messages_from_checkpoint(checkpoint)
        compressed = [*summary_messages, *suffix]
        self._history_prefix_message_count = len(summary_messages)
        self._history_prefix_run_ids = []
        self._existing_summary = checkpoint
        self._latest_usage = AgentContextUsageSnapshot()
        return compressed

    async def compress_completed_messages(
        self,
        *,
        messages: list[ModelMessage],
        current_run_id: str,
        compression_service: Any | None = None,
        fail_on_error: bool = True,
    ) -> dict[str, Any]:
        """最终响应已稳定后压缩全部可见历史，并把检查点推进到当前 run。"""

        run_ids = [*self._history_prefix_run_ids, current_run_id]
        checkpoint = await self._compress_prefix(
            prefix=messages,
            persistent=True,
            compression_service=compression_service,
            checkpoint_run_ids=run_ids,
            fail_on_error=fail_on_error,
        )
        if checkpoint is None:
            return self._existing_summary or {}
        self._history_prefix_message_count = len(_summary_messages_from_checkpoint(checkpoint))
        self._history_prefix_run_ids = []
        self._existing_summary = checkpoint
        self._latest_usage = AgentContextUsageSnapshot()
        return checkpoint

    async def _compress_prefix(
        self,
        *,
        prefix: list[ModelMessage],
        persistent: bool,
        compression_service: Any | None,
        checkpoint_run_ids: list[str] | None = None,
        fail_on_error: bool = True,
    ) -> dict[str, Any] | None:
        """压缩前缀消息；优先委托模型压缩服务，缺失时使用原确定性摘要。"""

        run_ids = list(checkpoint_run_ids if checkpoint_run_ids is not None else self._history_prefix_run_ids)
        if compression_service is not None:
            return await compression_service.compress_prefix(
                prefix=prefix,
                existing_summary=self._existing_summary,
                target_tokens=self._budget.compression_target_tokens,
                persistent=persistent,
                checkpoint_run_ids=run_ids,
                fail_on_error=fail_on_error,
            )
        summary = _summarize_messages(
            prefix,
            existing_summary=self._existing_summary,
            target_tokens=self._budget.compression_target_tokens,
        )
        return (
            await self._write_summary_checkpoint(summary, checkpoint_run_ids=run_ids, compression_method="deterministic_fallback")
            if persistent and run_ids
            else _build_in_memory_summary_checkpoint(summary, self._existing_summary, compression_method="deterministic_fallback")
        )

    async def _write_summary_checkpoint(
        self,
        summary: str,
        *,
        checkpoint_run_ids: list[str] | None = None,
        compression_method: str = "deterministic_fallback",
    ) -> dict[str, Any]:
        """把压缩摘要写入 session.summary_json，并推进到本次 run 启动前的最后一个历史 run。"""

        run_ids = list(checkpoint_run_ids if checkpoint_run_ids is not None else self._history_prefix_run_ids)
        if not run_ids:
            return _build_in_memory_summary_checkpoint(summary, self._existing_summary, compression_method=compression_method)
        last_run_id = run_ids[-1]
        run_model = await self._session.get(AiAgentRun, last_run_id)
        covered_created_at = _iso(run_model.created_at) if run_model is not None else None
        checkpoint = {
            "kind": _SUMMARY_KIND,
            "summary": summary,
            "topics": [],
            "covered_until_run_id": last_run_id,
            "covered_until_created_at": covered_created_at,
            "source_run_ids": run_ids,
            "compression_method": compression_method,
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
        latest_usage=usage_snapshot_from_messages(message_json),
    )


def build_history_budget(model_config: Any, *, runtime_context: AgentRuntimeContext) -> AgentHistoryBudget:
    """根据模型配置计算真实 usage 高水位压缩触发线。"""

    _ = runtime_context
    context_window_tokens = _positive_int(getattr(model_config, "context_window_tokens", None), DEFAULT_CONTEXT_WINDOW_TOKENS)
    max_output_tokens = _positive_int(getattr(model_config, "max_output_tokens", None), DEFAULT_MAX_OUTPUT_TOKENS)
    compression_target_ratio = _bounded_float(
        getattr(model_config, "compression_target_ratio", None),
        DEFAULT_COMPRESSION_TARGET_RATIO,
        lower=0.02,
        upper=0.5,
    )
    safety_margin_tokens = max(MIN_SAFETY_MARGIN_TOKENS, ceil(context_window_tokens * SAFETY_MARGIN_RATIO))
    context_input_budget_tokens = max(0, context_window_tokens - max_output_tokens - safety_margin_tokens)
    compression_target_tokens = (
        0
        if context_input_budget_tokens <= 0
        else max(1, min(ceil(context_window_tokens * compression_target_ratio), context_input_budget_tokens))
    )
    return AgentHistoryBudget(
        context_window_tokens=context_window_tokens,
        max_output_tokens=max_output_tokens,
        compression_target_ratio=compression_target_ratio,
        safety_margin_tokens=safety_margin_tokens,
        context_input_budget_tokens=context_input_budget_tokens,
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
) -> AgentContextLimitProcessor:
    """创建请求前压缩处理器；无 usage 时处理器会保持 no-op。"""

    return AgentContextLimitProcessor(
        session=session,
        user_id=user_id,
        session_id=session_id,
        agent_id=agent_id,
        budget=budget,
        history_prefix_message_count=len(rebuilt_history.messages),
        history_prefix_run_ids=rebuilt_history.included_run_ids,
        existing_summary=rebuilt_history.summary_json,
        latest_usage=rebuilt_history.latest_usage,
    )


def build_context_status_item(
    *,
    session_id: str,
    agent_id: str,
    budget: AgentHistoryBudget,
    rebuilt_history: RebuiltAgentMessageHistory | None = None,
    message_json: list[dict[str, Any]] | None = None,
    summary_json: dict[str, Any] | None = None,
    usage_override: AgentContextUsageSnapshot | None = None,
    retained_message_count_override: int | None = None,
    compression_status: str = "idle",
    compression_method: str | None = None,
    compression_error_message: str | None = None,
) -> AgentContextStatusItem:
    """把真实 usage 和模型配置转换为前端上下文状态。"""

    if rebuilt_history is not None:
        usage = rebuilt_history.latest_usage
        summary = rebuilt_history.summary_json or {}
        retained_message_count = len(rebuilt_history.messages)
    else:
        usage = usage_snapshot_from_messages(message_json)
        summary = summary_json or {}
        retained_message_count = len(message_json or [])
    if usage_override is not None:
        usage = usage_override
    if retained_message_count_override is not None:
        retained_message_count = retained_message_count_override
    context_used_tokens = usage.context_used_tokens
    summary_available = bool(summary.get("summary"))
    normalized_method = compression_method or _compression_method_from_summary(summary, summary_available)
    return AgentContextStatusItem(
        session_id=session_id,
        agent_id=agent_id,
        compression_enabled=True,
        compression_required=context_used_tokens >= budget.context_input_budget_tokens if context_used_tokens > 0 else False,
        compression_status=_normalize_compression_status(compression_status, summary_available),
        compression_method=normalized_method,
        compression_error_message=compression_error_message,
        summary_available=summary_available,
        summary=str(summary.get("summary") or "") or None,
        topics=[str(item) for item in summary.get("topics", [])] if isinstance(summary.get("topics"), list) else [],
        summary_updated_at=str(summary.get("updated_at") or "") or None,
        context_window_tokens=budget.context_window_tokens,
        max_output_tokens=budget.max_output_tokens,
        history_token_ratio=1.0,
        compression_target_ratio=budget.compression_target_ratio,
        safety_margin_tokens=budget.safety_margin_tokens,
        current_input_tokens=usage.input_tokens,
        fixed_context_tokens=0,
        history_budget_tokens=0,
        compression_target_tokens=budget.compression_target_tokens,
        estimated_history_tokens=0,
        retained_recent_history_tokens=0,
        retained_recent_message_count=retained_message_count,
        context_input_budget_tokens=budget.context_input_budget_tokens,
        context_used_tokens=context_used_tokens,
        context_remaining_tokens=max(0, budget.context_input_budget_tokens - context_used_tokens),
        last_input_tokens=usage.input_tokens,
        last_output_tokens=usage.output_tokens,
        last_total_tokens=usage.total_tokens,
        last_reasoning_tokens=usage.reasoning_tokens,
    )


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


def _build_in_memory_summary_checkpoint(
    summary: str,
    existing_summary: dict[str, Any] | None,
    *,
    compression_method: str = "deterministic_fallback",
) -> dict[str, Any]:
    """构造仅用于当前 run 内压缩的摘要，避免误标记已覆盖的历史 run。"""

    existing_topics = existing_summary.get("topics") if isinstance(existing_summary, dict) else []
    return {
        "kind": _SUMMARY_KIND,
        "summary": summary,
        "topics": existing_topics if isinstance(existing_topics, list) else [],
        "covered_until_run_id": None,
        "covered_until_created_at": None,
        "source_run_ids": [],
        "compression_method": compression_method,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _preserved_suffix_start(messages: list[ModelMessage]) -> int:
    """定位压缩时必须保留的后缀，确保当前请求和工具调用配对不被破坏。"""

    if not messages:
        return 0
    last_index = len(messages) - 1
    last_message = messages[last_index]
    if not isinstance(last_message, ModelRequest):
        return last_index
    suffix_start = last_index
    if any(isinstance(part, ToolReturnPart | RetryPromptPart) for part in last_message.parts):
        for index in range(last_index - 1, -1, -1):
            message = messages[index]
            if isinstance(message, ModelResponse) and any(isinstance(part, ToolCallPart) for part in message.parts):
                suffix_start = index
                break
    return suffix_start


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
    """把图片引用替换为文本占位，供状态读取等非入模路径使用。"""

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


def _compression_method_from_summary(summary: dict[str, Any], summary_available: bool) -> str:
    """从摘要检查点读取压缩方式，兼容旧检查点。"""

    method = str(summary.get("compression_method") or "").strip()
    if method in {"model", "deterministic_fallback"}:
        return method
    return "deterministic_fallback" if summary_available else "none"


def _normalize_compression_status(status: str, summary_available: bool) -> str:
    """归一化上下文压缩状态；普通摘要读取时展示已压缩。"""

    if status in {"compressing", "compressed", "failed"}:
        return status
    return "compressed" if summary_available else "idle"


def _iso(value: datetime | None) -> str | None:
    """把 datetime 转换为 JSON 友好字符串。"""

    return value.isoformat() if value is not None else None
