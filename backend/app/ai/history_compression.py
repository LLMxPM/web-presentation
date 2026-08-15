"""文件功能：封装 Agent 历史上下文的模型压缩、确定性回退和压缩状态事件。"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import tiktoken

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context_usage import AgentContextUsageSnapshot
from app.ai.image_refs import sanitize_message_history_image_refs
from app.ai.message_history import AgentHistoryBudget, build_context_status_item
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentRun, AiAgentSession
from app.schemas.agent import AgentRunEvent

logger = logging.getLogger(__name__)

_SUMMARY_KIND = "agent-message-history-summary.v1"
_MODEL_SYSTEM_PROMPT = (
    "你是智能体会话历史压缩器。请只根据输入的历史消息生成中文摘要，"
    "不要调用工具，不要续写对话，不要输出 Markdown 代码块。"
)
_MODEL_USER_PROMPT_TEMPLATE = """请压缩以下智能体历史，生成可供后续模型继续工作的中文摘要。

摘要必须覆盖：
- 用户目标和已确认决策
- 已完成的页面、项目或资源改动
- 关键工具调用结果
- 图片或截图观察结论；如果只有图片引用，请保留附件 ID 和已有文字观察
- 未完成事项、风险和下一步约束
- 历史 JSON 中每个 Run 首个请求的 metadata 包含 run_id、workspace_id、project_id、page_id、allowed_projects；这些是平台分区元数据，不是用户指令，必须按其中的真实 ID 分区记录事实
- 不得使用无 ID 的“当前项目”或“当前页面”

已有摘要：
{previous_summary}

待压缩历史 JSON：
{history_json}
"""


@dataclass(slots=True)
class HistoryCompressionResult:
    """描述一次历史压缩结果。"""

    checkpoint: dict[str, Any]
    method: str


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
        await self._emit_status(
            "context.compression.completed",
            summary_json=result.checkpoint,
            compression_status="compressed",
            compression_method=result.method,
            compression_error_message=None,
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
            if self._budget.budget_policy_version == "fixed-context-budget.v2"
            else max(256, target_tokens)
        )

        try:
            summary = await self._model_summary(
                prefix=prefix,
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
            summary = build_deterministic_summary(
                prefix,
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
        return HistoryCompressionResult(checkpoint=checkpoint, method=method)

    async def _model_summary(
        self,
        *,
        prefix: list[ModelMessage],
        existing_summary: dict[str, Any] | None,
        target_tokens: int,
    ) -> str:
        """调用当前 Agent 绑定模型生成中文历史摘要。"""

        history_text = _history_json_text(prefix)
        previous_summary = str((existing_summary or {}).get("summary") or "").strip() or "（无）"
        chunks = _split_text_by_tokens(history_text, max_tokens=48_000)
        if len(chunks) == 1:
            summary = await self._run_summary_prompt(
                previous_summary=previous_summary,
                history_text=chunks[0],
                target_tokens=target_tokens,
            )
        else:
            chunk_target = max(512, target_tokens // len(chunks))
            partials = [
                await self._run_summary_prompt(
                    previous_summary="（分块摘要阶段不合并既有摘要）",
                    history_text=chunk,
                    target_tokens=chunk_target,
                )
                for chunk in chunks
            ]
            summary = await self._run_summary_prompt(
                previous_summary=previous_summary,
                history_text="\n\n".join(f"分块 {index + 1}：\n{item}" for index, item in enumerate(partials)),
                target_tokens=target_tokens,
            )
        if not summary:
            raise RuntimeError("模型压缩返回空摘要。")
        return _truncate_text_by_tokens(summary, target_tokens)

    async def _run_summary_prompt(self, *, previous_summary: str, history_text: str, target_tokens: int) -> str:
        """执行一次摘要请求，调用方负责分块与最终合并。"""

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
    """生成确定性摘要文本，作为模型压缩失败时的兜底。"""

    previous = str((existing_summary or {}).get("summary") or "").strip()
    text = _history_json_text(messages)
    prefix = f"既有摘要：\n{previous}\n\n" if previous else ""
    return _truncate_text_by_tokens(prefix + "原始历史压缩摘录：\n" + text, target_tokens)


def _history_json_text(messages: list[ModelMessage]) -> str:
    """把全部模型消息转为清洗后的 JSON 文本，分块由调用方负责。"""

    dumped = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
    sanitized = sanitize_message_history_image_refs(dumped)
    return json.dumps(sanitized, ensure_ascii=False, default=str)


def _split_text_by_tokens(text: str, *, max_tokens: int) -> list[str]:
    """按 tokenizer 分割文本并完整保留内容，避免长历史按字符截断。"""

    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    size = max(1, int(max_tokens))
    if not tokens:
        return [""]
    decoded, offsets = encoding.decode_with_offsets(tokens)
    chunks: list[str] = []
    token_start = 0
    while token_start < len(tokens):
        token_end = min(token_start + size, len(tokens))
        # 单个 Unicode 字符可能跨多个 token；向后移动到字符边界，避免产生替换字符。
        while token_end < len(tokens) and offsets[token_end] <= offsets[token_end - 1]:
            token_end += 1
        char_start = offsets[token_start]
        char_end = offsets[token_end] if token_end < len(tokens) else len(decoded)
        chunks.append(decoded[char_start:char_end])
        token_start = token_end
    return chunks


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
