"""文件功能：验证 WorkspaceFontService 的事务边界、commit 控制、单项查询与异常回滚语义。"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.models.enums import RecordStatus
from app.schemas.font import (
    WorkspaceFontConfigCreateRequest,
    WorkspaceFontConfigUpdateRequest,
    WorkspaceFontFamilyUpdateRequest,
)
from app.services.workspace_font_service import WorkspaceFontService


async def _create_workspace(client: AsyncClient, name: str) -> int:
    res = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert res.status_code == 200
    return res.json()["id"]


async def _upload_font_asset(client: AsyncClient, workspace_id: int, name: str) -> int:
    res = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (f"{name}.woff2", b"font-binary-data", "font/woff2")},
        data={"asset_type": "font", "tags": "[]", "name": name},
    )
    assert res.status_code == 200
    return res.json()["id"]


async def test_font_service_commit_false_rollback_integrity(authenticated_client: AsyncClient) -> None:
    """验证 commit=False 模式下不会自行提交，session.rollback() 能干净撤销全部变更。"""
    ws_id = await _create_workspace(authenticated_client, "字体事务回滚空间")
    asset_id = await _upload_font_asset(authenticated_client, ws_id, "rollback_font")

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = WorkspaceFontService(session)
        created = await service.create_workspace_font(
            ws_id,
            WorkspaceFontConfigCreateRequest(
                asset_id=asset_id,
                family_name="RollbackFamily",
                font_weight="400",
                font_style="normal",
            ),
            commit=False,
        )
        assert created.id is not None
        # 手动回滚事务
        await session.rollback()

    # 重新开启会话，验证数据库中没有该注册项和该字体族
    async with session_factory() as verify_session:
        verify_service = WorkspaceFontService(verify_session)
        with pytest.raises(AppException) as exc_info:
            await verify_service.get_workspace_font(ws_id, created.id)
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "FONT_CONFIG_NOT_FOUND"


async def test_font_service_public_single_queries_and_isolation(authenticated_client: AsyncClient) -> None:
    """验证公开单项查询方法正常返回，且跨空间访问被 404 隐藏。"""
    ws1 = await _create_workspace(authenticated_client, "字体查询空间1")
    ws2 = await _create_workspace(authenticated_client, "字体查询空间2")
    asset_id = await _upload_font_asset(authenticated_client, ws1, "query_font")

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = WorkspaceFontService(session)
        created = await service.create_workspace_font(
            ws1,
            WorkspaceFontConfigCreateRequest(
                asset_id=asset_id,
                family_name="QueryFamily",
                font_weight="400",
                font_style="normal",
            ),
            commit=True,
        )

        # 1. 成功读取 face 详情
        face_detail = await service.get_workspace_font(ws1, created.id)
        assert face_detail.id == created.id
        assert face_detail.font_family == "QueryFamily"
        assert face_detail.asset_url is not None

        # 2. 成功读取 family 详情
        family_detail = await service.get_workspace_font_family(ws1, created.family_id)
        assert family_detail.id == created.family_id
        assert family_detail.name == "QueryFamily"
        assert len(family_detail.faces) == 1
        assert family_detail.faces[0].id == created.id

        # 3. 跨空间查询必须 404
        with pytest.raises(AppException) as face_exc:
            await service.get_workspace_font(ws2, created.id)
        assert face_exc.value.status_code == 404

        with pytest.raises(AppException) as family_exc:
            await service.get_workspace_font_family(ws2, created.family_id)
        assert family_exc.value.status_code == 404


async def test_font_service_rename_family_with_commit_control(authenticated_client: AsyncClient) -> None:
    """验证字体族重命名支持 commit=False，并在同一事务内完成主题标签同步。"""
    ws_id = await _create_workspace(authenticated_client, "族重命名空间")
    asset_id = await _upload_font_asset(authenticated_client, ws_id, "rename_font")

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = WorkspaceFontService(session)
        created = await service.create_workspace_font(
            ws_id,
            WorkspaceFontConfigCreateRequest(
                asset_id=asset_id,
                family_name="OldFamily",
                font_weight="400",
                font_style="normal",
            ),
            commit=True,
        )

        # 外部开启事务，不立即 commit
        renamed = await service.rename_font_family(
            ws_id,
            created.family_id,
            WorkspaceFontFamilyUpdateRequest(name="NewFamily"),
            commit=False,
        )
        assert renamed.name == "NewFamily"
        await session.commit()

        # 验证已生效
        verified = await service.get_workspace_font_family(ws_id, created.family_id)
        assert verified.name == "NewFamily"
