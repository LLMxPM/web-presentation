"""文件功能：语义化封装 SQLite 单写者相关的读事务收口。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


async def commit_end_read(session: AsyncSession) -> None:
    """结束当前只读事务，避免长时间占用 SQLite 读快照/锁。

    用于候选 SELECT 之后、进入 Runtime/Chromium 等慢路径之前。
    不发送任何业务 UPDATE。
    """

    if session.in_transaction():
        await session.commit()
