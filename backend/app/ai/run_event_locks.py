"""文件功能：提供进程内按 run 的事件追加锁，串行化尚未持有 SQLite 写锁的追加与退避重试。"""

from __future__ import annotations

import asyncio
from weakref import WeakValueDictionary

# 进程内按 run 的事件追加串行化锁表。WeakValueDictionary 允许无引用时自动回收。
_RUN_EVENT_LOCKS: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def get_run_event_lock(run_id: str) -> asyncio.Lock:
    """获取进程内按 run 复用的事件写锁，串行尚未持有 SQLite 写锁的追加操作。

    本锁只约束当前进程，用于让退避重试的 rollback 不与其他追加交错；跨实例的
    `event_index` 单调性由 `allocate_run_event_index` 的数据库原子递增承担，
    因此不得把它当作 Backend 多副本的互斥原语。
    """

    lock = _RUN_EVENT_LOCKS.get(run_id)
    if lock is None:
        lock = asyncio.Lock()
        _RUN_EVENT_LOCKS[run_id] = lock
    return lock


# 兼容既有 monkeypatch / 内部调用名。
_get_run_event_lock = get_run_event_lock
