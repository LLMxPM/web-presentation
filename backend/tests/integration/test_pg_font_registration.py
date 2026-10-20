"""文件功能：在真实 PostgreSQL 上回归带幂等占位的字体族归并、face 唯一性与注册原子性。"""
from __future__ import annotations

import asyncio
import os
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core.exceptions import AppException
from app.db.base import Base
from app.models.api_idempotency_record import ApiIdempotencyRecord
from app.models.asset import WorkspaceAsset
from app.models.font import WorkspaceFontConfig, WorkspaceFontFamily
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.font import WorkspaceFontConfigCreateRequest
from app.services.idempotency_service import IdempotencyService
from app.services.workspace_font_service import WorkspaceFontService


@pytest.fixture
async def pg_fonts():
    """只在显式 E2E PG 库播种唯一命名前缀的数据，结束时清理本夹具创建的行。"""
    url = os.environ.get("P4_POSTGRES_DATABASE_URL", "").strip()
    if not url:
        if os.environ.get("P4_POSTGRES_REQUIRED") == "1":
            pytest.fail("必须配置 P4_POSTGRES_DATABASE_URL")
        pytest.skip("未配置 PostgreSQL 字体专项测试库")
    assert "_e2e" in urlsplit(url).path, "字体并发回归只允许专用 _e2e 库"
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    suffix = uuid4().hex
    async with factory() as session:
        user = User(username="font-pg-" + suffix, password_hash="test-only", display_name="字体专项", preview_size_presets=[])
        workspace = Workspace(code="font-pg-" + suffix, name="字体并发专项")
        session.add_all([user, workspace])
        await session.flush()
        assets = [WorkspaceAsset(
            workspace_id=workspace.id, name=f"face-{i}", file_name=f"face-{i}.ttf",
            original_name=f"face-{i}.ttf", file_size=1, file_hash=str(i) * 64, asset_type="font",
        ) for i in range(2)]
        session.add_all(assets)
        await session.commit()
        user_id, workspace_id, asset_ids = user.id, workspace.id, [item.id for item in assets]
        original_timestamp = workspace.updated_at
    try:
        yield factory, user_id, workspace_id, asset_ids, original_timestamp
    finally:
        async with factory() as session:
            for model in (ApiIdempotencyRecord, WorkspaceFontConfig, WorkspaceFontFamily, WorkspaceAsset):
                await session.execute(delete(model).where(model.workspace_id == workspace_id))
            await session.execute(delete(Workspace).where(Workspace.id == workspace_id))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        await engine.dispose()


@pytest.mark.parametrize("case", ["same-face", "different-weights", "same-asset"])
async def test_concurrent_font_registration_with_idempotency_is_atomic(pg_fonts, case):
    """两次占位都已持有工作空间外键锁后同时注册，要求无死锁、无裸完整性错误且不改空间时间。"""
    factory, user_id, workspace_id, assets, original_timestamp = pg_fonts
    barrier = asyncio.Barrier(2)

    async def register(index):
        """保留真实幂等事务边界，在进入领域服务前固定并发交错点。"""
        async with factory() as session:
            payload = WorkspaceFontConfigCreateRequest(
                asset_id=assets[0] if case == "same-asset" else assets[index],
                family_name="Concurrent Family",
                font_weight=str(400 + 300 * index) if case == "different-weights" else "400",
            )

            async def operation(_record_id):
                """等待双方幂等占位完成后调用实际字体服务，不 mock 数据库与锁。"""
                await barrier.wait()
                result = await WorkspaceFontService(session).create_workspace_font(workspace_id, payload, commit=False)
                return 200, result

            return await IdempotencyService(session).execute_idempotent_operation(
                user_id=user_id, workspace_id=workspace_id, idempotency_key=f"register-{index}",
                operation="font.register", fingerprint=str(index) * 64, operation_func=operation,
            )

    results = await asyncio.wait_for(asyncio.gather(register(0), register(1), return_exceptions=True), timeout=20)
    errors = [result for result in results if isinstance(result, BaseException)]
    expected_faces = 2 if case == "different-weights" else 1
    assert len(errors) == 2 - expected_faces, results
    if errors:
        assert isinstance(errors[0], AppException), errors
        assert errors[0].code == ("FONT_CONFIG_ALREADY_EXISTS" if case == "same-asset" else "FONT_CONFIG_DUPLICATE_FACE")
    async with factory() as session:
        families = list((await session.scalars(select(WorkspaceFontFamily).where(WorkspaceFontFamily.workspace_id == workspace_id))).all())
        faces = list((await session.scalars(select(WorkspaceFontConfig).where(WorkspaceFontConfig.workspace_id == workspace_id))).all())
        records = list((await session.scalars(select(ApiIdempotencyRecord).where(ApiIdempotencyRecord.workspace_id == workspace_id))).all())
        workspace = await session.get(Workspace, workspace_id)
        assert len(families) == 1
        assert len(faces) == len(records) == expected_faces
        assert all(record.status == "completed" for record in records)
        assert workspace.updated_at == original_timestamp
