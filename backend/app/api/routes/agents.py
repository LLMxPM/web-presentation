"""文件功能：提供 Editor 内容助手使用的 BFF 路由，负责会话管理、会话命名与 Agno 运行代理。"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.registry import AgentRegistry
from app.ai.run_background import get_agent_run_manager
from app.ai.runtime_context_builder import build_agent_runtime_context
from app.ai.session_facade import AgentSessionFacade
from app.api.dependencies import get_current_user
from app.core.exceptions import AppException
from app.db.session import get_db_session, get_session_factory
from app.schemas.agent import (
    AgentActiveRunItem,
    AgentCancelRunRequest,
    AgentCancelRunResponse,
    AgentContinueRunRequest,
    AgentContextStatusItem,
    AgentDescriptor,
    AgentImageAttachmentItem,
    AgentImageAttachmentPromoteRequest,
    AgentMessageItem,
    AgentRunStartResponse,
    AgentScopeContext,
    AgentSessionItem,
    AgentSessionRuntimeSnapshot,
    AgentRunRequest,
    CreateAgentSessionRequest,
    RenameAgentSessionRequest,
)
from app.schemas.common import MessageResponse
from app.schemas.agent_config import (
    AgentCatalogItem,
    AgentConfigItem,
    AgentConfigUpdateRequest,
    AgentToolConfigUpdateRequest,
)
from app.models.ai_agent_run import AiAgentRunTask
from app.services.ai_agent_config_service import AiAgentConfigService
from app.services.ai_agent_run_service import (
    AiAgentRunService,
    build_agent_run_input_payload,
    task_is_active,
)
from app.services.ai_llm_service import AiLlmService
from app.services.agent_image_attachment_service import AgentImageAttachmentService
from app.services.auth_service import AuthContext
from app.services.page_service import PageService
from app.services.project_service import ProjectService
from app.services.workspace_component_service import WorkspaceComponentService
from app.repositories.workspace_repository import WorkspaceRepository
from app.ai.agent import AGENT_COORDINATOR_AGENT_ID, COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID, AgentRuntimeContext
from app.ai.registry import RegisteredAgentDescriptor

router = APIRouter(prefix="/ai")
CONTENT_AGENT_PROJECT_REQUIRED_REASON = "内容助手需要进入具体项目后才能启动。"


@router.get("/agents", response_model=list[AgentDescriptor])
async def list_agents(
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str | None = None,
) -> list[AgentDescriptor]:
    """返回当前页面范围内可用的 Agent 列表。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    registry = _get_agent_registry(request)
    slot_lookup = await AiLlmService(session, user_id=current.user.id).get_slot_binding_lookup()
    config_service = AiAgentConfigService(session, user_id=current.user.id)
    descriptors = registry.list_descriptors()
    if agent_id:
        descriptors = [registry.get_descriptor(agent_id)]
    result: list[AgentDescriptor] = []
    for descriptor in descriptors:
        agent_config = await config_service.get_config_summary(descriptor.id)
        binding = slot_lookup.get(descriptor.llm_slot) if descriptor.llm_slot else None
        required_llm_slots = _resolve_required_llm_slots(registry, descriptor)
        llm_binding_ready = bool(required_llm_slots) and all(
            bool((slot_lookup.get(slot) if slot else None) and slot_lookup[slot].binding_ready)
            for slot in required_llm_slots
        )
        result.append(
            AgentDescriptor(
                id=descriptor.id,
                name=descriptor.name,
                icon=descriptor.icon,
                summary=descriptor.summary,
                default_session_name=descriptor.default_session_name,
                capabilities=list(descriptor.capabilities),
                scope_type=descriptor.scope_type,
                entry_kind=descriptor.entry_kind,  # type: ignore[arg-type]
                available=_is_agent_available(descriptor, scope),
                unavailable_reason=_resolve_unavailable_reason(descriptor, scope),
                llm_slot=descriptor.llm_slot,
                llm_binding_ready=llm_binding_ready,
                bound_llm_name=binding.llm_config_name if binding else None,
                bound_provider_label=binding.provider_label if binding else None,
                supports_image_input=binding.supports_image_input if binding else False,
                prompt_customized=agent_config.prompt_customized,
                enabled_tool_count=agent_config.enabled_tool_count,
                disabled_tool_count=agent_config.disabled_tool_count,
                scope=scope,
            )
        )
    return result


