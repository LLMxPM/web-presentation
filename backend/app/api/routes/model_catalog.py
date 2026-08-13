"""文件功能：提供 Models.dev 聊天目录查询和管理员同步接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.db.session import get_db_session
from app.models.enums import UserRole
from app.schemas.model_catalog import ChatModelCatalogItem, ChatProviderCatalogItem, ModelCatalogSyncItem
from app.services.ai_model_catalog_service import AiModelCatalogService
from app.services.auth_service import AuthContext

router = APIRouter(prefix="/ai")


@router.get("/chat-provider-catalog", response_model=list[ChatProviderCatalogItem])
async def list_chat_provider_catalog(
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    query: str | None = Query(default=None, max_length=128),
) -> list[ChatProviderCatalogItem]:
    """查询平台当前可运行协议覆盖的聊天供应商。"""

    del current
    items = await AiModelCatalogService(session).list_providers(query=query)
    return [
        ChatProviderCatalogItem(
            provider_key=item.provider_key,
            name=item.name,
            api_url=item.api_url,
            docs_url=item.docs_url,
            default_base_url=item.default_base_url,
            protocol_key=item.protocol_key,
            catalog_version=item.catalog_version,
            synced_at=item.synced_at.isoformat() if item.synced_at else None,
        )
        for item in items
    ]


@router.get("/chat-provider-catalog/{provider_key}/models", response_model=list[ChatModelCatalogItem])
async def list_chat_model_catalog(
    provider_key: str,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    query: str | None = Query(default=None, max_length=128),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[ChatModelCatalogItem]:
    """分页搜索供应商当前模型。"""

    del current
    items = await AiModelCatalogService(session).list_models(provider_key, query=query, offset=offset, limit=limit)
    return [
        ChatModelCatalogItem(
            provider_key=item.provider_key,
            model_id=item.model_id,
            name=item.name,
            family=item.family,
            status=item.status,
            release_date=item.release_date,
            last_updated=item.last_updated,
            context_tokens=item.context_tokens,
            input_tokens=item.input_tokens,
            output_tokens=item.output_tokens,
            input_modalities=list(item.input_modalities_json or []),
            output_modalities=list(item.output_modalities_json or []),
            supports_tool_call=item.supports_tool_call,
            supports_structured_output=item.supports_structured_output,
            supports_attachment=item.supports_attachment,
            supports_reasoning=item.supports_reasoning,
            reasoning_options=dict(item.reasoning_options_json or {}),
            catalog_version=item.catalog_version,
            synced_at=item.synced_at.isoformat() if item.synced_at else None,
        )
        for item in items
    ]


@router.get("/model-catalog-sync", response_model=ModelCatalogSyncItem)
async def get_model_catalog_sync_state(
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ModelCatalogSyncItem:
    """返回目录版本和最后同步结果。"""

    del current
    state = await AiModelCatalogService(session).get_state()
    return _to_sync_item(state)


@router.post("/model-catalog-sync", response_model=ModelCatalogSyncItem)
async def sync_model_catalog(
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ModelCatalogSyncItem:
    """由平台管理员强制刷新 Models.dev 缓存。"""

    if current.user.role != UserRole.PLATFORM_ADMIN.value:
        raise AppException(status_code=403, code="AI_MODEL_CATALOG_ADMIN_REQUIRED", detail="只有平台管理员可以同步模型目录。")
    return _to_sync_item(await AiModelCatalogService(session).sync(force=True))


def _to_sync_item(state) -> ModelCatalogSyncItem:  # noqa: ANN001
    """把 ORM 同步状态转换为脱离数据库的接口对象。"""

    now = utc_now()
    return ModelCatalogSyncItem(
        catalog_version=state.catalog_version,
        last_attempt_at=state.last_attempt_at.isoformat() if state.last_attempt_at else None,
        last_success_at=state.last_success_at.isoformat() if state.last_success_at else None,
        last_error=state.last_error,
        syncing=bool(state.lease_expires_at and state.lease_expires_at > now),
    )
