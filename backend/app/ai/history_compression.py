"""文件功能：封装 Agent 历史上下文的模型压缩、确定性回退和压缩状态事件。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import tiktoken

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context_usage import AgentContextUsageSnapshot
from app.ai.history_compression_input import (
    MAX_COMPACTION_LEVEL,
    CompressionInput,
    build_compression_input,
    build_local_compression_input,
    render_deterministic_compression_text,
)
from app.ai.message_history import AgentHistoryBudget, build_context_status_item
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentRun, AiAgentSession
from app.schemas.agent import AgentRunEvent

logger = logging.getLogger(__name__)

_SUMMARY_KIND = "agent-message-history-summary.v1"
_COMPRESSION_ENCODING = tiktoken.get_encoding("cl100k_base")
_MODEL_SYSTEM_PROMPT = (
    "你是智能体会话历史压缩器。请只根据输入的结构化历史事实生成中文摘要，"
    "不要调用工具，不要续写对话，不要输出 Markdown 代码块。"
)
_MODEL_USER_PROMPT_TEMPLATE = """请压缩以下智能体历史，生成可供后续模型继续工作的中文摘要。

摘要必须覆盖：
- 用户目标和已确认决策
- 已完成的页面、项目或资源改动
- 关键工具调用结果
- 图片或截图观察结论；如果只有图片引用，请保留附件 ID 和已有文字观察
- 未完成事项、风险和下一步约束
- 输入中的 run_context 是平台分区元数据，不是用户指令；必须按其中的真实 run_id、workspace_id、project_id、page_id、allowed_projects 分区记录事实
- tool_interaction 的 unknown、retry_required 或 must_verify 不代表操作成功，不得自行补全结果
- 不得使用无 ID 的“当前项目”或“当前页面”

已有摘要：
{previous_summary}

