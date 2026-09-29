"""文件功能：验证任务运行时列词汇、词汇化认领/恢复与 DurableJobRuntime 门面（WS-A2）。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Integer, String, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.time_utils import utc_now
from app.services.durable_job_lease_service import (
    DurableJobRuntime,
    claim_pending_jobs,
    recover_expired_running_jobs,
    request_job_cancellation,
)
from app.services.job_runtime_vocabulary import (
    MUTATION_JOB_VOCABULARY,
    PROJECT_BUILD_VOCABULARY,
    STANDARD_JOB_VOCABULARY,
    JobColumnVocabulary,
)


class _Base(DeclarativeBase):
    """测试用声明基类。"""


class _StandardJob(_Base):
    """标准列词汇的假任务模型。"""

    __tablename__ = "t_standard_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(nullable=True)


class _AliasedJob(_Base):
    """历史别名列词汇的假任务模型（模拟 ProjectBuild）。"""

    __tablename__ = "t_aliased_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class _Row:
    """模拟 SQLAlchemy Row 的最小行为。"""

    def __init__(self, *values: Any) -> None:
        """按位置保存候选列。"""

        self._values = values

    def __getitem__(self, index: int) -> Any:
        """按位置取值。"""

        return self._values[index]

    def __len__(self) -> int:
        """返回列数。"""

        return len(self._values)


class _Result:
    """模拟 execute 结果。"""

    def __init__(self, rows: list[_Row], rowcount: int = 0) -> None:
        """保存候选与影响行数。"""

        self._rows = rows
        self.rowcount = rowcount

    def all(self) -> list[_Row]:
        """返回候选行。"""

        return self._rows


class _Bind:
    """模拟数据库 bind。"""

    dialect = type("D", (), {"name": "sqlite"})()


class _RecordingSession:
    """记录执行的语句，不连真实数据库。"""

    def __init__(self, rows: list[_Row] | None = None) -> None:
        """可选预置候选行。"""

        self.statements: list[Any] = []
        self.rows = rows or []
        self._in_transaction = False

    def get_bind(self) -> _Bind:
        """对齐 AsyncSession，供 row_locks_hold_until_commit 使用。"""

        return _Bind()

    async def execute(self, statement: Any) -> _Result:
        """记录语句；SELECT 返回预置行，UPDATE 返回 rowcount=1。"""

        self.statements.append(statement)
        self._in_transaction = True
        if type(statement).__name__.lower().startswith("select"):
            return _Result(list(self.rows))
        return _Result([], rowcount=1)

    def in_transaction(self) -> bool:
        """对齐 AsyncSession。"""

        return self._in_transaction

    async def commit(self) -> None:
        """结束事务。"""

        self._in_transaction = False


def _sql_text(statement: Any) -> str:
    """把语句编译为可见字面量 SQL，便于断言列名与取值。"""

    try:
        return str(statement.compile(compile_kwargs={"literal_binds": True}))
    except Exception:
        return str(statement)


def test_standard_vocabulary_matches_contract_defaults() -> None:
    """标准词汇必须与契约 §2 默认列名一致。"""

    vocab = STANDARD_JOB_VOCABULARY
    assert vocab.owner == "worker_id"
    assert vocab.heartbeat == "heartbeat_at"
    assert vocab.lease_expires_at == "lease_expires_at"
    assert vocab.cancel_requested_at == "cancel_requested_at"
    assert vocab.error_code == "error_code"
    assert vocab.attempt_count == "attempt_count"


def test_project_build_vocabulary_maps_aliases() -> None:
    """ProjectBuild 词汇必须映射 lease_owner / claimed_at，且无 error_code。"""

    vocab = PROJECT_BUILD_VOCABULARY
    assert vocab.owner == "lease_owner"
    assert vocab.heartbeat == "claimed_at"
    assert vocab.error_code is None
    assert vocab.max_attempts == "max_attempts"


def test_mutation_job_vocabulary_maps_generation_and_error() -> None:
    """MutationJob 词汇必须映射 last_error_code 与 lease_generation 围栏。"""

    vocab = MUTATION_JOB_VOCABULARY
    assert vocab.error_code == "last_error_code"
    assert vocab.lease_generation == "lease_generation"
    assert vocab.next_attempt_at == "next_attempt_at"


def test_attribute_raises_on_missing_column() -> None:
    """映射到不存在的列时必须抛出明确错误，不得静默写空。"""

    vocab = JobColumnVocabulary(owner="not_a_column")
    with pytest.raises(AttributeError):
        vocab.owner_column(_StandardJob)


def test_optional_attribute_returns_none_when_absent() -> None:
    """可选列不存在时返回空，供恢复/取消跳过写入。"""

    vocab = JobColumnVocabulary(error_code=None)
    assert vocab.optional_attribute(_AliasedJob, vocab.error_code) is None


@pytest.mark.asyncio
async def test_claim_with_aliases_writes_lease_owner_and_claimed_at() -> None:
    """别名词汇认领时必须写入历史列名，而不是契约标准名。"""

    session = _RecordingSession(rows=[_Row(7)])
    now = utc_now()
    claimed = await claim_pending_jobs(
        session,  # type: ignore[arg-type]
        _AliasedJob,
        worker_id="w-1",
        limit=3,
        lease_seconds=30,
        now=now,
        vocabulary=PROJECT_BUILD_VOCABULARY,
    )
    assert claimed == [7]
    # 最后一条是认领 CAS
    cas = session.statements[-1]
    compiled = _sql_text(cas)
    assert "lease_owner" in compiled
    assert "claimed_at" in compiled
    assert "worker_id" not in compiled


@pytest.mark.asyncio
async def test_claim_values_hook_overrides_defaults() -> None:
    """领域 claim_values 可完全接管写入列。"""

    session = _RecordingSession(rows=[_Row(3)])
    now = utc_now()

    def _domain_values(row: _Row, claimed_at: datetime, expires_at: datetime) -> dict[str, Any]:
        return {
            "status": "running",
            "lease_owner": "domain-owner",
            "claimed_at": claimed_at,
            "lease_expires_at": expires_at,
            "attempt_count": 99,
            "error_message": None,
        }

    claimed = await claim_pending_jobs(
        session,  # type: ignore[arg-type]
        _AliasedJob,
        worker_id="ignored",
        limit=1,
        lease_seconds=10,
        now=now,
        vocabulary=PROJECT_BUILD_VOCABULARY,
        claim_values=_domain_values,
    )
    assert claimed == [3]
    compiled = _sql_text(session.statements[-1])
    assert "domain-owner" in compiled
    assert "99" in compiled


@pytest.mark.asyncio
async def test_recover_with_aliases_uses_lease_owner_columns() -> None:
    """别名词汇恢复时必须按历史列名写回，不碰标准名。"""

    session = _RecordingSession(rows=[_Row(11, 1)])
    summary = await recover_expired_running_jobs(
        session,  # type: ignore[arg-type]
        _AliasedJob,
        max_attempts=3,
        interrupted_error_code="TEST_INTERRUPTED",
        interrupted_error_message="测试中断。",
        vocabulary=PROJECT_BUILD_VOCABULARY,
    )
    assert summary.requeued_count == 1
    compiled = " ".join(_sql_text(s) for s in session.statements)
    assert "lease_owner" in compiled
    assert "claimed_at" in compiled


@pytest.mark.asyncio
async def test_recover_values_hook_overrides_default_write() -> None:
    """领域 recover_values 可覆盖恢复写入（如 generation 递增）。"""

    session = _RecordingSession(rows=[_Row(21, 1)])
    seen_kinds: list[str] = []

    def _domain_recover(kind: str, row: _Row, recovered_at: datetime) -> dict[str, Any]:
        seen_kinds.append(kind)
        return {
            "status": "pending",
            "lease_owner": None,
            "claimed_at": None,
            "lease_expires_at": None,
            "attempt_count": 5,
            "error_message": "DOMAIN_RECOVERED",
        }

    summary = await recover_expired_running_jobs(
        session,  # type: ignore[arg-type]
        _AliasedJob,
        max_attempts=3,
        interrupted_error_code="X",
        interrupted_error_message="Y",
        vocabulary=PROJECT_BUILD_VOCABULARY,
        recover_values=_domain_recover,
    )
    assert summary.requeued_count == 1
    assert seen_kinds == ["requeued"]
    compiled = " ".join(_sql_text(s) for s in session.statements)
    assert "DOMAIN_RECOVERED" in compiled


@pytest.mark.asyncio
async def test_recover_empty_queue_still_single_select() -> None:
    """空队列恢复不得追加 DML（保持既有空转保护）。"""

    session = _RecordingSession(rows=[])
    summary = await recover_expired_running_jobs(
        session,  # type: ignore[arg-type]
        _StandardJob,
        max_attempts=3,
        interrupted_error_code="TEST_INTERRUPTED",
        interrupted_error_message="测试中断。",
    )
    assert summary.total_count == 0
    assert len(session.statements) == 1


@pytest.mark.asyncio
async def test_cancel_without_cancel_column_only_terminates_pending() -> None:
    """无取消列的模型只能把 pending 收敛为 cancelled，不得构造 running 取消 UPDATE。"""

    session = _RecordingSession(rows=[])
    ok = await request_job_cancellation(
        session,  # type: ignore[arg-type]
        _AliasedJob,
        job_id=5,
        vocabulary=PROJECT_BUILD_VOCABULARY,
    )
    assert ok is True
    compiled = " ".join(_sql_text(s) for s in session.statements)
    assert "cancel_requested_at" not in compiled
    assert "cancelled" in compiled


@pytest.mark.asyncio
async def test_runtime_claim_and_recover_share_vocabulary() -> None:
    """DurableJobRuntime 门面必须把词汇贯穿 claim 与 recover。"""

    runtime = DurableJobRuntime(model=_AliasedJob, vocabulary=PROJECT_BUILD_VOCABULARY)
    session = _RecordingSession(rows=[_Row(2)])
    now = utc_now()
    claimed = await runtime.claim(
        session,  # type: ignore[arg-type]
        worker_id="w-rt",
        limit=2,
        lease_seconds=20,
        now=now,
    )
    assert claimed == [2]
    assert "lease_owner" in _sql_text(session.statements[-1])

    session2 = _RecordingSession(rows=[_Row(2, 0)])
    summary = await runtime.recover(
        session2,  # type: ignore[arg-type]
        max_attempts=3,
        interrupted_error_code="RT_INTERRUPTED",
        interrupted_error_message="门面恢复。",
    )
    assert summary.requeued_count == 1
    assert "lease_owner" in " ".join(_sql_text(s) for s in session2.statements)


@pytest.mark.asyncio
async def test_runtime_transition_uses_owner_alias() -> None:
    """门面 transition 必须按词汇拥有者列写围栏条件。"""

    runtime = DurableJobRuntime(model=_AliasedJob, vocabulary=PROJECT_BUILD_VOCABULARY)
    session = _RecordingSession(rows=[])
    ok = await runtime.transition(
        session,  # type: ignore[arg-type]
        job_id=9,
        worker_id="w-rt",
        values={"status": "succeeded", "finished_at": utc_now()},
        require_active_lease=True,
    )
    assert ok is True
    compiled = " ".join(_sql_text(s) for s in session.statements)
    assert "lease_owner" in compiled
