"""文件功能：验证跨表任务不变量 INV-1/INV-3/INV-5 的写路径强制与审计兜底（WS-A4）。"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.ai.job_invariants import (
    assert_inv1_requirement_batch,
    assert_inv5_attempt_fence,
    audit_cross_table_invariants,
    finalize_external_backed_job,
)
from app.core.exceptions import AppException
from app.core.time_utils import utc_now


def _batch(**kwargs):
    """构造 Batch 假对象。"""

    base = {
        "batch_id": "batch-1",
        "requirement_id": "req-1",
        "status": "resuming",
        "lease_expires_at": utc_now() + timedelta(seconds=30),
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _requirement(**kwargs):
    """构造 Requirement 假对象。"""

    base = {
        "requirement_id": "req-1",
        "status": "resolving",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_inv1_resolving_requires_resuming_batch() -> None:
    """resolving 必须对应 resuming Batch。"""

    with pytest.raises(AppException) as exc:
        assert_inv1_requirement_batch(
            requirement=_requirement(status="resolving"),
            batch=_batch(status="ready"),
        )
    assert exc.value.code == "AI_INV1_REQUIREMENT_BATCH_MISMATCH"


def test_inv1_resuming_requires_active_lease() -> None:
    """resuming + resolving 还要求租约未过期。"""

    with pytest.raises(AppException) as exc:
        assert_inv1_requirement_batch(
            requirement=_requirement(),
            batch=_batch(lease_expires_at=utc_now() - timedelta(seconds=1)),
        )
    assert exc.value.code == "AI_INV1_RESUMING_LEASE_EXPIRED"


def test_inv1_matched_pair_passes() -> None:
    """合法 resolving/resuming 对不得抛错。"""

    assert_inv1_requirement_batch(
        requirement=_requirement(),
        batch=_batch(),
    )


def test_inv1_pending_with_resuming_is_invalid() -> None:
    """Batch 已 resuming 时 Requirement 不得仍是 pending。"""

    with pytest.raises(AppException) as exc:
        assert_inv1_requirement_batch(
            requirement=_requirement(status="pending"),
            batch=_batch(),
        )
    assert exc.value.code == "AI_INV1_REQUIREMENT_BATCH_MISMATCH"


def test_inv5_rejects_attempt_mismatch() -> None:
    """attempt 不一致必须拒绝。"""

    job = SimpleNamespace(
        id=1,
        status="running",
        attempt_id="att-new",
        lease_owner="w-1",
        lease_expires_at=utc_now() + timedelta(seconds=10),
    )
    with pytest.raises(AppException) as exc:
        assert_inv5_attempt_fence(job=job, attempt_id="att-old", lease_owner="w-1")
    assert exc.value.code == "BUILD_ATTEMPT_MISMATCH"


def test_inv5_rejects_expired_lease() -> None:
    """租约过期必须拒绝。"""

    job = SimpleNamespace(
        id=1,
        status="running",
        attempt_id="att-1",
        lease_owner="w-1",
        lease_expires_at=utc_now() - timedelta(seconds=1),
    )
    with pytest.raises(AppException) as exc:
        assert_inv5_attempt_fence(job=job, attempt_id="att-1", lease_owner="w-1")
    assert exc.value.code == "BUILD_LEASE_EXPIRED"


def test_inv5_rejects_owner_mismatch() -> None:
    """提交者与租约持有者不一致必须拒绝。"""

    job = SimpleNamespace(
        id=1,
        status="running",
        attempt_id="att-1",
        lease_owner="w-1",
        lease_expires_at=utc_now() + timedelta(seconds=10),
    )
    with pytest.raises(AppException) as exc:
        assert_inv5_attempt_fence(job=job, attempt_id="att-1", lease_owner="w-2")
    assert exc.value.code == "BUILD_LEASE_OWNER_MISMATCH"


def test_inv5_matching_fence_passes() -> None:
    """合法 attempt + 租约 + 持有者必须放行。"""

    job = SimpleNamespace(
        id=1,
        status="running",
        attempt_id="att-1",
        lease_owner="w-1",
        lease_expires_at=utc_now() + timedelta(seconds=10),
    )
    assert_inv5_attempt_fence(job=job, attempt_id="att-1", lease_owner="w-1")


def test_inv5_rejects_missing_owner_when_required() -> None:
    """回收后的无持有者行不得提升产物。"""

    job = SimpleNamespace(
        id=1,
        status="pending",
        attempt_id="att-1",
        lease_owner=None,
        lease_expires_at=None,
    )
    with pytest.raises(AppException) as exc:
        assert_inv5_attempt_fence(job=job, attempt_id="att-1", require_owner_present=True)
    assert exc.value.code == "BUILD_LEASE_MISSING"


@pytest.mark.asyncio
async def test_finalize_external_backed_job_rejects_non_terminal() -> None:
    """INV-3 统一入口只接受终态。"""

    job = SimpleNamespace(
        status="running",
        finished_at=None,
        run_id="r",
        tool_call_id="t",
        result_json=None,
        error_code=None,
        error_message=None,
        attempt_count=1,
        worker_id="w",
        lease_expires_at=None,
        heartbeat_at=None,
    )
    with pytest.raises(ValueError):
        await finalize_external_backed_job(
            session=None,  # type: ignore[arg-type]
            job=job,
            status="running",
            sync_external=False,
        )


@pytest.mark.asyncio
async def test_finalize_external_backed_job_sets_terminal_status() -> None:
    """INV-3：终态写入 Job 并可关闭外部同步做纯单元验证。"""

    job = SimpleNamespace(
        status="running",
        finished_at=None,
        run_id="r",
        tool_call_id="t",
        result_json={"ok": True},
        error_code=None,
        error_message=None,
        attempt_count=1,
        worker_id="w",
        lease_expires_at=utc_now(),
        heartbeat_at=utc_now(),
    )
    ok = await finalize_external_backed_job(
        session=None,  # type: ignore[arg-type]
        job=job,
        status="succeeded",
        sync_external=False,
    )
    assert ok is True
    assert job.status == "succeeded"
    assert job.finished_at is not None


class _EmptyAuditSession:
    """审计只读会话桩：无候选时返回空。"""

    async def scalars(self, _stmt):  # noqa: ANN001
        """返回空序列。"""

        class _R:
            def all(self) -> list:
                return []

        return _R()

    async def scalar(self, _stmt):  # noqa: ANN001
        """返回空。"""

        return None


@pytest.mark.asyncio
async def test_audit_cross_table_invariants_empty_when_clean() -> None:
    """干净库审计必须为空结果。"""

    violations = await audit_cross_table_invariants(_EmptyAuditSession())  # type: ignore[arg-type]
    assert violations == {"inv1": [], "inv3": []}
