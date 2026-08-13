"""文件功能：提供拆分后的 Chat 与图片模型配置 CRUD 和槽位绑定接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.schemas.common import MessageResponse
from app.schemas.model_config import (
    ChatBindingItem, ChatBindingUpdate, ChatModelConfigCreate, ChatModelConfigItem, ChatModelConfigUpdate,
    ChatProviderConfigCreate, ChatProviderConfigItem, ChatProviderConfigUpdate,
    ImageBindingItem, ImageBindingUpdate, ImageModelConfigCreate, ImageModelConfigItem, ImageModelConfigUpdate,
    ImageProviderCatalogItem, ImageProviderConfigCreate, ImageProviderConfigItem, ImageProviderConfigUpdate,
)
from app.services.ai_chat_config_service import AiChatConfigService
from app.services.ai_image_config_service import AiImageConfigService
from app.services.auth_service import AuthContext

router = APIRouter(prefix="/ai")


def _chat(session: AsyncSession, current: AuthContext) -> AiChatConfigService:
    """构造当前用户聊天配置服务。"""

    return AiChatConfigService(session, user_id=current.user.id, user_role=current.user.role)


def _image(session: AsyncSession, current: AuthContext) -> AiImageConfigService:
    """构造当前用户图片配置服务。"""

    return AiImageConfigService(session, user_id=current.user.id, user_role=current.user.role)


@router.get("/chat-provider-configs", response_model=list[ChatProviderConfigItem])
async def list_chat_providers(current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _chat(session, current).list_providers()


@router.post("/chat-provider-configs", response_model=ChatProviderConfigItem, status_code=201)
async def create_chat_provider(payload: ChatProviderConfigCreate, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _chat(session, current).create_provider(payload, operator_id=current.user.id)


@router.patch("/chat-provider-configs/{row_id}", response_model=ChatProviderConfigItem)
async def update_chat_provider(row_id: int, payload: ChatProviderConfigUpdate, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _chat(session, current).update_provider(row_id, payload, operator_id=current.user.id)


@router.delete("/chat-provider-configs/{row_id}", response_model=MessageResponse)
async def delete_chat_provider(row_id: int, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    await _chat(session, current).delete_provider(row_id)
    return MessageResponse(message="聊天供应商已删除。")


@router.get("/chat-model-configs", response_model=list[ChatModelConfigItem])
async def list_chat_models(current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _chat(session, current).list_models()


@router.post("/chat-model-configs", response_model=ChatModelConfigItem, status_code=201)
async def create_chat_model(payload: ChatModelConfigCreate, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _chat(session, current).create_model(payload, operator_id=current.user.id)


@router.patch("/chat-model-configs/{row_id}", response_model=ChatModelConfigItem)
async def update_chat_model(row_id: int, payload: ChatModelConfigUpdate, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _chat(session, current).update_model(row_id, payload, operator_id=current.user.id)


@router.delete("/chat-model-configs/{row_id}", response_model=MessageResponse)
async def delete_chat_model(row_id: int, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    await _chat(session, current).delete_model(row_id)
    return MessageResponse(message="聊天模型已删除。")


@router.get("/chat-model-bindings/{slot}", response_model=ChatBindingItem)
async def get_chat_binding(slot: str, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _chat(session, current).get_binding(slot)


@router.put("/chat-model-bindings/{slot}", response_model=ChatBindingItem)
async def update_chat_binding(slot: str, payload: ChatBindingUpdate, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _chat(session, current).update_binding(slot, payload, operator_id=current.user.id)


@router.get("/image-provider-catalog", response_model=list[ImageProviderCatalogItem])
async def list_image_catalog(current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return _image(session, current).list_catalog()


@router.get("/image-provider-configs", response_model=list[ImageProviderConfigItem])
async def list_image_providers(current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _image(session, current).list_providers()


@router.post("/image-provider-configs", response_model=ImageProviderConfigItem, status_code=201)
async def create_image_provider(payload: ImageProviderConfigCreate, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _image(session, current).create_provider(payload, operator_id=current.user.id)


@router.patch("/image-provider-configs/{row_id}", response_model=ImageProviderConfigItem)
async def update_image_provider(row_id: int, payload: ImageProviderConfigUpdate, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _image(session, current).update_provider(row_id, payload, operator_id=current.user.id)


@router.delete("/image-provider-configs/{row_id}", response_model=MessageResponse)
async def delete_image_provider(row_id: int, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    await _image(session, current).delete_provider(row_id)
    return MessageResponse(message="图片供应商已删除。")


@router.get("/image-model-configs", response_model=list[ImageModelConfigItem])
async def list_image_models(current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _image(session, current).list_models()


@router.post("/image-model-configs", response_model=ImageModelConfigItem, status_code=201)
async def create_image_model(payload: ImageModelConfigCreate, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _image(session, current).create_model(payload, operator_id=current.user.id)


@router.patch("/image-model-configs/{row_id}", response_model=ImageModelConfigItem)
async def update_image_model(row_id: int, payload: ImageModelConfigUpdate, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    return await _image(session, current).update_model(row_id, payload, operator_id=current.user.id)


@router.delete("/image-model-configs/{row_id}", response_model=MessageResponse)
async def delete_image_model(row_id: int, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    await _image(session, current).delete_model(row_id)
    return MessageResponse(message="图片模型已删除。")


@router.get("/image-model-bindings/{slot}", response_model=ImageBindingItem)
async def get_image_binding(slot: str, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    if slot != "image_generation":
        from app.core.exceptions import AppException
        raise AppException(status_code=400, code="AI_IMAGE_SLOT_UNSUPPORTED", detail="图片模型只支持 image_generation 槽位。")
    return await _image(session, current).get_binding()


@router.put("/image-model-bindings/{slot}", response_model=ImageBindingItem)
async def update_image_binding(slot: str, payload: ImageBindingUpdate, current: Annotated[AuthContext, Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db_session)]):
    if slot != "image_generation":
        from app.core.exceptions import AppException
        raise AppException(status_code=400, code="AI_IMAGE_SLOT_UNSUPPORTED", detail="图片模型只支持 image_generation 槽位。")
    return await _image(session, current).update_binding(payload, operator_id=current.user.id)