@router.get("/agent-catalog", response_model=list[AgentCatalogItem])
async def list_agent_catalog(
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AgentCatalogItem]:
    """返回系统内置智能体、默认提示词与工具目录。"""

    return await AiAgentConfigService(session, user_id=current.user.id).list_agent_catalog()


@router.get("/agent-configs", response_model=list[AgentConfigItem])
async def list_agent_configs(
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AgentConfigItem]:
    """返回当前用户的智能体有效配置。"""

    return await AiAgentConfigService(session, user_id=current.user.id).list_configs()


@router.patch("/agent-configs/{agent_id}", response_model=AgentConfigItem)
async def update_agent_config(
    agent_id: str,
    payload: AgentConfigUpdateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentConfigItem:
    """更新当前用户的智能体业务补充提示词，或恢复默认。"""

    return await AiAgentConfigService(session, user_id=current.user.id).update_agent_config(
        agent_id,
        payload,
        operator_id=current.user.id,
    )


@router.patch("/agent-configs/{agent_id}/tools/{tool_key}", response_model=AgentConfigItem)
async def update_agent_tool_config(
    agent_id: str,
    tool_key: str,
    payload: AgentToolConfigUpdateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentConfigItem:
    """更新当前用户的单个工具开关与工具提示词覆盖，或恢复工具默认配置。"""

    return await AiAgentConfigService(session, user_id=current.user.id).update_tool_config(
        agent_id,
        tool_key,
        payload,
        operator_id=current.user.id,
    )


@router.get("/sessions", response_model=list[AgentSessionItem])
async def list_agent_sessions(
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> list[AgentSessionItem]:
    """列出当前页面范围下的 Agent 会话。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_available(descriptor, scope)
    return await AgentSessionFacade(app=request.app, current=current, session=session).list_sessions(
        agent_id=agent_id,
        scope=scope,
    )


@router.post("/sessions", response_model=AgentSessionItem, status_code=201)
async def create_agent_session(
    payload: CreateAgentSessionRequest,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentSessionItem:
    """创建一个绑定当前页面的 Agent 会话。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=payload.scope.workspace_id,
        project_id=payload.scope.project_id,
        page_id=payload.scope.page_id,
        component_id=payload.scope.component_id,
        scope_type=payload.scope.scope_type,
        source=payload.scope.source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(payload.agent_id)
    _ensure_agent_launch_available(descriptor, scope)
    session_name = payload.session_name or descriptor.default_session_name
    return await AgentSessionFacade(app=request.app, current=current, session=session).create_session(
        agent_id=payload.agent_id,
        scope=scope,
        session_name=session_name,
    )


@router.patch("/sessions/{session_id}", response_model=AgentSessionItem)
async def rename_agent_session(
    session_id: str,
    payload: RenameAgentSessionRequest,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> AgentSessionItem:
    """重命名或自动命名当前页面范围内的 Agent 会话。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_available(descriptor, scope)
    runtime_context = await _build_runtime_context(session=session, scope=scope)
    return await AgentSessionFacade(app=request.app, current=current, session=session).rename_session(
        session_id=session_id,
        agent_id=agent_id,
        scope=scope,
        session_name=payload.session_name,
        autogenerate=payload.autogenerate,
        runtime_context=runtime_context,
    )


@router.get("/sessions/{session_id}/messages", response_model=list[AgentMessageItem])
async def get_agent_session_messages(
    session_id: str,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> list[AgentMessageItem]:
    """读取当前页面范围下的 Agent 会话消息。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_available(descriptor, scope)
    return await AgentSessionFacade(app=request.app, current=current, session=session).get_messages(
        session_id=session_id,
        agent_id=agent_id,
        scope=scope,
    )


@router.get("/sessions/{session_id}/runtime", response_model=AgentSessionRuntimeSnapshot)
async def get_agent_session_runtime(
    session_id: str,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> AgentSessionRuntimeSnapshot:
    """返回当前会话的完整运行时快照，供 Editor 刷新后恢复状态。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_available(descriptor, scope)
    runtime_context = await _build_runtime_context(session=session, scope=scope)
    return await AgentSessionFacade(app=request.app, current=current, session=session).get_runtime_snapshot(
        session_id=session_id,
        agent_id=agent_id,
        scope=scope,
        runtime_context=runtime_context,
    )


@router.post("/sessions/{session_id}/attachments/images", response_model=AgentImageAttachmentItem, status_code=201)
async def upload_agent_image_attachment(
    session_id: str,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    file: Annotated[UploadFile, File(...)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> AgentImageAttachmentItem:
    """上传一张会话图片附件，供后续 Agent run 作为视觉输入。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_available(descriptor, scope)
    await AgentSessionFacade(app=request.app, current=current, session=session).ensure_session_access(
        session_id=session_id,
        agent_id=agent_id,
        scope=scope,
    )
    return await AgentImageAttachmentService(session, user_id=current.user.id).upload_image_attachment(
        workspace_id=scope.workspace_id,
        session_id=session_id,
        file=file,
        operator_id=current.user.id,
    )


@router.get("/sessions/{session_id}/attachments/images/{attachment_id}/content")
async def get_agent_image_attachment_content(
    session_id: str,
    attachment_id: int,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> Response:
    """返回会话图片附件原始内容，用于登录态下的缩略图预览。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_available(descriptor, scope)
    await AgentSessionFacade(app=request.app, current=current, session=session).ensure_session_access(
        session_id=session_id,
        agent_id=agent_id,
        scope=scope,
    )
    attachment, content = await AgentImageAttachmentService(
        session,
        user_id=current.user.id,
    ).read_attachment_content(
        workspace_id=scope.workspace_id,
        session_id=session_id,
        attachment_id=attachment_id,
    )
    return Response(content=content, media_type=attachment.content_type)


@router.delete("/sessions/{session_id}/attachments/images/{attachment_id}", response_model=MessageResponse)
async def delete_agent_image_attachment(
    session_id: str,
    attachment_id: int,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> MessageResponse:
    """软删除会话图片附件。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_available(descriptor, scope)
    await AgentSessionFacade(app=request.app, current=current, session=session).ensure_session_access(
        session_id=session_id,
        agent_id=agent_id,
        scope=scope,
    )
    await AgentImageAttachmentService(session, user_id=current.user.id).archive_attachment(
        workspace_id=scope.workspace_id,
        session_id=session_id,
        attachment_id=attachment_id,
        operator_id=current.user.id,
    )
    return MessageResponse(message="图片附件已删除。")


@router.post("/sessions/{session_id}/attachments/images/{attachment_id}/promote", response_model=AgentImageAttachmentItem)
async def promote_agent_image_attachment(
    session_id: str,
    attachment_id: int,
    payload: AgentImageAttachmentPromoteRequest,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> AgentImageAttachmentItem:
    """把会话图片附件保存为工作空间 image 资源。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_available(descriptor, scope)
    await AgentSessionFacade(app=request.app, current=current, session=session).ensure_session_access(
        session_id=session_id,
        agent_id=agent_id,
        scope=scope,
    )
    return await AgentImageAttachmentService(session, user_id=current.user.id).promote_attachment_to_asset(
        workspace_id=scope.workspace_id,
        session_id=session_id,
        attachment_id=attachment_id,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        overwrite=payload.overwrite,
        operator_id=current.user.id,
    )


@router.post("/sessions/{session_id}/runs", response_model=AgentRunStartResponse, status_code=202)
async def start_agent_run(
    session_id: str,
    payload: AgentRunRequest,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> AgentRunStartResponse:
    """创建后台 run 并返回事件订阅游标。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    run_id = await _start_agent_run_task(
        session_id=session_id,
        payload=payload,
        request=request,
        current=current,
        session=session,
        scope=scope,
        agent_id=agent_id,
    )
    return AgentRunStartResponse(run_id=run_id, session_id=session_id, status="pending", event_cursor=0)


@router.post("/sessions/{session_id}/runs/stream")
async def stream_agent_run(
    session_id: str,
    payload: AgentRunRequest,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> StreamingResponse:
    """向 Agent 发送消息，并把运行事件以 SSE 方式转发给 Editor。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    run_id = await _start_agent_run_task(
        session_id=session_id,
        payload=payload,
        request=request,
        current=current,
        session=session,
        scope=scope,
        agent_id=agent_id,
    )
    return StreamingResponse(
        get_agent_run_manager(request.app).stream_sse_events(run_id=run_id, current=current),
        media_type="text/event-stream",
    )


async def _start_agent_run_task(
    *,
    session_id: str,
    payload: AgentRunRequest,
    request: Request,
    current: AuthContext,
    session: AsyncSession,
    scope: AgentScopeContext,
    agent_id: str,
) -> str:
    """校验请求并启动后台 run，供新旧入口复用。"""

    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_launch_available(descriptor, scope)
    runtime_context = await _build_runtime_context(session=session, scope=scope)
    facade = AgentSessionFacade(app=request.app, current=current, session=session)
    model_supports_image_input = False
    try:
        model_config = await AiLlmService(session, user_id=current.user.id).get_bound_config_or_raise(descriptor.llm_slot or "")
        model_supports_image_input = bool(model_config.supports_image_input)
    except AppException:
        if payload.image_attachment_ids:
            raise
    if payload.image_attachment_ids:
        if not model_supports_image_input:
            raise AppException(
                status_code=409,
                code="AI_LLM_IMAGE_INPUT_UNSUPPORTED",
                detail="当前绑定模型不支持图片输入，不能发送图片附件。",
            )
        await AgentImageAttachmentService(session, user_id=current.user.id).validate_attachments_for_run(
            workspace_id=scope.workspace_id,
            session_id=session_id,
            attachment_ids=payload.image_attachment_ids,
        )
    agent_config = await AiAgentConfigService(session, user_id=current.user.id).get_effective_runtime_config(agent_id)
    tool_scopes = AgentSessionFacade._resolve_tool_scopes(
        agent_id=agent_id,
        agent_config=agent_config,
        supports_image_input=model_supports_image_input,
    )
    reserved_lock = await facade.reserve_run_slot(session_id=session_id, agent_id=agent_id, scope=scope)
    run_id = str(uuid4())
    try:
        await AiAgentRunService(session).create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=agent_id,
            user_id=current.user.id,
            backend_session_id=current.backend_session_id,
            scope=scope,
            input_summary=payload.message,
            input_payload_json=build_agent_run_input_payload(
                message=payload.message,
                image_attachment_ids=payload.image_attachment_ids,
            ),
            tool_scopes=tool_scopes,
        )
        manager = get_agent_run_manager(request.app)
        await manager.start_run(
            app=request.app,
            current=current,
            session_id=session_id,
            agent_id=agent_id,
            scope=scope,
            runtime_context=runtime_context,
            message=payload.message,
            image_attachment_ids=payload.image_attachment_ids,
            reserved_lock=reserved_lock,
            run_id=run_id,
        )
    except Exception:
        if reserved_lock.locked():
            reserved_lock.release()
        raise
    return run_id


@router.get("/sessions/{session_id}/runs/{run_id}/events/stream")
async def stream_agent_run_events(
    session_id: str,
    run_id: str,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
    after_sequence: int = 0,
) -> StreamingResponse:
    """订阅或回放指定 run 的后台事件流。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_available(descriptor, scope)
    await AgentSessionFacade(app=request.app, current=current, session=session).ensure_session_access(
        session_id=session_id,
        agent_id=agent_id,
        scope=scope,
    )
    task = await AiAgentRunService(session).get_task_by_run(run_id=run_id, user_id=current.user.id)
    if task is None or task.session_id != session_id or task.agent_id != agent_id:
        raise AppException(status_code=404, code="AI_RUN_NOT_FOUND", detail="智能体运行记录不存在。")
    return StreamingResponse(
        get_agent_run_manager(request.app).stream_sse_events(
            run_id=run_id,
            current=current,
            after_sequence=after_sequence,
        ),
        media_type="text/event-stream",
    )


@router.get("/runs/{run_id}/events")
async def stream_agent_run_events_by_run(
    run_id: str,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
    after_sequence: int = 0,
) -> StreamingResponse:
    """按 run_id 订阅或回放后台事件流。"""

    await _get_authorized_run_task_or_raise(session=session, run_id=run_id, current=current)
    return StreamingResponse(
        get_agent_run_manager(request.app).stream_sse_events(
            run_id=run_id,
            current=current,
            after_sequence=after_sequence,
        ),
        media_type="text/event-stream",
    )


@router.post("/runs/{run_id}/continue")
async def continue_agent_run_by_run_id(
    run_id: str,
    payload: AgentContinueRunRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> AgentRunStartResponse:
    """按 run_id 继续当前暂停运行。"""

    task = await _get_authorized_run_task_or_raise(session=session, run_id=run_id, current=current)
    if task.status != "paused":
        raise AppException(status_code=409, code="AI_SESSION_RUN_NOT_PAUSED", detail="当前运行不处于暂停态。")
    scope = _scope_from_run_task(task)
    descriptor = _get_agent_registry(request).get_descriptor(task.agent_id)
    _ensure_agent_launch_available(descriptor, scope)
    runtime_context = await _build_runtime_context(session=session, scope=scope)
    facade = AgentSessionFacade(app=request.app, current=current, session=session)
    active_run = await facade.get_active_run(
        session_id=task.session_id,
        agent_id=task.agent_id,
        scope=scope,
        runtime_context=runtime_context,
    )
    if active_run is None or active_run.status != "paused" or active_run.run_id != run_id:
        raise AppException(status_code=409, code="AI_SESSION_RUN_NOT_PAUSED", detail="当前会话没有待继续的智能体运行。")
    await AiAgentRunService(session).mark_running(task=task, reset_tool_auth=True)
    await get_agent_run_manager(request.app).start_continue(
        app=request.app,
        current=current,
        session_id=task.session_id,
        agent_id=task.agent_id,
        scope=scope,
        runtime_context=runtime_context,
        tool_execution=payload.tool_execution,
        decision=payload.decision,
        note=payload.note,
        feedback_selections=payload.feedback_selections,
        run_id=run_id,
    )
    return AgentRunStartResponse(run_id=run_id, session_id=task.session_id, status="pending", event_cursor=active_run.event_sequence)


@router.post("/runs/{run_id}/cancel", response_model=AgentCancelRunResponse)
async def cancel_agent_run_by_run_id(
    run_id: str,
    payload: AgentCancelRunRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> AgentCancelRunResponse:
    """按 run_id 中断或强制结束当前运行。"""

    task = await _get_authorized_run_task_or_raise(session=session, run_id=run_id, current=current)
    if not task_is_active(task):
        raise AppException(status_code=409, code="AI_RUN_NOT_ACTIVE", detail="当前运行已结束，不能取消。")
    response = await get_agent_run_manager(request.app).cancel_active_run(
        app=request.app,
        current=current,
        session_id=task.session_id,
        agent_id=task.agent_id,
        scope=_scope_from_run_task(task),
        force=payload.force,
    )
    if response.cancel_requested:
        ai_db = getattr(request.app.state, "ai_db", None)
        if ai_db is not None:
            async with get_session_factory()() as preserve_session:
                await AiAgentRunService(preserve_session).preserve_user_cancelled_run_output(ai_db=ai_db, task=task)
    return response


async def _get_authorized_run_task_or_raise(
    *,
    session: AsyncSession,
    run_id: str,
    current: AuthContext,
) -> AiAgentRunTask:
    """按 run_id 读取当前用户可访问的后台任务。"""

    task = await AiAgentRunService(session).get_task_by_run(run_id=run_id, user_id=current.user.id)
    if task is None:
        raise AppException(status_code=404, code="AI_RUN_NOT_FOUND", detail="智能体运行记录不存在。")
    return task


def _scope_from_run_task(task: AiAgentRunTask) -> AgentScopeContext:
    """从 run task 还原执行时绑定的业务范围。"""

    return AgentScopeContext(
        scope_type=task.scope_type,  # type: ignore[arg-type]
        workspace_id=task.workspace_id,
        project_id=task.project_id,
        page_id=task.page_id,
        component_id=task.component_id,
        source=task.source,
    )


@router.get("/sessions/{session_id}/active-run", response_model=AgentActiveRunItem | None)
async def get_agent_session_active_run(
    session_id: str,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> AgentActiveRunItem | None:
    """读取当前会话最近一次 Agno run 状态。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_available(descriptor, scope)
    runtime_context = await _build_runtime_context(session=session, scope=scope)
    facade = AgentSessionFacade(app=request.app, current=current, session=session)
    return await facade.get_active_run(
        session_id=session_id,
        agent_id=agent_id,
        scope=scope,
        runtime_context=runtime_context,
    )


@router.get("/sessions/{session_id}/context-status", response_model=AgentContextStatusItem)
async def get_agent_session_context_status(
    session_id: str,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> AgentContextStatusItem:
    """读取当前会话上下文预算、压缩状态与摘要详情。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_available(descriptor, scope)
    runtime_context = await _build_runtime_context(session=session, scope=scope)
    facade = AgentSessionFacade(app=request.app, current=current, session=session)
    return await facade.get_context_status(
        session_id=session_id,
        agent_id=agent_id,
        scope=scope,
        runtime_context=runtime_context,
    )


@router.post("/sessions/{session_id}/active-run/cancel", response_model=AgentCancelRunResponse)
async def cancel_agent_session_active_run(
    session_id: str,
    payload: AgentCancelRunRequest,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> AgentCancelRunResponse:
    """取消当前会话中未结束的 Agno run。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_available(descriptor, scope)
    return await get_agent_run_manager(request.app).cancel_active_run(
        app=request.app,
        current=current,
        session_id=session_id,
        agent_id=agent_id,
        scope=scope,
        force=payload.force,
    )


@router.post("/sessions/{session_id}/active-run/continue")
async def continue_agent_session_active_run(
    session_id: str,
    payload: AgentContinueRunRequest,
    workspace_id: int,
    request: Request,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
    agent_id: str = "agent-coordinator",
) -> StreamingResponse:
    """继续当前会话中暂停等待确认的 Agno run。"""

    scope = await _resolve_scope_context(
        session=session,
        user_id=current.user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        scope_type=scope_type,
        source=source,
    )
    descriptor = _get_agent_registry(request).get_descriptor(agent_id)
    _ensure_agent_launch_available(descriptor, scope)
    runtime_context = await _build_runtime_context(session=session, scope=scope)
    facade = AgentSessionFacade(app=request.app, current=current, session=session)
    active_run = await facade.get_active_run(
        session_id=session_id,
        agent_id=agent_id,
        scope=scope,
        runtime_context=runtime_context,
    )
    if active_run is None or active_run.status != "paused":
        raise AppException(status_code=409, code="AI_SESSION_RUN_NOT_PAUSED", detail="当前会话没有待继续的智能体运行。")
    run_id = active_run.run_id
    task_service = AiAgentRunService(session)
    existing_task = await task_service.get_task_by_run(run_id=run_id, user_id=current.user.id)
    model_supports_image_input = False
    try:
        model_config = await AiLlmService(session, user_id=current.user.id).get_bound_config_or_raise(descriptor.llm_slot or "")
        model_supports_image_input = bool(model_config.supports_image_input)
    except AppException:
        model_supports_image_input = False
    agent_config = await AiAgentConfigService(session, user_id=current.user.id).get_effective_runtime_config(agent_id)
    tool_scopes = AgentSessionFacade._resolve_tool_scopes(
        agent_id=agent_id,
        agent_config=agent_config,
        supports_image_input=model_supports_image_input,
    )
    if existing_task is None:
        existing_task = await task_service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=agent_id,
            user_id=current.user.id,
            backend_session_id=current.backend_session_id,
            scope=scope,
            input_summary="继续已暂停的智能体运行。",
            tool_scopes=tool_scopes,
        )
    elif task_is_active(existing_task) and existing_task.status != "paused":
        raise AppException(status_code=409, code="AI_SESSION_RUN_ACTIVE", detail="当前会话已有运行中的智能体任务。")
    await task_service.mark_running(task=existing_task, reset_tool_auth=True)
    await get_agent_run_manager(request.app).start_continue(
        app=request.app,
        current=current,
        session_id=session_id,
        agent_id=agent_id,
        scope=scope,
        runtime_context=runtime_context,
        tool_execution=payload.tool_execution,
        decision=payload.decision,
        note=payload.note,
        feedback_selections=payload.feedback_selections,
        run_id=run_id,
    )
    return StreamingResponse(
        get_agent_run_manager(request.app).stream_sse_events(
            run_id=run_id,
            current=current,
            after_sequence=active_run.event_sequence,
        ),
        media_type="text/event-stream",
    )


async def _resolve_scope_context(
    *,
    session: AsyncSession,
    user_id: int,
    workspace_id: int,
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
    scope_type: Literal["workspace", "project", "page", "component"] | None = None,
    source: str = "editor-page-detail",
) -> AgentScopeContext:
    """校验泛化业务范围归属，并返回标准化 scope。"""

    workspace = await WorkspaceRepository(session).get_by_id(workspace_id)
    if workspace is None:
        raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="工作空间不存在。")
    if not await WorkspaceRepository(session).has_active_member(workspace_id=workspace_id, user_id=user_id):
        raise AppException(status_code=403, code="WORKSPACE_ACCESS_DENIED", detail="无权访问该工作空间。")

    resolved_scope_type = scope_type or _infer_scope_type(project_id=project_id, page_id=page_id, component_id=component_id)
    resolved_project_id = project_id
    resolved_page_id = page_id
    resolved_component_id = component_id
    resolved_workspace_name = workspace.name
    resolved_project_name: str | None = None
    resolved_page_title: str | None = None
    resolved_component_name: str | None = None

    if page_id is not None:
        page_item = await PageService(session).get(page_id)
        if page_item.workspace_id is None or page_item.project_id is None:
            raise AppException(
                status_code=409,
                code="AI_PAGE_SCOPE_INCOMPLETE",
                detail="当前页面尚未绑定项目或工作空间，暂不支持内容助手。",
            )
        if page_item.workspace_id != workspace_id:
            raise AppException(
                status_code=403,
                code="AI_PAGE_SCOPE_DENIED",
                detail="当前页面与传入的工作空间范围不匹配。",
            )
        if project_id is not None and page_item.project_id != project_id:
            raise AppException(
                status_code=403,
                code="AI_PAGE_SCOPE_DENIED",
                detail="当前页面与传入的项目范围不匹配。",
            )
        resolved_project_id = page_item.project_id
        resolved_page_id = page_item.id
        resolved_page_title = page_item.title
        resolved_workspace_name = page_item.workspace_name or resolved_workspace_name
        resolved_project_name = page_item.project_name

    if resolved_project_id is not None:
        project = await ProjectService(session).get(resolved_project_id)
        if project.workspace_id != workspace_id:
            raise AppException(
                status_code=403,
                code="AI_PROJECT_SCOPE_DENIED",
                detail="当前项目与传入的工作空间范围不匹配。",
            )
        resolved_project_name = project.name
        resolved_workspace_name = project.workspace_name or resolved_workspace_name

    if component_id is not None:
        component = await WorkspaceComponentService(session).get(component_id)
        if component.workspace_id != workspace_id:
            raise AppException(
                status_code=403,
                code="AI_COMPONENT_SCOPE_DENIED",
                detail="当前组件与传入的工作空间范围不匹配。",
            )
        resolved_component_id = component.id
        resolved_component_name = component.name
        resolved_workspace_name = component.workspace_name or resolved_workspace_name

    if resolved_scope_type == "project" and resolved_project_id is None:
        raise AppException(
            status_code=409,
            code="AI_PROJECT_SCOPE_REQUIRED",
            detail="当前智能体范围缺少项目 ID。",
        )
    if resolved_scope_type == "page" and resolved_page_id is None:
        raise AppException(
            status_code=409,
            code="AI_PAGE_SCOPE_REQUIRED",
            detail="当前智能体范围缺少页面 ID。",
        )
    if resolved_scope_type == "component" and resolved_component_id is None:
        raise AppException(
            status_code=409,
            code="AI_COMPONENT_SCOPE_REQUIRED",
            detail="当前智能体范围缺少组件 ID。",
        )
    return AgentScopeContext(
        scope_type=resolved_scope_type,
        workspace_id=workspace_id,
        project_id=resolved_project_id,
        page_id=resolved_page_id,
        component_id=resolved_component_id,
        workspace_name=resolved_workspace_name,
        project_name=resolved_project_name,
        page_title=resolved_page_title,
        component_name=resolved_component_name,
        source=source,
    )


async def _build_runtime_context(*, session: AsyncSession, scope: AgentScopeContext) -> AgentRuntimeContext:
    """根据泛化 scope 补齐运行时上下文，供 Agent 提示词和工具预览使用。"""

    return await build_agent_runtime_context(session=session, scope=scope)


def _infer_scope_type(
    *,
    project_id: int | None,
    page_id: int | None,
    component_id: int | None,
) -> Literal["workspace", "project", "page", "component"]:
    """从旧查询参数推断 scope_type，兼容旧调用。"""

    if page_id is not None:
        return "page"
    if component_id is not None:
        return "component"
    if project_id is not None:
        return "project"
    return "workspace"


def _is_agent_available(descriptor: RegisteredAgentDescriptor, scope: AgentScopeContext) -> bool:
    """判断智能体在当前路由上下文下是否可用。"""

    return _resolve_unavailable_reason(descriptor, scope) is None


def _ensure_agent_available(descriptor: RegisteredAgentDescriptor, scope: AgentScopeContext) -> None:
    """校验读取类接口所需的基础智能体上下文。"""

    unavailable_reason = _resolve_base_unavailable_reason(descriptor, scope)
    if unavailable_reason:
        raise AppException(
            status_code=409,
            code="AI_AGENT_SCOPE_UNAVAILABLE",
            detail=unavailable_reason,
        )


def _ensure_agent_launch_available(descriptor: RegisteredAgentDescriptor, scope: AgentScopeContext) -> None:
    """在创建会话或启动运行前校验智能体启动上下文是否完整。"""

    unavailable_reason = _resolve_unavailable_reason(descriptor, scope)
    if unavailable_reason:
        raise AppException(
            status_code=409,
            code="AI_AGENT_SCOPE_UNAVAILABLE",
            detail=unavailable_reason,
        )


def _resolve_unavailable_reason(descriptor: RegisteredAgentDescriptor, scope: AgentScopeContext) -> str | None:
    """返回智能体不可用原因；可用时返回 None。"""

    base_reason = _resolve_base_unavailable_reason(descriptor, scope)
    if base_reason:
        return base_reason
    if descriptor.id == AGENT_COORDINATOR_AGENT_ID and scope.project_id is None:
        return CONTENT_AGENT_PROJECT_REQUIRED_REASON
    return None


def _resolve_base_unavailable_reason(descriptor: RegisteredAgentDescriptor, scope: AgentScopeContext) -> str | None:
    """返回读取类接口也必须满足的基础不可用原因。"""

    if descriptor.id in {AGENT_COORDINATOR_AGENT_ID, COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID} and scope.workspace_id is None:
        return "当前路由缺少 workspace_id，智能体不可用。"
    return None


def _resolve_required_llm_slots(registry: AgentRegistry, descriptor: RegisteredAgentDescriptor) -> tuple[str, ...]:
    """返回入口运行前必须绑定的模型槽位。"""

    slots = [descriptor.llm_slot] if descriptor.llm_slot else []
    if descriptor.id == AGENT_COORDINATOR_AGENT_ID:
        for member_agent_id in (COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID):
            member_descriptor = registry.get_descriptor(member_agent_id)
            if member_descriptor.llm_slot:
                slots.append(member_descriptor.llm_slot)
    return tuple(dict.fromkeys(slots))


def _get_agent_registry(request: Request) -> AgentRegistry:
    """从应用状态中读取已初始化的 Agent 注册表。"""

    registry = getattr(request.app.state, "ai_registry", None)
    if registry is None:
        raise RuntimeError("AI registry is not initialized.")
    return registry
