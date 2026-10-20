"""文件功能：语义化封装跨数据库事务边界技巧，使业务层不再自行解释 SQLite 写锁行为。"""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base


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


def row_locks_hold_until_commit(session: AsyncSession) -> bool:
    """判断当前方言的 `SELECT ... FOR UPDATE` 行锁是否会持续到事务结束。

    PostgreSQL 会真正加行锁，因此「加锁读候选 → 逐条 CAS」可以放在同一个事务里，
    候选集在被提交前对其他执行者不可见。SQLite 方言把 `FOR UPDATE`（含
    `SKIP LOCKED`）静默丢弃成普通 SELECT，锁语义不存在，而该读事务在下一条 UPDATE
    时会升级为写事务并可能直接以 SQLITE_BUSY 失败，所以必须提前结束读事务。

    调用方据此选择**事务形态**，不要自行比较 `dialect.name`：这是本仓唯一的方言分支
    出口，`SKIP LOCKED` 带来的收益与风险都只在这里判定一次。
    """

    return session.get_bind().dialect.name == "postgresql"


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


async def acquire_row_write_lock(session: AsyncSession, model: type[Base], row_id: int) -> None:
    """用时间列自更新锁住已鉴权的 Timestamp 实体，不改业务值、不提交事务。

    不更新主键，避免 PostgreSQL 与同事务幂等占位插入持有的外键 KEY SHARE 锁互相升级死锁。
    显式自赋值也会抑制 updated_at 的 ORM onupdate，保持纯锁操作不修改更新时间。
    """

    identity = getattr(model, "id")
    timestamp = getattr(model, "updated_at")
    await session.execute(
        update(model).where(identity == row_id).values(updated_at=timestamp)
        .execution_options(synchronize_session=False)
    )
