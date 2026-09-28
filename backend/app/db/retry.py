"""文件功能：收口数据库写冲突退避重试，业务层不再各自手写 except OperationalError 循环。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.errors import detect_transient_write_conflict

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class WriteConflictContext:
    """一次可重试写冲突的上下文，供调用方在退避前刷新实体或记录结构化日志。

    本对象在 `rollback()` **之后**才交给 `on_conflict`，此时会话内所有 ORM 实体都已被
    expire：钩子里不得读取实体的惰性属性（会触发同步 IO 并抛 `MissingGreenlet`），
    只能使用调用方在重试循环之前取出的标量，或通过 `session.get()` 显式重读。
    """

    session: AsyncSession
    attempt: int
    error: OperationalError
    delay_seconds: float


def exponential_backoff_delays(attempts: int, base_seconds: float) -> tuple[float, ...]:
    """生成 `attempts` 次尝试之间的指数退避时长，返回长度为 attempts-1 的序列。"""

    return tuple(base_seconds * (2**index) for index in range(max(0, attempts - 1)))


@asynccontextmanager
async def _attempt_session(
    session_factory: Callable[[], AsyncSession] | None,
    session: AsyncSession | None,
) -> AsyncIterator[AsyncSession]:
    """按调用方选择的生命周期提供会话：复用传入会话，或每次尝试新建并在结束时关闭。"""

    if session is not None:
        yield session
        return
    if session_factory is None:
        raise ValueError("WRITE_RETRY_SESSION_REQUIRED")
    created = session_factory()
    try:
        yield created
    finally:
        await created.close()


async def run_with_write_retry(
    operation: Callable[[AsyncSession], Awaitable[T]],
    *,
    backoff_delays: Sequence[float],
    session_factory: Callable[[], AsyncSession] | None = None,
    session: AsyncSession | None = None,
    on_conflict: Callable[[WriteConflictContext], Awaitable[None]] | None = None,
) -> T:
    """在瞬时写冲突时按退避表重试 `operation`，其他数据库错误原样上抛。

    冲突判据只有 `app.db.errors.detect_transient_write_conflict` 一处，同时覆盖 SQLite
    BUSY/LOCKED 与 PostgreSQL deadlock(40P01)/serialization_failure(40001)；因此本函数
    对两种数据库是同一条代码路径，调用方不需要方言分支。

    会话生命周期二选一：传 `session` 则复用且**不关闭**（事务仍归调用方所有）；传
    `session_factory` 则每次尝试新建会话，并在该次尝试结束后关闭，使退避期间不占用连接。

    每次可重试冲突都先 `rollback()` 再判断尝试是否用尽，因此最后一次失败同样把会话
    留在干净状态。`on_conflict` 只在确实还会重试时触发，用于刷新实体或打点。
    """

    delays = tuple(backoff_delays)
    attempts = len(delays) + 1
    for attempt in range(attempts):
        async with _attempt_session(session_factory, session) as active:
            try:
                return await operation(active)
            except OperationalError as exc:
                await active.rollback()
                if not detect_transient_write_conflict(exc) or attempt + 1 >= attempts:
                    raise
                delay_seconds = delays[attempt]
                if on_conflict is not None:
                    await on_conflict(
                        WriteConflictContext(
                            session=active,
                            attempt=attempt,
                            error=exc,
                            delay_seconds=delay_seconds,
                        )
                    )
                await asyncio.sleep(delay_seconds)
    # 循环内每次迭代都 return 或 raise；此处只为静态检查穷尽返回路径。
    raise RuntimeError("unreachable write retry state")
