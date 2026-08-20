"""文件功能：测试单事务先占位关联幂等引擎的指纹计算、占位插入、重放机制与并发冲突隔离。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.idempotency_service import IdempotencyService


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

    from datetime import timedelta
    from app.core.time_utils import utc_now
    from app.models.api_idempotency_record import ApiIdempotencyRecord

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
