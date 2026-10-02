"""文件功能：系统设置管理接口，供平台管理员查看、修改类 B 动态配置并测试对象存储连通性。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_platform_admin
from app.db.session import get_db_session
from app.schemas.system_setting import (
    S3TestConnectionRequest,
    S3TestConnectionResponse,
    SystemSettingsListResponse,
    SystemSettingsUpdateRequest,
)
from app.services.auth_service import AuthContext
from app.services.system_settings_service import SystemSettingsService

router = APIRouter(dependencies=[Depends(require_platform_admin)])


@router.get("", response_model=SystemSettingsListResponse)
async def get_admin_settings(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SystemSettingsListResponse:
    """获取系统全量设置列表（按分类分组、附带掩码脱敏与 Safe-Mode 警告）。"""
    return await SystemSettingsService(session).list_settings()


@router.put("", response_model=SystemSettingsListResponse)
async def update_admin_settings(
    payload: SystemSettingsUpdateRequest,
    current: Annotated[AuthContext, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SystemSettingsListResponse:
    """批量更新系统设置并触发进程内原子热更新。"""
    return await SystemSettingsService(session).update_settings(
        payload.settings,
        user_id=current.user.id,
    )


@router.post("/storage/test-connection", response_model=S3TestConnectionResponse)
async def test_s3_storage_connection(
    payload: S3TestConnectionRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> S3TestConnectionResponse:
    """实测 S3 兼容对象存储连通性与 Bucket 读写/权限。"""
    return await SystemSettingsService(session).test_s3_connection(payload)
