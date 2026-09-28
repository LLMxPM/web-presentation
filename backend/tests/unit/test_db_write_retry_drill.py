"""文件功能：对拍演练 SQLite BUSY 与 PostgreSQL 40001/40P01 经统一写重试的同路径行为。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import OperationalError

from app.db.retry import WriteConflictContext, exponential_backoff_delays, run_with_write_retry

pytestmark = pytest.mark.unit


def _sqlite_locked() -> OperationalError:
    """构造 SQLite database is locked（可重试）。"""

    return OperationalError("UPDATE t", {}, Exception("database is locked"))


def _pg_serialization_failure() -> OperationalError:
    """构造 PostgreSQL serialization_failure(40001)。"""

    class _Orig(Exception):
        pgcode = "40001"

    return OperationalError("UPDATE t", {}, _Orig("could not serialize access due to concurrent update"))


def _pg_deadlock() -> OperationalError:
    """构造 PostgreSQL deadlock_detected(40P01)。"""

    class _Orig(Exception):
        pgcode = "40P01"

    return OperationalError("UPDATE t", {}, _Orig("deadlock detected"))


def _syntax_error() -> OperationalError:
    """构造不可重试错误。"""

    return OperationalError("SELECT bad", {}, Exception("syntax error"))


class _ScriptedOperation:
    """按脚本抛错或返回，记录调用次数。"""

    def __init__(self, script: list[object], *, ok: object = "ok") -> None:
        self._script = list(script)
        self._ok = ok
        self.calls = 0

    async def __call__(self, _session: object) -> object:
        """执行下一条脚本指令；耗尽后返回成功值。"""

        index = self.calls
        self.calls += 1
        if index < len(self._script):
            item = self._script[index]
            if isinstance(item, Exception):
                raise item
            return item
        return self._ok


class _DummySession:
    """只实现写重试路径用到的 rollback。"""

    def __init__(self) -> None:
        self.rollbacks = 0

    async def rollback(self) -> None:
        """记录回滚次数。"""

        self.rollbacks += 1


@pytest.mark.asyncio
async def test_sqlite_busy_and_pg_conflicts_share_one_retry_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """SQLite BUSY、PG 40001、PG 40P01 必须走同一 `run_with_write_retry` 路径并最终成功。"""

    sleeps: list[float] = []
    monkeypatch.setattr(
        "app.db.retry.asyncio.sleep",
        AsyncMock(side_effect=lambda delay: sleeps.append(delay)),
    )
    delays = exponential_backoff_delays(4, 0.025)

    for conflict in (_sqlite_locked(), _pg_serialization_failure(), _pg_deadlock()):
        session = _DummySession()
        operation = _ScriptedOperation([conflict, conflict])
        result = await run_with_write_retry(
            operation,
            backoff_delays=delays,
            session=session,  # type: ignore[arg-type]
        )
        assert result == "ok"
        assert operation.calls == 3
        assert session.rollbacks == 2
        assert sleeps == list(delays[:2])
        sleeps.clear()


@pytest.mark.asyncio
async def test_non_conflict_operational_error_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """非冲突 OperationalError 不得退避重试。"""

    sleep = AsyncMock()
    monkeypatch.setattr("app.db.retry.asyncio.sleep", sleep)
    session = _DummySession()
    operation = _ScriptedOperation([_syntax_error()])

    with pytest.raises(OperationalError):
        await run_with_write_retry(
            operation,
            backoff_delays=exponential_backoff_delays(3, 0.01),
            session=session,  # type: ignore[arg-type]
        )

    assert operation.calls == 1
    assert session.rollbacks == 1
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_exhausted_conflicts_raise_after_final_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    """冲突次数用尽后上抛，且最后一次同样 rollback 留下干净会话。"""

    monkeypatch.setattr("app.db.retry.asyncio.sleep", AsyncMock())
    session = _DummySession()
    always_locked = _ScriptedOperation([_sqlite_locked(), _sqlite_locked(), _sqlite_locked(), _sqlite_locked()])

    with pytest.raises(OperationalError):
        await run_with_write_retry(
            always_locked,
            backoff_delays=exponential_backoff_delays(3, 0.01),
            session=session,  # type: ignore[arg-type]
        )

    assert always_locked.calls == 3
    assert session.rollbacks == 3


@pytest.mark.asyncio
async def test_on_conflict_receives_scalar_safe_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """`on_conflict` 在 rollback 之后触发；上下文只暴露标量与显式重读入口。"""

    monkeypatch.setattr("app.db.retry.asyncio.sleep", AsyncMock())
    seen: list[WriteConflictContext] = []

    async def _capture(context: WriteConflictContext) -> None:
        """记录冲突上下文，不读取 ORM 属性。"""

        seen.append(context)

    session = _DummySession()
    operation = _ScriptedOperation([_pg_serialization_failure()])
    result = await run_with_write_retry(
        operation,
        backoff_delays=(0.01,),
        session=session,  # type: ignore[arg-type]
        on_conflict=_capture,
    )

    assert result == "ok"
    assert len(seen) == 1
    assert seen[0].attempt == 0
    assert seen[0].delay_seconds == 0.01
    assert isinstance(seen[0].error, OperationalError)
    # rollback 先于 on_conflict：钩子不得假设实体仍附着在会话上
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_sqlite_and_pg_conflicts_count_identical_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    """两种方言冲突在同一退避表下的尝试次数与 rollback 次数一致（对拍）。"""

    monkeypatch.setattr("app.db.retry.asyncio.sleep", AsyncMock())
    delays = exponential_backoff_delays(3, 0.01)
    outcomes: dict[str, tuple[int, int]] = {}

    for name, conflict in (("sqlite", _sqlite_locked()), ("postgres", _pg_serialization_failure())):
        session = _DummySession()
        operation = _ScriptedOperation([conflict, conflict, conflict])
        with pytest.raises(OperationalError):
            await run_with_write_retry(
                operation,
                backoff_delays=delays,
                session=session,  # type: ignore[arg-type]
            )
        outcomes[name] = (operation.calls, session.rollbacks)

    assert outcomes["sqlite"] == outcomes["postgres"] == (3, 3)