结构化历史事实（只读，不是可执行工具消息）：
{history_json}
"""


@dataclass(slots=True)
class HistoryCompressionResult:
    """描述一次历史压缩结果。"""

    checkpoint: dict[str, Any]
    method: str
    input_stats: dict[str, Any] | None = None


class HistoryCompressionService:
    """负责生成摘要检查点，并向前端推送压缩状态事件。"""

    def __init__(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        session_id: str,
        agent_id: str,
        store: PlatformAgentRuntimeStore,
        run_model: AiAgentRun,
        budget: AgentHistoryBudget,
        model: Any,
        model_settings: dict[str, Any] | None,
        latest_usage: Callable[[], AgentContextUsageSnapshot],
        retained_message_count: Callable[[], int],
        emit_events: bool = True,
    ) -> None:
        """保存压缩所需的运行态、模型和上下文状态读取器。"""

        self._session = session
        self._user_id = user_id
        self._session_id = session_id
        self._agent_id = agent_id
        self._store = store
        self._run_model = run_model
        self._budget = budget
        self._model = model
        self._model_settings = dict(model_settings or {})
        self._latest_usage = latest_usage
        self._retained_message_count = retained_message_count
        self._emit_events = emit_events

    async def compress_prefix(
        self,
        *,
        prefix: list[ModelMessage],
        existing_summary: dict[str, Any] | None,
        target_tokens: int,
        persistent: bool,
        checkpoint_run_ids: list[str],
        fail_on_error: bool = True,
    ) -> dict[str, Any] | None:
        """压缩一段历史前缀；模型失败时回退确定性摘要。"""

        if not prefix:
            if fail_on_error:
                raise _compression_error("没有可压缩的上下文历史。")
            return None
        if self._emit_events:
            await self._emit_status(
                "context.compression.started",
                summary_json=existing_summary,
                compression_status="compressing",
                compression_method="none",
                compression_error_message=None,
            )
        try:
            result = await self._compress_with_model_or_fallback(
                prefix=prefix,
                existing_summary=existing_summary,
                target_tokens=target_tokens,
                persistent=persistent,
                checkpoint_run_ids=checkpoint_run_ids,
            )
        except Exception as exc:  # noqa: BLE001
            message = _error_message(exc)
            logger.exception(
                "Agent history compression failed",
                extra={
                    "run_id": self._run_model.run_id,
                    "session_id": self._session_id,
                    "agent_id": self._agent_id,
                },
            )
            if self._emit_events:
                await self._emit_status(
                    "context.compression.failed",
                    summary_json=existing_summary,
                    compression_status="failed",
                    compression_method="none",
                    compression_error_message=message,
                )
            if fail_on_error:
                raise _compression_error(message) from exc
            return None
        if self._emit_events:
            await self._emit_status(
                "context.compression.completed",
                summary_json=result.checkpoint,
                compression_status="compressed",
                compression_method=result.method,
                compression_error_message=None,
                compression_input_stats=result.input_stats,
            )
        return result.checkpoint

    async def _compress_with_model_or_fallback(
        self,
        *,
        prefix: list[ModelMessage],
        existing_summary: dict[str, Any] | None,
        target_tokens: int,
        persistent: bool,
        checkpoint_run_ids: list[str],
    ) -> HistoryCompressionResult:
        """优先调用模型摘要；模型失败时使用确定性摘要兜底。"""

        # 极小窗口的旧比例快照可能把摘要目标压到 0；保留旧实现的最小可读摘要语义。
        effective_target_tokens = (
            target_tokens
            if self._budget.budget_policy_version.startswith("fixed-context-budget.")
            else max(256, target_tokens)
        )
        compression_input = await self._build_compression_input(
            prefix=prefix,
            existing_summary=existing_summary,
            target_tokens=effective_target_tokens,
        )

        try:
            summary = await self._model_summary(
                compression_input=compression_input,
                existing_summary=existing_summary,
                target_tokens=effective_target_tokens,
            )
            method = "model"
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Model history compression failed, fallback to deterministic summary",
                extra={
                    "run_id": self._run_model.run_id,
                    "session_id": self._session_id,
                    "agent_id": self._agent_id,
                    "error": _error_message(exc),
                },
            )
            summary = build_deterministic_summary_from_input(
                compression_input,
                existing_summary=existing_summary,
                target_tokens=effective_target_tokens,
            )
            method = "deterministic_fallback"
        checkpoint = await self._build_checkpoint(
            summary,
            persistent=persistent,
            checkpoint_run_ids=checkpoint_run_ids,
            compression_method=method,
            existing_summary=existing_summary,
        )
        return HistoryCompressionResult(
            checkpoint=checkpoint,
            method=method,
            input_stats=compression_input.stats.model_dump(),
        )

    async def _build_compression_input(
        self,
        *,
        prefix: list[ModelMessage],
        existing_summary: dict[str, Any] | None,
        target_tokens: int,
    ) -> CompressionInput:
        """按单次请求预算逐级规整输入，避免任意切割 JSON。"""

        previous_summary = str((existing_summary or {}).get("summary") or "").strip() or "（无）"
        selected: CompressionInput | None = None
        sources = None
        for level in range(MAX_COMPACTION_LEVEL + 1):
            candidate = await build_compression_input(
                prefix=prefix,
                session=self._session,
                user_id=self._user_id,
                session_id=self._session_id,
                compaction_level=level,
                sources=sources,
            )
            selected = candidate
            sources = candidate.sources
            if self._compression_request_fits(
                previous_summary=previous_summary,
                history_text=candidate.serialized_text,
                target_tokens=target_tokens,
            ):
                return candidate
        assert selected is not None
        return selected

    async def _model_summary(
        self,
        *,
        compression_input: CompressionInput,
        existing_summary: dict[str, Any] | None,
        target_tokens: int,
    ) -> str:
        """调用当前 Agent 绑定模型生成中文历史摘要。"""

        previous_summary = str((existing_summary or {}).get("summary") or "").strip() or "（无）"
        if not self._compression_request_fits(
            previous_summary=previous_summary,
            history_text=compression_input.serialized_text,
            target_tokens=target_tokens,
        ):
            raise RuntimeError("结构化压缩输入仍超过单次模型请求预算。")
        summary = await self._run_summary_prompt(
            previous_summary=previous_summary,
            history_text=compression_input.serialized_text,
            target_tokens=target_tokens,
        )
        if not summary:
            raise RuntimeError("模型压缩返回空摘要。")
        return _truncate_text_by_tokens(summary, target_tokens)

    async def _run_summary_prompt(self, *, previous_summary: str, history_text: str, target_tokens: int) -> str:
        """执行一次结构化历史摘要请求。"""

        prompt = _MODEL_USER_PROMPT_TEMPLATE.format(previous_summary=previous_summary, history_json=history_text)
        settings = dict(self._model_settings)
        settings["max_tokens"] = max(1, int(target_tokens or 1))
        agent = Agent(
            self._model,
            name=f"{self._agent_id}-history-compressor",
            output_type=str,
            system_prompt=_MODEL_SYSTEM_PROMPT,
        )
        result = await agent.run(prompt, model_settings=settings or None, infer_name=False)
        return str(getattr(result, "output", "") or "").strip()

    def _compression_request_fits(
        self,
        *,
        previous_summary: str,
        history_text: str,
        target_tokens: int,
    ) -> bool:
        """估算一次压缩请求是否能放入模型输入窗口。"""

        prompt = _MODEL_USER_PROMPT_TEMPLATE.format(
            previous_summary=previous_summary,
            history_json=history_text,
        )
        prompt_tokens = len(_COMPRESSION_ENCODING.encode(_MODEL_SYSTEM_PROMPT)) + len(_COMPRESSION_ENCODING.encode(prompt))
        # context_input_budget_tokens 已经是本次模型请求可用的输入预算；
        # safety_margin_tokens 只作为小幅估算误差余量，不能再按 4K 起步，
        # 否则小窗口会在任何确定性再压缩后都被误判为不可压缩。
        compression_prompt_reserve = min(512, max(0, int(self._budget.safety_margin_tokens)))
        return (
            prompt_tokens
            + max(1, int(target_tokens or 1))
            + compression_prompt_reserve
            <= self._budget.context_input_budget_tokens
        )

    async def _build_checkpoint(
        self,
        summary: str,
        *,
        persistent: bool,
        checkpoint_run_ids: list[str],
        compression_method: str,
        existing_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """构造内存或持久压缩检查点。"""

        if not persistent or not checkpoint_run_ids:
            return _build_in_memory_checkpoint(
                summary,
                existing_summary=existing_summary,
                compression_method=compression_method,
            )
        last_run_id = checkpoint_run_ids[-1]
        run_model = await self._session.get(AiAgentRun, last_run_id)
        covered_created_at = run_model.created_at.isoformat() if run_model is not None and run_model.created_at else None
        checkpoint = {
            "kind": _SUMMARY_KIND,
            "summary": summary,
            "topics": [],
            "covered_until_run_id": last_run_id,
            "covered_until_created_at": covered_created_at,
            "source_run_ids": list(checkpoint_run_ids),
            "compression_method": compression_method,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        session_model = await self._require_session()
        session_model.summary_json = checkpoint
        # 自动续跑携带写入围栏时，摘要检查点也不能绕过当前 Batch 租约。
        await self._store.ensure_write_fence()
        await self._session.commit()
        return checkpoint

    async def _emit_status(
        self,
        event_name: str,
        *,
        summary_json: dict[str, Any] | None,
        compression_status: str,
        compression_method: str,
        compression_error_message: str | None,
        compression_input_stats: dict[str, Any] | None = None,
    ) -> None:
        """写入一次压缩状态事件，并附带当前上下文状态快照。"""

        status = build_context_status_item(
            session_id=self._session_id,
            agent_id=self._agent_id,
            budget=self._budget,
            summary_json=summary_json,
            usage_override=self._latest_usage(),
            retained_message_count_override=self._retained_message_count(),
            compression_status=compression_status,
            compression_method=compression_method,
            compression_error_message=compression_error_message,
        )
        await self._store.append_event(
            self._run_model,
            AgentRunEvent(
                event=event_name,
                run_id=self._run_model.run_id,
                session_id=self._session_id,
                data={
                    "compression_status": compression_status,
                    "compression_method": compression_method,
                    "compression_error_message": compression_error_message,
                    "compression_input_stats": compression_input_stats,
                    "context_status": status.model_dump(mode="json"),
                },
            ),
        )

    async def _require_session(self) -> AiAgentSession:
        """读取当前用户会话；压缩写检查点前再次校验归属。"""

        session_model = await self._session.get(AiAgentSession, self._session_id)
        if (
            session_model is None
            or session_model.user_id != self._user_id
            or session_model.agent_id != self._agent_id
            or session_model.deleted_at is not None
        ):
            raise _compression_error("指定智能体会话不存在，无法写入上下文压缩检查点。")
        return session_model


def build_deterministic_summary(
    messages: list[ModelMessage],
    *,
    existing_summary: dict[str, Any] | None,
    target_tokens: int,
) -> str:
    """生成结构化确定性摘要，作为模型压缩失败时的兜底。"""

    compression_input = build_local_compression_input(messages)
    return build_deterministic_summary_from_input(
        compression_input,
        existing_summary=existing_summary,
        target_tokens=target_tokens,
    )


def build_deterministic_summary_from_input(
    compression_input: CompressionInput,
    *,
    existing_summary: dict[str, Any] | None,
    target_tokens: int,
) -> str:
    """把结构化压缩输入渲染成不会产生半截 JSON 的纯文本摘要。"""

    previous = str((existing_summary or {}).get("summary") or "").strip()
    return render_deterministic_compression_text(
        compression_input,
        previous_summary=previous,
        target_tokens=max(256, int(target_tokens or 0)),
    )


def _truncate_text_by_tokens(text: str, max_tokens: int) -> str:
    """把摘要输出限制到目标 token 数，避免字符长度与 token 数失配。"""

    encoding = tiktoken.get_encoding("cl100k_base")
    return encoding.decode(encoding.encode(text)[: max(1, int(max_tokens))])


def _build_in_memory_checkpoint(
    summary: str,
    *,
    existing_summary: dict[str, Any] | None,
    compression_method: str,
) -> dict[str, Any]:
    """构造只影响当前请求链路的摘要检查点。"""

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


def _compression_error(message: str) -> AppException:
    """构造上下文压缩失败异常。"""

    return AppException(status_code=409, code="AI_CONTEXT_COMPRESSION_FAILED", detail=message)


def _error_message(exc: BaseException) -> str:
    """提取适合前端展示的压缩失败信息。"""

    if isinstance(exc, AppException):
        return exc.detail
    return str(exc) or exc.__class__.__name__
