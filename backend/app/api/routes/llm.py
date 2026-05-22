"""文件功能：提供用户级大模型配置、供应商目录与固定槽位绑定接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.schemas.llm import (
    LlmConfigCreateRequest,
    LlmConfigItem,
    LlmConfigUpdateRequest,
    LlmProviderCatalogItem,
    LlmSlotBindingItem,
    LlmSlotBindingUpdateRequest,
)
from app.services.ai_llm_service import AiLlmService
from app.services.auth_service import AuthContext

router = APIRouter(prefix="/ai")


@router.get("/llm-providers", response_model=list[LlmProviderCatalogItem])
async def list_llm_providers(
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[LlmProviderCatalogItem]:
    """返回当前后端支持的供应商目录。"""

    return await AiLlmService(session, user_id=current.user.id, user_role=current.user.role).list_provider_catalog()


@router.get("/llm-configs", response_model=list[LlmConfigItem])
async def list_llm_configs(
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[LlmConfigItem]:
    """列出当前用户维护的大模型配置。"""

    return await AiLlmService(session, user_id=current.user.id, user_role=current.user.role).list_configs()


@router.post("/llm-configs", response_model=LlmConfigItem, status_code=201)
async def create_llm_config(
    payload: LlmConfigCreateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LlmConfigItem:
    """创建新的大模型配置。"""

    return await AiLlmService(session, user_id=current.user.id, user_role=current.user.role).create_config(
        payload,
        operator_id=current.user.id,
    )


@router.get("/llm-configs/{config_id}", response_model=LlmConfigItem)
async def get_llm_config(
    config_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LlmConfigItem:
    """读取单条大模型配置详情。"""

    return await AiLlmService(session, user_id=current.user.id, user_role=current.user.role).get_config(config_id)


@router.patch("/llm-configs/{config_id}", response_model=LlmConfigItem)
async def update_llm_config(
    config_id: int,
    payload: LlmConfigUpdateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LlmConfigItem:
    """更新指定的大模型配置。"""

    return await AiLlmService(session, user_id=current.user.id, user_role=current.user.role).update_config(
        config_id,
        payload,
        operator_id=current.user.id,
    )


@router.get("/llm-slots", response_model=list[LlmSlotBindingItem])
async def list_llm_slots(
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[LlmSlotBindingItem]:
    """列出当前用户全部固定槽位的绑定状态。"""

    return await AiLlmService(session, user_id=current.user.id, user_role=current.user.role).list_slot_bindings()


@router.put("/llm-slots/{slot}", response_model=LlmSlotBindingItem)
async def update_llm_slot(
    slot: str,
    payload: LlmSlotBindingUpdateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LlmSlotBindingItem:
    """更新指定固定槽位绑定的大模型配置。"""

    return await AiLlmService(session, user_id=current.user.id, user_role=current.user.role).update_slot_binding(
        slot,
        payload,
        operator_id=current.user.id,
    )
