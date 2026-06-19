"""文件功能：提供 Agent 会话 Facade 的 SSE 编码、raw SSE 解析和断线清理辅助函数。"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable
from typing import Any

from app.ai.session_facade_common import _coerce_str
from app.schemas.agent import AgentRunEvent


async def _close_async_iterator(stream: AsyncIterator[Any]) -> None:
    """关闭上游 Agno 流，确保客户端断线后不继续消费模型输出。"""

    aclose = getattr(stream, "aclose", None)
    if callable(aclose):
        await aclose()



async def _finish_shielded_cleanup(awaitable: Awaitable[Any]) -> bool:
    """保护断线清理任务；返回清理期间是否收到新的取消信号。"""

    task = asyncio.create_task(awaitable)
    try:
        await asyncio.shield(task)
        return False
    except asyncio.CancelledError:
        try:
            await task
        except BaseException:  # noqa: BLE001
            pass
        return True



def _format_sse(event: AgentRunEvent) -> bytes:
    """把统一事件模型编码为标准 SSE 文本块。"""

    return f"event: {event.event}\ndata: {event.model_dump_json()}\n\n".encode("utf-8")



def _ensure_sse_bytes(value: Any) -> bytes:
    """把 Agno background stream 返回的 SSE 字符串统一成字节。"""

    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")



def _iter_raw_sse_payloads(raw_bytes: bytes) -> list[tuple[dict[str, Any], str]]:
    """从已格式化 SSE 文本中解析 Agno raw payload，供终态兜底使用。"""

    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return []
    payloads: list[tuple[dict[str, Any], str]] = []
    for block in re.split(r"\r?\n\r?\n+", raw_text.strip()):
        if not block:
            continue
        event_name = ""
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append((payload, str(payload.get("event") or event_name)))
    return payloads



def _raw_terminal_content(payload: dict[str, Any]) -> str | None:
    """读取 raw 终态事件中的可展示内容或错误说明。"""

    for key in ("content", "error", "message"):
        value = _coerce_str(payload.get(key))
        if value:
            return value
    return None



def _format_raw_sse_error(*, run_id: str | None, session_id: str | None, message: str, code: str) -> bytes:
    """构造 Agno raw SSE 兼容的错误事件。"""

    payload = {
        "event": "RunError",
        "run_id": run_id,
        "session_id": session_id,
        "content": message,
        "error": message,
        "error_type": code,
    }
    return f"event: RunError\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")



def _stream_sse_events(events: AsyncGenerator[AgentRunEvent, None]) -> AsyncGenerator[bytes, None]:
    """把统一事件生成器转为兼容旧接口的 SSE 字节流。"""

    async def generator() -> AsyncGenerator[bytes, None]:
        async for event in events:
            yield _format_sse(event)

    return generator()
