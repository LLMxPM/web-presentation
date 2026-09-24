"""文件功能：收口数据库写锁探测；业务禁止直接下钻 driver_connection。"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def holds_write_lock(session: AsyncSession) -> bool:
    """判断当前 SQLite 连接是否已开启写事务。

    仅用于避免「进程锁 → 数据库写锁」锁序反转。非 SQLite 恒 False。
    探测失败时打点告警并返回 False（fail-safe：退回进程锁路径），不静默吞掉。
    """

    try:
        bind = session.get_bind()
        if bind is None or bind.dialect.name != "sqlite":
            return False
    except Exception:  # noqa: BLE001
        logger.warning(
            "写锁探测失败（dialect）。",
            extra={"event": "db.locks.probe_failed", "stage": "dialect"},
            exc_info=True,
        )
        return False

    try:
        # 延迟导入同步连接对象：仅本模块允许 driver_connection 下钻
        connection = session.sync_session.connection()
        if connection is None:
            return False
        driver_connection = connection.connection.driver_connection
        value = bool(getattr(driver_connection, "in_transaction", False))
        if not hasattr(driver_connection, "in_transaction"):
            logger.warning(
                "写锁探测降级：驱动无 in_transaction 属性，退回进程锁路径。",
                extra={"event": "db.locks.probe_degraded"},
            )
        return value
    except Exception:  # noqa: BLE001
        logger.warning(
            "写锁探测失败，退回进程锁路径。",
            extra={"event": "db.locks.probe_failed", "stage": "driver"},
            exc_info=True,
        )
        return False
