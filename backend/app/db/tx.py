"""文件功能：语义化封装跨数据库事务边界技巧，使业务层不再自行解释 SQLite 写锁行为。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


async def commit_end_read(session: AsyncSession) -> None:
    """结束当前只读事务，不发送任何业务 UPDATE。

    两类调用场景：

    1. 候选 SELECT 之后、进入 Runtime/Chromium 等慢路径之前，避免长时间占用读快照。
    2. 候选 SELECT 之后、逐条 CAS 写之前。SQLite 把读事务升级为写事务时，若期间
       已有其他写者提交，会直接以 SQLITE_BUSY 失败而不是排队等待；提前结束读事务，
       后续 UPDATE 便以写者身份重新取锁。PostgreSQL 的正确性不依赖本函数（行锁由
       `SELECT ... FOR UPDATE` 表达），但提前结束只读事务同样能缩短空闲期占用。

    结束读事务即放弃快照隔离，因此调用方后续的写必须自带条件围栏（CAS 谓词），
    不能假设候选集仍然有效。
    """

    if session.in_transaction():
        await session.commit()


async def acquire_admission_lock(
    session: AsyncSession,
    state: object,
    *,
    version_attr: str = "version",
) -> None:
    """递增单行版本号并 flush，以此取得「容量检查 + 插入」的准入锁。

    同一条 UPDATE 在两种数据库上给出等价效果：PostgreSQL 锁住该单行，SQLite 则因
    进入写事务而取得全库写者身份，于是其后的计数检查与 INSERT 之间不再存在竞态。

    这里刻意不用 `SELECT ... FOR UPDATE`：SQLite 方言会把 `FOR UPDATE`（含
    `SKIP LOCKED`）静默丢弃、编译成普通 SELECT，锁语义在 Lite 侧会无声消失。
    单行 UPDATE 是两种数据库都能真正表达的最小准入原语。
    """

    current = getattr(state, version_attr, None) or 0
    setattr(state, version_attr, int(current) + 1)
    await session.flush()
