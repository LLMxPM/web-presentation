"""文件功能：测试单事务先占位关联幂等引擎的指纹计算、占位插入、重放机制、读重试与并发冲突隔离。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.api_idempotency_record import ApiIdempotencyRecord
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.idempotency_service import WRITE_CONFLICT_BACKOFF_DELAYS, IdempotencyService


@pytest.mark.asyncio
async def test_idempotency_fingerprint_and_caching(app_session: AsyncSession) -> None:
    """测试幂等指纹计算与相同 Key 重放已完成结果。"""

    user = User(
        username="idemp_user",
        password_hash="hash",
        display_name="User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    app_session.add(user)
    await app_session.flush()

    ws = Workspace(code="ws-idem-01", name="WS", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
    app_session.add(ws)
    await app_session.commit()

    u_id = user.id
    w_id = ws.id

    service = IdempotencyService(app_session)
    key = "idem-test-key-001"
    fp = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path="/api/v1/projects",
        json_data={"name": "Demo Project"},
    )

    execution_count = 0

    async def _operation(record_id: int | None) -> tuple[int, dict[str, str]]:
        nonlocal execution_count
        execution_count += 1
        return 201, {"project_id": "1001", "name": "Demo Project"}

    # 首次执行
    code1, res1 = await service.execute_idempotent_operation(
        user_id=u_id,
        workspace_id=w_id,
        idempotency_key=key,
        operation="project.create",
        fingerprint=fp,
        operation_func=_operation,
    )
    assert code1 == 201
    assert res1["project_id"] == "1001"
    assert execution_count == 1

    # 携带相同 Key 和相同 Payload 重放请求 -> 应命中缓存并返回，不重复执行 _operation
    code2, res2 = await service.execute_idempotent_operation(
        user_id=u_id,
        workspace_id=w_id,
        idempotency_key=key,
        operation="project.create",
        fingerprint=fp,
        operation_func=_operation,
    )
    assert code2 == 201
    assert res2["project_id"] == "1001"
    assert execution_count == 1  # 依然为 1，未重复执行

    # 携带相同 Key 但不同 Payload -> 必须抛出 409 IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD
    different_fp = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path="/api/v1/projects",
        json_data={"name": "Completely Different Payload"},
    )
    with pytest.raises(AppException) as exc_info:
        await service.execute_idempotent_operation(
            user_id=u_id,
            workspace_id=w_id,
            idempotency_key=key,
            operation="project.create",
            fingerprint=different_fp,
            operation_func=_operation,
        )
    assert exc_info.value.code == "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD"


@pytest.mark.asyncio
async def test_idempotency_expired_record_recycling_and_cleanup(app_session: AsyncSession) -> None:
    """测试过期幂等记录自动复用重新执行以及 clean_expired_records 清理机制。"""

    user = User(
        username="idemp_exp_user",
        password_hash="hash",
        display_name="User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    app_session.add(user)
    await app_session.flush()

    ws = Workspace(code="ws-idem-exp", name="WS Exp", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
    app_session.add(ws)
    await app_session.commit()

    service = IdempotencyService(app_session)
    key = "idem-exp-key"
    fp = "fp-exp-test"

    u_id = user.id
    ws_id = ws.id

    # 1. 插入一个已过期的幂等记录
    expired_time = utc_now() - timedelta(days=1)
    record = ApiIdempotencyRecord(
        user_id=u_id,
        workspace_id=ws_id,
        idempotency_key=key,
        operation="test.op",
        request_fingerprint="old-fp",
        status="completed",
        status_code=200,
        response_body={"old": "data"},
        expires_at=expired_time,
        created_at=expired_time,
    )
    app_session.add(record)
    await app_session.commit()

    # 2. 复用该过期 Key -> 应该重新执行而非返回旧数据或报指纹冲突
    executed = False

    async def _new_op(record_id: int | None) -> tuple[int, dict[str, str]]:
        nonlocal executed
        executed = True
        return 200, {"new": "fresh_data"}

    code, res = await service.execute_idempotent_operation(
        user_id=u_id,
        workspace_id=ws_id,
        idempotency_key=key,
        operation="test.op",
        fingerprint=fp,
        operation_func=_new_op,
    )
    assert code == 200
    assert res == {"new": "fresh_data"}
    assert executed is True

    # 3. 再次插入一个已过期记录，测试 clean_expired_records
    expired_record2 = ApiIdempotencyRecord(
        user_id=u_id,
        workspace_id=ws_id,
        idempotency_key="clean-key-2",
        operation="test.op",
        request_fingerprint="fp2",
        status="completed",
        status_code=200,
        response_body={},
        expires_at=utc_now() - timedelta(hours=2),
        created_at=utc_now() - timedelta(hours=5),
    )
    app_session.add(expired_record2)
    await app_session.commit()

    cleaned = await IdempotencyService.clean_expired_records()
    assert cleaned >= 1


class _ScriptedScalarSession:
    """按脚本返回 scalar 结果或抛出异常，用于覆盖读重试路径。"""

    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)
        self.scalar_calls = 0

    async def scalar(self, _stmt: Any) -> Any:
        """执行下一条脚本指令；脚本耗尽后重复最后一条。"""

        index = min(self.scalar_calls, len(self._script) - 1)
        self.scalar_calls += 1
        item = self._script[index]
        if isinstance(item, Exception):
            raise item
        return item

    async def flush(self) -> None:
        """占位，满足过期复用路径的 flush 调用。"""

    async def commit(self) -> None:
        """占位，满足过期复用路径的提交调用。"""

    async def rollback(self) -> None:
        """占位，满足异常回滚路径。"""


def _sqlite_locked_error() -> OperationalError:
    """构造 SQLite database is locked 的可重试写冲突。"""

    return OperationalError("SELECT 1", {}, Exception("database is locked"))


def _syntax_error() -> OperationalError:
    """构造不可重试的 OperationalError。"""

    return OperationalError("SELECT bad", {}, Exception("syntax error"))


def _completed_record() -> ApiIdempotencyRecord:
    """构造一条已完成、指纹匹配的幂等记录（不入库）。"""

    return ApiIdempotencyRecord(
        user_id=1,
        workspace_id=1,
        idempotency_key="retry-key",
        operation="test.op",
        request_fingerprint="fp-retry",
        status="completed",
        status_code=200,
        response_body={"ok": True},
        expires_at=utc_now() + timedelta(days=1),
        created_at=utc_now(),
    )


@pytest.mark.asyncio
async def test_existing_record_lookup_retries_on_transient_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """可重试写冲突应退避重查，最终命中已有记录并重放。"""

    sleeps: list[float] = []
    monkeypatch.setattr(
        "app.services.idempotency_service.asyncio.sleep",
        AsyncMock(side_effect=lambda delay: sleeps.append(delay)),
    )
    session = _ScriptedScalarSession(
        [
            _sqlite_locked_error(),
            _sqlite_locked_error(),
            _completed_record(),
        ]
    )
    service = IdempotencyService(session)  # type: ignore[arg-type]

    code, body = await service._handle_existing_record(
        user_id=1,
        workspace_id=1,
        idempotency_key="retry-key",
        operation="test.op",
        fingerprint="fp-retry",
        operation_func=AsyncMock(return_value=(200, {"ok": True})),
    )

    assert code == 200
    assert body == {"ok": True}
    assert session.scalar_calls == 3
    assert sleeps == list(WRITE_CONFLICT_BACKOFF_DELAYS[:2])


@pytest.mark.asyncio
async def test_existing_record_lookup_does_not_retry_non_conflict_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不可重试错误必须立即上抛，不得吃满退避表。"""

    sleep = AsyncMock()
    monkeypatch.setattr("app.services.idempotency_service.asyncio.sleep", sleep)
    session = _ScriptedScalarSession([_syntax_error()])
    service = IdempotencyService(session)  # type: ignore[arg-type]

    with pytest.raises(OperationalError):
        await service._handle_existing_record(
            user_id=1,
            workspace_id=1,
            idempotency_key="retry-key",
            operation="test.op",
            fingerprint="fp-retry",
            operation_func=AsyncMock(),
        )

    assert session.scalar_calls == 1
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_record_lookup_fallback_rereads_when_never_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全部重查均为 None 时，for-else 必须兜底再读一次后才判并发冲突。"""

    monkeypatch.setattr(
        "app.services.idempotency_service.asyncio.sleep",
        AsyncMock(),
    )
    session = _ScriptedScalarSession([None])
    service = IdempotencyService(session)  # type: ignore[arg-type]

    with pytest.raises(AppException) as exc_info:
        await service._handle_existing_record(
            user_id=1,
            workspace_id=1,
            idempotency_key="missing-key",
            operation="test.op",
            fingerprint="fp-missing",
            operation_func=AsyncMock(),
        )

    assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"
    # 退避表 N 次 + for-else 兜底 1 次
    assert session.scalar_calls == len(WRITE_CONFLICT_BACKOFF_DELAYS) + 1


@pytest.mark.asyncio
async def test_existing_record_lookup_sleeps_between_empty_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """查无此行同样退避，避免在并发写者提交前空转紧循环重查。"""

    sleeps: list[float] = []
    monkeypatch.setattr(
        "app.services.idempotency_service.asyncio.sleep",
        AsyncMock(side_effect=lambda delay: sleeps.append(delay)),
    )
    session = _ScriptedScalarSession([None, _completed_record()])
    service = IdempotencyService(session)  # type: ignore[arg-type]

    code, body = await service._handle_existing_record(
        user_id=1,
        workspace_id=1,
        idempotency_key="late-visible",
        operation="test.op",
        fingerprint="fp-retry",
        operation_func=AsyncMock(return_value=(200, {"ok": True})),
    )

    assert code == 200
    assert body == {"ok": True}
    assert session.scalar_calls == 2
    assert sleeps == [WRITE_CONFLICT_BACKOFF_DELAYS[0]]
