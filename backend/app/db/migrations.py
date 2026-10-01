"""文件功能：为独立 Alembic 迁移引擎启用真实事务，保证 SQLite DDL 与 revision 一起回滚。"""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine


def configure_migration_transactions(engine: AsyncEngine) -> None:
    """仅调整迁移引擎；SQLite 禁止驱动对首个 DDL 自动提交，不改变业务 Session 锁语义。"""
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine.sync_engine, "connect")
    def disable_driver_begin(connection, _record) -> None:
        """由 SQLAlchemy 接管 BEGIN；aiosqlite 仍正常执行 COMMIT/ROLLBACK。"""
        connection.isolation_level = None

    @event.listens_for(engine.sync_engine, "begin")
    def begin_transaction(connection) -> None:
        """在反射/首个 DDL 前显式开始真实事务，进程强杀时由 SQLite 回滚整个迁移。"""
        connection.exec_driver_sql("BEGIN")
