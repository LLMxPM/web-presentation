"""文件功能：平台运行态事件的 SSE 编码、进程内订阅推送与回放订阅流。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from time import monotonic
from typing import TYPE_CHECKING, Protocol

from app.schemas.agent import AgentRunEvent

if TYPE_CHECKING:
    from app.ai.platform_runtime import PlatformAgentRuntimeStore

# 外部页面任务会在完成后追加 run.continued 或终态事件，因此 waiting_external
# 不能被视为 SSE 结束，订阅需持续等待自动续跑结果。
STREAM_END_EVENTS = {"run.completed", "run.cancelled", "run.error", "run.paused"}

_EVENT_POLL_INTERVAL_SECONDS = 1.0
_SSE_KEEPALIVE_INTERVAL_SECONDS = 30.0

_SUBSCRIBERS: dict[str, set[asyncio.Queue[AgentRunEvent | None]]] = {}
_LIVE_RUN_ACTIVITY_VERSIONS: dict[str, int] = {}


class _RunEventReplaySource(Protocol):
    """回放订阅所需的最小 store 接口，避免与持久化模块形成运行时环。"""

    async def replay_events(self, *, run_id: str, event_index: int) -> list[AgentRunEvent]: ...

    async def get_run_status(self, *, run_id: str) -> str | None: ...


def encode_sse_event(event: AgentRunEvent) -> bytes:
    """把平台事件编码为 SSE 数据块。"""

    return f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n".encode("utf-8")


def get_live_run_activity_version(run_id: str) -> int:
    """返回当前进程内 run 的活动版本，供模型或工具等待逻辑识别成员事件心跳。"""

    return _LIVE_RUN_ACTIVITY_VERSIONS.get(run_id, 0)


def update_live_run_activity(run_id: str, event: AgentRunEvent) -> None:
    """成功追加事件后推进活动版本；流结束时清理，避免长期持有已结束 run。"""

    if event.event in STREAM_END_EVENTS:
        _LIVE_RUN_ACTIVITY_VERSIONS.pop(run_id, None)
        return
    _LIVE_RUN_ACTIVITY_VERSIONS[run_id] = _LIVE_RUN_ACTIVITY_VERSIONS.get(run_id, 0) + 1


def subscribe(run_id: str) -> asyncio.Queue[AgentRunEvent | None]:
    """订阅指定 run 的实时平台事件。"""

    queue: asyncio.Queue[AgentRunEvent | None] = asyncio.Queue()
    _SUBSCRIBERS.setdefault(run_id, set()).add(queue)
    return queue


def unsubscribe(run_id: str, queue: asyncio.Queue[AgentRunEvent | None]) -> None:
    """取消订阅指定 run。"""

    queues = _SUBSCRIBERS.get(run_id)
    if not queues:
        return
    queues.discard(queue)
    if not queues:
        _SUBSCRIBERS.pop(run_id, None)


def notify_subscribers(run_id: str, event: AgentRunEvent) -> None:
    """向本进程订阅者推送平台事件。"""

    for queue in list(_SUBSCRIBERS.get(run_id, ())):
        queue.put_nowait(event)
    if event.event in STREAM_END_EVENTS:
        for queue in list(_SUBSCRIBERS.get(run_id, ())):
            queue.put_nowait(None)


def subscribe_live_run_events(*, run_id: str) -> asyncio.Queue[AgentRunEvent | None]:
    """提前订阅指定 run 的本进程实时事件。"""

    return subscribe(run_id)


async def stream_live_subscribe(
    *,
    run_id: str,
    queue: asyncio.Queue[AgentRunEvent | None] | None = None,
) -> AsyncGenerator[bytes, None]:
    """只订阅本进程实时事件；queue 可由调用方提前创建以避免启动竞态。"""

    live_queue = queue or subscribe(run_id)
    try:
        while True:
            event = await live_queue.get()
            if event is None:
                return
            if event.event == "run.cancelling":
                continue
            yield encode_sse_event(event)
            if event.event in STREAM_END_EVENTS:
                return
    finally:
        unsubscribe(run_id, live_queue)


async def stream_replay_then_subscribe(
    *,
    store: _RunEventReplaySource,
    run_id: str,
    event_index: int,
    idle_timeout_seconds: float | None = None,
) -> AsyncGenerator[bytes, None]:
    """先从数据库回放事件，再订阅本进程实时事件，并用数据库轮询兜底跨进程恢复。"""

    # 兼容既有调用参数；观察链路不再依据空闲时间改变Run终态。
    _ = idle_timeout_seconds
    last_index = event_index
    for event in await store.replay_events(run_id=run_id, event_index=last_index):
        yield encode_sse_event(event)
        last_index = event.event_index if event.event_index is not None else last_index
        if event.event in STREAM_END_EVENTS:
            return

    queue = subscribe(run_id)
    last_keepalive_at = monotonic()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_EVENT_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                replayed = False
                for replayed_event in await store.replay_events(run_id=run_id, event_index=last_index):
                    replayed = True
                    yield encode_sse_event(replayed_event)
                    last_index = replayed_event.event_index if replayed_event.event_index is not None else last_index
                    if replayed_event.event in STREAM_END_EVENTS:
                        return
                if replayed:
                    last_keepalive_at = monotonic()
                    continue
                run_status = await store.get_run_status(run_id=run_id)
                if run_status in {"completed", "cancelled", "failed"} or run_status == "paused":
                    return
                now = monotonic()
                if now - last_keepalive_at >= _SSE_KEEPALIVE_INTERVAL_SECONDS:
                    yield b": keepalive\n\n"
                    last_keepalive_at = now
                continue
            if event is None:
                return
            if event.event_index is not None and event.event_index <= last_index:
                continue
            yield encode_sse_event(event)
            last_index = event.event_index if event.event_index is not None else last_index
            last_keepalive_at = monotonic()
            if event.event in STREAM_END_EVENTS:
                return
    finally:
        unsubscribe(run_id, queue)


# 兼容既有模块级调用名（store 事件追加与测试 monkeypatch）。
_subscribe = subscribe
_unsubscribe = unsubscribe
_notify_subscribers = notify_subscribers
_update_live_run_activity = update_live_run_activity
