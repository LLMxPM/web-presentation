"""文件功能：SQLite 文件库单进程边界守卫，拒绝多 worker 与跨容器共享同一 db 文件。"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.engine import make_url

logger = logging.getLogger(__name__)

# 同一进程内幂等：重复 create_app/启动校验不重复抢锁
_process_guard: SqliteSingleProcessGuard | None = None


class SqliteSingleProcessViolation(RuntimeError):
    """SQLite 文件库被多进程/多容器共享时抛出，启动必须失败。"""


class SqliteSingleProcessGuard:
    """对 SQLite 数据库文件持有进程级排他锁，保证同一 db 仅一个 Backend 进程写入。"""

    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path).resolve()
        self._lock_path = self.database_path.with_name(self.database_path.name + ".single-process.lock")
        self._handle: BinaryIO | None = None

    def acquire(self) -> None:
        """获取排他锁；失败表示已有其他进程/容器在写同一 SQLite 文件。"""

        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self._lock_path, "a+b")
        try:
            _lock_file_exclusive(handle)
        except OSError as exc:
            handle.close()
            raise SqliteSingleProcessViolation(
                f"SQLite 单写库要求单 Backend 进程：无法获取 {self._lock_path} 排他锁。"
                "请勿多容器挂同一数据卷，也不要使用 uvicorn --workers > 1。"
            ) from exc
        self._handle = handle
        logger.info(
            "SQLite 单进程边界已锁定。",
            extra={
                "event": "sqlite.single_process.locked",
                "sqlite_single_process": True,
                "database_path": str(self.database_path),
            },
        )

    def release(self) -> None:
        """释放排他锁并解除进程内登记；进程退出后由 OS 自动回收句柄。"""

        global _process_guard
        if _process_guard is self:
            _process_guard = None
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            _unlock_file(handle)
        finally:
            handle.close()


def ensure_sqlite_single_process(database_url: str) -> SqliteSingleProcessGuard | None:
    """SQLite 文件库启动校验；非 SQLite 或内存库返回 None。

    同一进程对同一库重复调用幂等；换库调用会释放旧锁并重新绑定，
    以便测试/工具按序创建多个应用时每个库都真正被守卫。
    """

    try:
        url = make_url(database_url)
    except Exception:  # noqa: BLE001
        return None
    if not url.drivername.startswith("sqlite"):
        return None
    database = str(url.database or "").strip()
    if not database or database in {":memory:", "file::memory:"}:
        return None

    _reject_multi_worker_env()

    global _process_guard
    resolved = Path(database).resolve()
    existing = _process_guard
    if existing is not None:
        if existing.database_path == resolved:
            return existing
        logger.warning(
            "同一进程改用另一个 SQLite 文件库，释放旧单进程锁后重新绑定。",
            extra={
                "event": "sqlite.single_process.rebind",
                "previous_database_path": str(existing.database_path),
                "database_path": str(resolved),
            },
        )
        existing.release()
        _process_guard = None

    guard = SqliteSingleProcessGuard(database)
    guard.acquire()
    _process_guard = guard
    return guard


def _reject_multi_worker_env() -> None:
    """拒绝显式多 worker 配置；uvicorn --workers>1 不得与 SQLite 文件库共存。"""

    resolved = read_explicit_worker_count()
    if resolved is None:
        return
    key, workers = resolved
    raise SqliteSingleProcessViolation(
        f"SQLite 文件库不允许 {key}={workers}：必须单进程写入。"
        "请将并发约束写在部署模板（如 AI_PAGE_MUTATION_CONCURRENCY=1），不要扩 Backend 进程数。"
    )


def read_explicit_worker_count() -> tuple[str, int] | None:
    """读取显式声明的 Backend 进程数；未声明或声明为单进程时返回 None。"""

    for key in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        raw = os.environ.get(key, "").strip()
        if not raw:
            continue
        try:
            workers = int(raw)
        except ValueError:
            continue
        if workers > 1:
            return key, workers
    return None


def _lock_file_exclusive(handle: BinaryIO) -> None:
    """按平台对文件句柄加排他锁；不可用时退化为非阻塞创建锁文件。"""

    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    try:
        import fcntl
    except ImportError:  # pragma: no cover - 非 POSIX 极少路径
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle: BinaryIO) -> None:
    """释放平台文件锁。"""

    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    try:
        import fcntl
    except ImportError:  # pragma: no cover
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
