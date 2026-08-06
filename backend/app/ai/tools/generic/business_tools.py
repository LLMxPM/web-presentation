"""文件功能：构建内容助手固定通用工具，并把逻辑操作分派到现有业务服务与重资源工具。"""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import ApprovalRequired
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import extract_user_id
from app.ai.platform_tools import AgentToolContext, AgentToolResult, PlatformTool, agent_tool
from app.ai.tools.code_check import build_check_component_code_tool, build_check_page_code_tool
from app.ai.tools.component import build_component_manager_tools
from app.ai.tools.generic.archive import archive_entities, build_archive_confirmation, restore_entities
from app.ai.tools.generic.models import (
    BusinessOperation,
    BusinessResourceType,
    EntityArchiveArguments,
    build_mutation_envelope,
    build_query_envelope,
)
from app.ai.tools.page import build_apply_page_edits_tool, build_get_page_content_tool
from app.ai.tools.project import build_project_tools
from app.ai.tools.resource import build_resource_manager_tools
from app.ai.tools.shared import resolve_tool_context
from app.ai.tools.workspace.assets import build_list_workspace_font_assets_tool
from app.core.exceptions import AppException
from app.models.enums import RecordStatus
from app.models.workspace_style import WorkspaceStyle
from app.models.workspace_theme import WorkspaceTheme
from app.schemas.common import ListQuery
from app.schemas.page import PageCopyToProjectRequest, PageListQuery
from app.schemas.project import ProjectCreateRequest, ProjectUpdateRequest
from app.schemas.theme import ThemePalette, WorkspaceThemeCreateRequest, WorkspaceThemeUpdateRequest
from app.schemas.workspace_style import WorkspaceStyleCreateRequest, WorkspaceStyleUpdateRequest
from app.services.page_service import PageService
from app.services.project_service import ProjectService
from app.services.project_suggested_reference_asset_service import ProjectSuggestedReferenceAssetService
from app.services.suggested_component_service import SuggestedComponentService
from app.services.workspace_style_service import WorkspaceStyleService
from app.services.workspace_theme_service import WorkspaceThemeService
from app.services.agent_work_scope_service import project_is_in_work_scope


class ThemeCreatePayload(BaseModel):
    """限制内容助手创建主题时只能提交文本与色板字段。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    palette: ThemePalette


class ThemeUpdatePayload(BaseModel):
    """限制内容助手修改主题时不能接触 Logo 和字体字段。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    palette: ThemePalette | None = None


def build_generic_business_tools(session_factory: async_sessionmaker[AsyncSession]) -> list[Any]:
    """构建内容助手固定通用业务工具集合。"""

    internal_tools = _build_internal_tool_map(session_factory)

    @agent_tool(show_result=False)
    async def get_operation_guide(
        run_context: AgentToolContext,
        resource_type: BusinessResourceType,
        operation: BusinessOperation,
        action: str | None = None,
    ) -> dict[str, Any]:
        """读取对象操作手册、参数结构、限制和示例；该结果不是授权或执行前置条件。"""

        await resolve_tool_context(
            session_factory,
            run_context,
            required_scopes=(),
            required_dependency_fields=("workspace_id",),
        )
        from app.ai.tool_specs import get_operation_guide_spec

        guide = get_operation_guide_spec(resource_type, operation, action)
        if guide is None:
            raise AppException(
                status_code=404,
                code="AI_OPERATION_GUIDE_NOT_FOUND",
                detail="未找到对应操作手册；请检查 resource_type、operation 和 action。",
            )
        return guide.to_payload()

    @agent_tool(show_result=False)
    async def query_entities(
        run_context: AgentToolContext,
        resource_type: BusinessResourceType,
        action: str = "list",
        target_id: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """统一查询业务对象；具体 action 与 filters 请先参考操作手册。"""

        dependencies, claims = await resolve_tool_context(
            session_factory,
            run_context,
            required_scopes=(),
            required_dependency_fields=("workspace_id",),
        )
        data = await _query_entities(
            session_factory,
            internal_tools,
            run_context,
            dependencies=dependencies,
            claims=claims,
            resource_type=resource_type,
            action=action,
            target_id=target_id,
            filters=dict(filters or {}),
        )
        return build_query_envelope(resource_type=resource_type, action=action, data=data)

    @agent_tool(show_result=False, sequential=True)
    async def create_entity(
        run_context: AgentToolContext,
        resource_type: BusinessResourceType,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """统一创建业务对象；payload 的真实字段由操作手册说明并由后端 Schema 校验。"""

        result = await _create_entity(session_factory, internal_tools, run_context, resource_type, dict(payload))
        return _wrap_internal_mutation(resource_type, "create", result)

    @agent_tool(show_result=False, sequential=True)
    async def update_entity(
        run_context: AgentToolContext,
        resource_type: BusinessResourceType,
        target_id: int,
        payload: dict[str, Any],
        action: str = "metadata",
    ) -> dict[str, Any]:
        """统一修改业务对象；源码更新等复杂参数应按对应 action 的操作手册提交。"""

        result = await _update_entity(
            session_factory,
            internal_tools,
            run_context,
            resource_type,
            int(target_id),
            action,
            dict(payload),
        )
        return _wrap_internal_mutation(resource_type, "update", result, action=action, target_id=int(target_id))

    @agent_tool(show_result=False, sequential=True)
    async def archive_entity(
        run_context: AgentToolContext,
        resource_type: BusinessResourceType,
        target_ids: list[int],
        archive_reason: str | None = None,
        versions: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """归档一至一百个同类型对象；批量调用在真正写入前要求用户确认。"""

        arguments = EntityArchiveArguments(
            resource_type=resource_type,
            target_ids=target_ids,
            archive_reason=archive_reason,
            versions=versions or {},
        )
        approved = bool(run_context.dependencies.get("current_tool_call_approved"))
        needs_confirmation_check = len(arguments.target_ids) > 1 or (
            arguments.resource_type == "page" and run_context.dependencies.get("project_id") is not None
        )
        if not approved and needs_confirmation_check:
            confirmation = await build_archive_confirmation(session_factory, run_context, arguments)
            focus_project_id = run_context.dependencies.get("project_id")
            target_project_ids = {
                int(item["project_id"])
                for item in confirmation.get("targets", [])
                if item.get("project_id") is not None
            }
            cross_focus = focus_project_id is not None and any(
                item != int(focus_project_id) for item in target_project_ids
            )
            if len(arguments.target_ids) > 1 or cross_focus:
                title = (
                    f"确认批量归档 {len(arguments.target_ids)} 个对象吗？"
                    if len(arguments.target_ids) > 1
                    else "确认归档焦点外页面吗？"
                )
                raise ApprovalRequired(metadata={"confirmation_title": title, **confirmation})
        return await archive_entities(session_factory, run_context, arguments)

    @agent_tool(show_result=False, sequential=True)
    async def execute_action(
        run_context: AgentToolContext,
        resource_type: BusinessResourceType,
        action: str,
        target_id: int | None = None,
        target_ids: list[int] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行发布、复制、恢复、检查等普通动作。"""

        return await _execute_action(
            session_factory,
            internal_tools,
            run_context,
            resource_type=resource_type,
            action=action,
            target_id=target_id,
            target_ids=target_ids,
            payload=dict(payload or {}),
        )

    @agent_tool(show_result=False, requires_confirmation=True, sequential=True)
    async def execute_dangerous_action(
        run_context: AgentToolContext,
        resource_type: BusinessResourceType,
        action: str,
        target_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行路由整体覆盖、项目配置整体覆盖或主题 key 重命名等危险动作。"""

        return await _execute_dangerous_action(
            session_factory,
            internal_tools,
            run_context,
            resource_type=resource_type,
            action=action,
            target_id=target_id,
            payload=dict(payload or {}),
        )

    return [
        get_operation_guide,
        query_entities,
        create_entity,
        update_entity,
        archive_entity,
        execute_action,
        execute_dangerous_action,
    ]


def _build_internal_tool_map(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, PlatformTool]:
    """构建被通用工具复用的现有业务工具映射。"""

    tools = [
        *build_project_tools(session_factory),
        build_get_page_content_tool(session_factory),
        build_apply_page_edits_tool(session_factory),
        *build_component_manager_tools(session_factory),
        *build_resource_manager_tools(session_factory),
        build_check_page_code_tool(session_factory),
        build_check_component_code_tool(session_factory),
        build_list_workspace_font_assets_tool(session_factory),
    ]
    return {item.name: item for item in tools}


async def _query_entities(
    session_factory: async_sessionmaker[AsyncSession],
    tools: dict[str, PlatformTool],
    run_context: AgentToolContext,
    *,
    dependencies: dict[str, Any],
    claims: dict[str, Any],
    resource_type: str,
    action: str,
    target_id: int | None,
    filters: dict[str, Any],
) -> Any:
    """分派统一查询并对主题结果执行字段裁剪。"""

    workspace_id = int(dependencies["workspace_id"])
    user_id = extract_user_id(str(claims.get("sub")))
    if resource_type == "project":
        async with session_factory() as session:
            service = ProjectService(session)
            if action == "list":
                result = await service.list(_list_query(filters), workspace_id, user_id=user_id)
                data = result.model_dump(mode="json")
                return _filter_project_items(data, dependencies)
            if action == "detail" and target_id is not None:
                _ensure_project_in_work_scope(dependencies, target_id)
                item = await service.get(target_id, user_id=user_id)
                _ensure_workspace(item.workspace_id, workspace_id)
                return item.model_dump(mode="json")
        if action in {"pages", "route_tree", "style_config", "suggested_components", "suggested_assets"}:
            project_id = _required_target_id(target_id, "查询项目子资源时必须提供 target_id。")
            context = await _with_project_scope(session_factory, run_context, project_id)
            if action == "suggested_components":
                async with session_factory() as session:
                    items = await SuggestedComponentService(session).list_project_component_items(
                        project_id,
                        workspace_id=workspace_id,
                    )
                    return {"items": [item.model_dump(mode="json") for item in items], "total": len(items)}
            if action == "suggested_assets":
                async with session_factory() as session:
                    items = await ProjectSuggestedReferenceAssetService(session).list_asset_items(
                        project_id,
                        workspace_id=workspace_id,
                    )
                    return {"items": [item.model_dump(mode="json") for item in items], "total": len(items)}
            tool_name = {
                "pages": "list_project_pages",
                "route_tree": "get_project_route_tree",
                "style_config": "get_project_style_config",
            }[action]
            return await _call_internal(tools[tool_name], context, filters)
    if resource_type == "page":
        if action == "list":
            if filters.get("project_id") is not None:
                await _with_project_scope(session_factory, run_context, int(filters["project_id"]))
            async with session_factory() as session:
                result = await PageService(session).list(
                    PageListQuery(
                        page=int(filters.get("page", 1)),
                        page_size=min(int(filters.get("page_size", 50)), 100),
                        keyword=filters.get("keyword"),
                        status=RecordStatus(filters.get("status", RecordStatus.ACTIVE.value)),
                        workspace_id=workspace_id,
                        project_id=filters.get("project_id"),
                    ),
                    user_id=user_id,
                )
                return _filter_page_items(result.model_dump(mode="json"), dependencies)
        page_id = _required_target_id(target_id, "查询页面详情时必须提供 target_id。")
        if action == "detail":
            async with session_factory() as session:
                item = await PageService(session).get(page_id, user_id=user_id)
                _ensure_workspace(item.workspace_id, workspace_id)
                _ensure_project_in_work_scope(dependencies, item.project_id)
                return item.model_dump(mode="json", exclude={"page_content"})
        if action == "content":
            context = await _with_page_scope(session_factory, run_context, page_id)
            return await _call_internal(tools["get_page_content"], context, {"page_id": page_id})
    if resource_type == "theme":
        return await _query_themes(session_factory, workspace_id, action, target_id, filters)
    if resource_type == "style":
        return await _query_styles(session_factory, workspace_id, action, target_id, filters)

    tool_name = _query_tool_name(resource_type, action)
    if tool_name:
        payload = dict(filters)
        if target_id is not None:
            payload[_target_parameter(resource_type)] = target_id
        return await _call_internal(tools[tool_name], run_context, payload)
    raise AppException(status_code=400, code="AI_ENTITY_QUERY_UNSUPPORTED", detail="该对象不支持指定查询 action。")


async def _create_entity(
    session_factory: async_sessionmaker[AsyncSession],
    tools: dict[str, PlatformTool],
    run_context: AgentToolContext,
    resource_type: str,
    payload: dict[str, Any],
) -> Any:
    """分派创建操作并保证工作空间 ID 来自运行上下文。"""

    dependencies, claims = await resolve_tool_context(session_factory, run_context, required_scopes=(), required_dependency_fields=("workspace_id",))
    workspace_id = int(dependencies["workspace_id"])
    operator_id = extract_user_id(str(claims.get("sub")))
    if resource_type == "project":
        if str(dependencies.get("work_scope_mode") or "workspace") == "selected_projects":
            raise AppException(
                status_code=403,
                code="AI_PROJECT_CREATE_OUTSIDE_WORK_SCOPE",
                detail="显式项目工作集模式下不能创建尚未进入工作集的新项目；请先切换为全部项目。",
            )
        if "status" in payload and str(payload["status"]) != RecordStatus.ACTIVE.value:
            raise AppException(
                status_code=400,
                code="AI_PROJECT_STATUS_UNSUPPORTED",
                detail="内容助手创建项目时只能使用 active 状态，不开放项目归档。",
            )
        payload["status"] = RecordStatus.ACTIVE.value
        payload["workspace_id"] = workspace_id
        async with session_factory() as session:
            return (await ProjectService(session).create(ProjectCreateRequest.model_validate(payload), operator_id)).model_dump(mode="json")
    if resource_type == "theme":
        safe = ThemeCreatePayload.model_validate(payload)
        async with session_factory() as session:
            created = await WorkspaceThemeService(session).create(
                workspace_id,
                WorkspaceThemeCreateRequest.model_validate(safe.model_dump()),
                operator_id,
            )
            return _theme_payload(created)
    if resource_type == "style":
        async with session_factory() as session:
            created = await WorkspaceStyleService(session).create(
                workspace_id,
                WorkspaceStyleCreateRequest.model_validate(payload),
                operator_id,
            )
            return created.model_dump(mode="json")
    if resource_type == "page":
        project_id = int(payload.pop("project_id", 0) or 0)
        await _require_cross_focus_write_confirmation(session_factory, run_context, project_id, "创建页面")
        context = await _with_project_scope(session_factory, run_context, project_id)
        return await _call_internal(tools["create_project_page"], context, payload)
    tool_name = {"component": "create_component", "asset": "create_resource_asset"}.get(resource_type)
    if tool_name:
        return await _call_internal(tools[tool_name], run_context, payload)
    raise AppException(status_code=400, code="AI_ENTITY_CREATE_UNSUPPORTED", detail="该对象类型不支持创建。")


async def _update_entity(
    session_factory: async_sessionmaker[AsyncSession],
    tools: dict[str, PlatformTool],
    run_context: AgentToolContext,
    resource_type: str,
    target_id: int,
    action: str,
    payload: dict[str, Any],
) -> Any:
    """分派更新操作，主题普通更新明确排除 key、Logo 和字体。"""

    dependencies, claims = await resolve_tool_context(session_factory, run_context, required_scopes=(), required_dependency_fields=("workspace_id",))
    workspace_id = int(dependencies["workspace_id"])
    operator_id = extract_user_id(str(claims.get("sub")))
    if resource_type == "project":
        for forbidden in ("workspace_id", "status", "theme_config_yaml"):
            if forbidden in payload:
                raise AppException(status_code=400, code="AI_PROJECT_FIELD_UNSUPPORTED", detail=f"update_entity 不允许修改项目字段：{forbidden}。")
        async with session_factory() as session:
            current = await ProjectService(session).get(target_id, user_id=operator_id)
            _ensure_workspace(current.workspace_id, workspace_id)
            _ensure_project_in_work_scope(dependencies, target_id)
            await _raise_cross_focus_confirmation(run_context, claims, target_id, "修改项目")
            return (await ProjectService(session).update(target_id, ProjectUpdateRequest.model_validate(payload), operator_id)).model_dump(mode="json")
    if resource_type == "theme":
        safe = ThemeUpdatePayload.model_validate(payload)
        async with session_factory() as session:
            updated = await WorkspaceThemeService(session).update(
                workspace_id,
                target_id,
                WorkspaceThemeUpdateRequest.model_validate(safe.model_dump(exclude_unset=True)),
                operator_id,
            )
            return _theme_payload(updated)
    if resource_type == "style":
        async with session_factory() as session:
            updated = await WorkspaceStyleService(session).update(
                workspace_id,
                target_id,
                WorkspaceStyleUpdateRequest.model_validate(payload),
                operator_id,
            )
            return updated.model_dump(mode="json")
    if resource_type == "page":
        await _require_page_write_confirmation(session_factory, run_context, target_id, "修改页面")
        context = await _with_page_scope(session_factory, run_context, target_id)
        tool_name = "apply_page_edits" if action == "content" else "update_page_metadata"
        payload["page_id"] = target_id
        return await _call_internal(tools[tool_name], context, payload)
    if resource_type == "component":
        tool_name = "apply_component_edits" if action == "content" else "update_component_metadata"
        payload["component_id"] = target_id
        return await _call_internal(tools[tool_name], run_context, payload)
    if resource_type == "asset":
        tool_name = "apply_resource_content_diff" if action == "content" else "update_resource_asset_metadata"
        payload["asset_id"] = target_id
        return await _call_internal(tools[tool_name], run_context, payload)
    raise AppException(status_code=400, code="AI_ENTITY_UPDATE_UNSUPPORTED", detail="该对象类型不支持更新。")


async def _execute_action(
    session_factory: async_sessionmaker[AsyncSession],
    tools: dict[str, PlatformTool],
    run_context: AgentToolContext,
    *,
    resource_type: str,
    action: str,
    target_id: int | None,
    target_ids: list[int] | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """执行普通动作，并统一包装既有工具结果。"""

    if action == "restore":
        ids = target_ids or ([] if target_id is None else [target_id])
        return await restore_entities(session_factory, run_context, resource_type=resource_type, target_ids=ids, reason=payload.get("reason"))
    tool_name = {
        ("component", "publish"): "publish_component",
        ("component", "check"): "check_component_code",
        ("page", "check"): "check_page_code",
        ("asset", "copy"): "copy_resource_asset",
        ("asset", "preview_content"): "preview_resource_content_diff",
        ("asset", "save_upload"): "save_uploaded_image_as_resource",
    }.get((resource_type, action))
    if resource_type == "page" and action == "copy":
        page_id = _required_target_id(target_id, "复制页面时必须提供 target_id。")
        await _with_page_scope(session_factory, run_context, page_id)
        destination_project_id = int(payload.get("project_id") or 0)
        await _require_cross_focus_write_confirmation(session_factory, run_context, destination_project_id, "复制页面")
        dependencies, claims = await resolve_tool_context(
            session_factory,
            run_context,
            required_scopes=(),
            required_dependency_fields=("workspace_id",),
        )
        operator_id = extract_user_id(str(claims.get("sub")))
        async with session_factory() as session:
            copied = await PageService(session).copy_to_project(
                page_id,
                PageCopyToProjectRequest.model_validate(payload),
                operator_id,
            )
            _ensure_workspace(copied.workspace_id, int(dependencies["workspace_id"]))
            result = copied.model_dump(mode="json")
        return _wrap_internal_mutation("page", "action", result, action=action, target_id=copied.id)
    if resource_type in {"theme", "style"} and action == "copy":
        result = await _copy_theme_or_style(session_factory, run_context, resource_type, _required_target_id(target_id, "复制时必须提供 target_id。"), payload)
        return _wrap_internal_mutation(resource_type, "action", result, action=action, target_id=target_id)
    if not tool_name:
        raise AppException(status_code=400, code="AI_ACTION_UNSUPPORTED", detail="该普通动作未开放。")
    arguments = dict(payload)
    context = run_context
    if target_id is not None:
        arguments[_target_parameter(resource_type)] = target_id
        if resource_type == "page":
            context = await _with_page_scope(session_factory, run_context, target_id)
    result = await _call_internal(tools[tool_name], context, arguments)
    return _wrap_internal_mutation(resource_type, "action", result, action=action, target_id=target_id)


async def _execute_dangerous_action(
    session_factory: async_sessionmaker[AsyncSession],
    tools: dict[str, PlatformTool],
    run_context: AgentToolContext,
    *,
    resource_type: str,
    action: str,
    target_id: int | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """只分派显式登记的危险动作，禁止用 action 绕过删除边界。"""

    if resource_type == "project" and action in {"replace_routes", "replace_style_config"}:
        project_id = _required_target_id(target_id, "危险项目操作必须提供 target_id。")
        context = await _with_project_scope(session_factory, run_context, project_id)
        tool_name = "update_project_route_tree" if action == "replace_routes" else "update_project_style_config"
        result = await _call_internal(tools[tool_name], context, payload)
        return _wrap_internal_mutation("project", "action", result, action=action, target_id=project_id)
    if resource_type == "theme" and action == "rename_key":
        dependencies, claims = await resolve_tool_context(session_factory, run_context, required_scopes=(), required_dependency_fields=("workspace_id",))
        theme_id = _required_target_id(target_id, "主题 key 重命名必须提供 target_id。")
        next_key = str(payload.get("key") or "").strip()
        operator_id = extract_user_id(str(claims.get("sub")))
        async with session_factory() as session:
            updated = await WorkspaceThemeService(session).update(
                int(dependencies["workspace_id"]),
                theme_id,
                WorkspaceThemeUpdateRequest(key=next_key),
                operator_id,
            )
            result = _theme_payload(updated)
        return _wrap_internal_mutation("theme", "action", result, action=action, target_id=theme_id)
    raise AppException(status_code=400, code="AI_DANGEROUS_ACTION_UNSUPPORTED", detail="该危险动作未开放；删除和清理动作永不开放。")


async def _call_internal(tool: PlatformTool, run_context: AgentToolContext, arguments: dict[str, Any]) -> Any:
    """按既有工具签名过滤参数后执行内部处理器。"""

    signature = inspect.signature(tool.entrypoint)
    allowed = {name for name in signature.parameters if name != next(iter(signature.parameters), None)}
    unknown = sorted(set(arguments) - allowed)
    if unknown:
        raise AppException(
            status_code=422,
            code="AI_OPERATION_ARGUMENTS_INVALID",
            detail=f"存在当前操作不支持的参数：{', '.join(unknown)}。请查询操作手册后重试。",
        )
    missing = [
        name
        for name, parameter in list(signature.parameters.items())[1:]
        if parameter.default is inspect.Signature.empty and name not in arguments
    ]
    if missing:
        raise AppException(
            status_code=422,
            code="AI_OPERATION_ARGUMENTS_REQUIRED",
            detail=f"缺少必要参数：{', '.join(missing)}。请查询操作手册后重试。",
        )
    result = tool.entrypoint(run_context, **arguments)
    if inspect.isawaitable(result):
        result = await result
    return _normalize_internal_result(result)


def _normalize_internal_result(result: Any) -> Any:
    """把内部工具多媒体容器转换为可嵌套的普通数据。"""

    if isinstance(result, AgentToolResult):
        return {
            "content": result.content,
            "images": result.images or [],
            "videos": result.videos or [],
            "audios": result.audios or [],
            "files": result.files or [],
        }
    return result


async def _with_project_scope(
    session_factory: async_sessionmaker[AsyncSession],
    run_context: AgentToolContext,
    project_id: int,
) -> AgentToolContext:
    """校验项目属于当前工作空间，再为内部旧工具注入可信项目范围。"""

    if project_id <= 0:
        raise AppException(status_code=400, code="PROJECT_ID_REQUIRED", detail="project_id 必须为正整数。")
    dependencies, claims = await resolve_tool_context(session_factory, run_context, required_scopes=(), required_dependency_fields=("workspace_id",))
    _ensure_project_in_work_scope(dependencies, project_id)
    user_id = extract_user_id(str(claims.get("sub")))
    async with session_factory() as session:
        project = await ProjectService(session).get(project_id, user_id=user_id)
        _ensure_workspace(project.workspace_id, int(dependencies["workspace_id"]))
    return _trusted_scope_context(run_context, project_id=project_id)


async def _with_page_scope(
    session_factory: async_sessionmaker[AsyncSession],
    run_context: AgentToolContext,
    page_id: int,
) -> AgentToolContext:
    """校验页面属于当前工作空间，再为内部旧工具注入可信页面和项目范围。"""

    dependencies, claims = await resolve_tool_context(session_factory, run_context, required_scopes=(), required_dependency_fields=("workspace_id",))
    user_id = extract_user_id(str(claims.get("sub")))
    async with session_factory() as session:
        page = await PageService(session).get(page_id, user_id=user_id)
        _ensure_workspace(page.workspace_id, int(dependencies["workspace_id"]))
        _ensure_project_in_work_scope(dependencies, page.project_id)
    return _trusted_scope_context(run_context, page_id=page_id, project_id=page.project_id)


def _ensure_project_in_work_scope(dependencies: dict[str, Any], project_id: int | None) -> None:
    """在查询和写入前统一执行 Run 项目工作集限制。"""

    if not project_is_in_work_scope(
        work_scope_mode=str(dependencies.get("work_scope_mode") or "workspace"),
        allowed_project_ids=list(dependencies.get("allowed_project_ids") or []),
        project_id=project_id,
    ):
        raise AppException(status_code=403, code="AI_PROJECT_OUTSIDE_WORK_SCOPE", detail="目标项目不在本轮固化的项目工作集中。")


def _filter_project_items(data: dict[str, Any], dependencies: dict[str, Any]) -> dict[str, Any]:
    """过滤项目列表，避免仅在详情和写入路径执行工作集限制。"""

    if str(dependencies.get("work_scope_mode") or "workspace") == "workspace":
        return data
    allowed = {int(item) for item in dependencies.get("allowed_project_ids") or []}
    items = [item for item in data.get("items", []) if int(item.get("id") or 0) in allowed]
    return {**data, "items": items, "total": len(items)}


def _filter_page_items(data: dict[str, Any], dependencies: dict[str, Any]) -> dict[str, Any]:
    """按页面所属项目过滤列表，空 selected_projects 返回空集合。"""

    if str(dependencies.get("work_scope_mode") or "workspace") == "workspace":
        return data
    allowed = {int(item) for item in dependencies.get("allowed_project_ids") or []}
    items = [item for item in data.get("items", []) if int(item.get("project_id") or 0) in allowed]
    return {**data, "items": items, "total": len(items)}


async def _require_page_write_confirmation(
    session_factory: async_sessionmaker[AsyncSession],
    run_context: AgentToolContext,
    page_id: int,
    action_label: str,
) -> None:
    """读取页面所属项目，并按焦点差异请求本次工具调用确认。"""

    dependencies, claims = await resolve_tool_context(session_factory, run_context, required_scopes=(), required_dependency_fields=("workspace_id",))
    user_id = extract_user_id(str(claims.get("sub")))
    async with session_factory() as session:
        page = await PageService(session).get(page_id, user_id=user_id)
        _ensure_workspace(page.workspace_id, int(dependencies["workspace_id"]))
    _ensure_project_in_work_scope(dependencies, page.project_id)
    await _raise_cross_focus_confirmation(run_context, claims, page.project_id, action_label)


async def _require_cross_focus_write_confirmation(
    session_factory: async_sessionmaker[AsyncSession],
    run_context: AgentToolContext,
    project_id: int,
    action_label: str,
) -> None:
    """校验显式项目目标并为焦点外写入生成动态确认。"""

    context = await _with_project_scope(session_factory, run_context, project_id)
    _, claims = await resolve_tool_context(session_factory, context, required_scopes=(), required_dependency_fields=("workspace_id",))
    await _raise_cross_focus_confirmation(run_context, claims, project_id, action_label)


async def _raise_cross_focus_confirmation(
    run_context: AgentToolContext,
    claims: dict[str, Any],
    target_project_id: int | None,
    action_label: str,
) -> None:
    """焦点项目与目标项目不同时逐次暂停，批准后恢复同一次工具调用。"""

    focus_project_id = claims.get("project_id")
    approved = bool(run_context.dependencies.get("current_tool_call_approved"))
    if focus_project_id is None or target_project_id is None or int(focus_project_id) == int(target_project_id) or approved:
        return
    raise ApprovalRequired(
        metadata={
            "confirmation_title": f"确认在焦点外{action_label}吗？",
            "current_focus": {"project_id": int(focus_project_id)},
            "target": {"project_id": int(target_project_id)},
            "impact": "本次写入目标不属于当前 Run 的默认项目焦点；批准仅对本次工具调用有效。",
        }
    )


def _trusted_scope_context(
    run_context: AgentToolContext,
    *,
    project_id: int | None = None,
    page_id: int | None = None,
) -> AgentToolContext:
    """复制运行上下文并标记已由通用分派层校验的范围覆盖。"""

    dependencies = {
        **run_context.dependencies,
        "trusted_scope_override": True,
        "project_id": project_id,
        "page_id": page_id,
    }
    return AgentToolContext(
        run_id=run_context.run_id,
        session_id=run_context.session_id,
        user_id=run_context.user_id,
        dependencies=dependencies,
    )


async def _query_themes(
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: int,
    action: str,
    target_id: int | None,
    filters: dict[str, Any],
) -> Any:
    """查询主题文本字段与色板，不向模型暴露 Logo 或字体配置。"""

    async with session_factory() as session:
        if filters.get("include_archived") and action in {"list", "detail"}:
            rows = list((await session.scalars(select(WorkspaceTheme).where(WorkspaceTheme.workspace_id == workspace_id))).all())
            if action == "detail":
                resolved_id = _required_target_id(target_id, "主题详情必须提供 target_id。")
                matched = next((item for item in rows if int(item.id) == resolved_id), None)
                if matched is None:
                    raise AppException(status_code=404, code="WORKSPACE_THEME_NOT_FOUND", detail="主题不存在。")
                return _theme_model_payload(matched)
            return {"total": len(rows), "items": [_theme_model_payload(item) for item in rows]}
        service = WorkspaceThemeService(session)
        if action == "list":
            result = await service.list(workspace_id, _list_query(filters))
            return {"total": result.total, "items": [_theme_payload(item) for item in result.items]}
        if action == "detail":
            return _theme_payload(await service.get(workspace_id, _required_target_id(target_id, "主题详情必须提供 target_id。")))
    raise AppException(status_code=400, code="AI_ENTITY_QUERY_UNSUPPORTED", detail="主题不支持该查询 action。")


async def _query_styles(
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: int,
    action: str,
    target_id: int | None,
    filters: dict[str, Any],
) -> Any:
    """查询工作空间样式，允许显式查看已归档记录。"""

    async with session_factory() as session:
        if filters.get("include_archived") and action in {"list", "detail"}:
            rows = list((await session.scalars(select(WorkspaceStyle).where(WorkspaceStyle.workspace_id == workspace_id))).all())
            if action == "detail":
                resolved_id = _required_target_id(target_id, "样式详情必须提供 target_id。")
                matched = next((item for item in rows if int(item.id) == resolved_id), None)
                if matched is None:
                    raise AppException(status_code=404, code="WORKSPACE_STYLE_NOT_FOUND", detail="样式不存在。")
                return _style_model_payload(matched)
            return {"total": len(rows), "items": [_style_model_payload(item) for item in rows]}
        service = WorkspaceStyleService(session)
        if action == "list":
            return (await service.list(workspace_id, _list_query(filters))).model_dump(mode="json")
        if action == "detail":
            return (await service.get(workspace_id, _required_target_id(target_id, "样式详情必须提供 target_id。"))).model_dump(mode="json")
    raise AppException(status_code=400, code="AI_ENTITY_QUERY_UNSUPPORTED", detail="样式不支持该查询 action。")


async def _copy_theme_or_style(
    session_factory: async_sessionmaker[AsyncSession],
    run_context: AgentToolContext,
    resource_type: str,
    target_id: int,
    payload: dict[str, Any],
) -> Any:
    """调用主题或样式现有复制服务。"""

    from app.schemas.theme import WorkspaceThemeCopyRequest
    from app.schemas.workspace_style import WorkspaceStyleCopyRequest

    dependencies, claims = await resolve_tool_context(session_factory, run_context, required_scopes=(), required_dependency_fields=("workspace_id",))
    workspace_id = int(dependencies["workspace_id"])
    operator_id = extract_user_id(str(claims.get("sub")))
    async with session_factory() as session:
        if resource_type == "theme":
            copied = await WorkspaceThemeService(session).copy(workspace_id, target_id, WorkspaceThemeCopyRequest.model_validate(payload), operator_id)
            return _theme_payload(copied)
        copied = await WorkspaceStyleService(session).copy(workspace_id, target_id, WorkspaceStyleCopyRequest.model_validate(payload), operator_id)
        return copied.model_dump(mode="json")


def _query_tool_name(resource_type: str, action: str) -> str | None:
    """返回由既有工具处理的逻辑查询映射。"""

    return {
        ("component", "list"): "list_components",
        ("component", "detail"): "get_component_detail",
        ("component", "versions"): "list_component_versions",
        ("component", "dependencies"): "get_component_dependencies",
        ("asset", "list"): "list_resource_assets",
        ("asset", "content"): "get_resource_asset_content",
        ("asset", "tags"): "list_resource_tags",
        ("runtime_kit", "list"): "list_runtime_kit_capabilities",
        ("runtime_kit", "detail"): "get_runtime_kit_capability",
        ("font", "list"): "list_workspace_font_assets",
    }.get((resource_type, action))


def _target_parameter(resource_type: str) -> str:
    """返回既有工具使用的目标 ID 参数名。"""

    return {"component": "component_id", "asset": "asset_id", "page": "page_id"}.get(resource_type, "target_id")


def _wrap_internal_mutation(
    resource_type: str,
    operation: str,
    result: Any,
    *,
    action: str | None = None,
    target_id: int | None = None,
) -> dict[str, Any]:
    """把内部工具结果包装为统一 mutation envelope。"""

    if isinstance(result, dict) and result.get("success") is False:
        return result
    target = None if target_id is None else {"id": target_id, "resource_type": resource_type}
    return build_mutation_envelope(
        resource_type=resource_type,
        operation=operation,
        action=action,
        message=_result_message(result, f"{resource_type} 操作已完成。"),
        target=target,
        mutation_kind={"page": "project-pages", "asset": "asset"}.get(resource_type, resource_type),
        data=result,
    )


def _result_message(result: Any, fallback: str) -> str:
    """优先复用业务处理器返回的用户可读消息。"""

    if isinstance(result, dict) and isinstance(result.get("message"), str):
        return result["message"]
    return fallback


def _list_query(filters: dict[str, Any]) -> ListQuery:
    """从通用筛选参数构造受限分页查询。"""

    return ListQuery(
        page=max(1, int(filters.get("page", 1))),
        page_size=max(1, min(int(filters.get("page_size", 50)), 100)),
        keyword=str(filters.get("keyword") or "").strip() or None,
        status=RecordStatus(str(filters["status"])) if filters.get("status") else None,
        sort_by=str(filters.get("sort_by") or "updated_at"),
        sort_order=str(filters.get("sort_order") or "desc"),
    )


def _theme_payload(item: Any) -> dict[str, Any]:
    """裁剪主题响应，确保不暴露 Logo 和字体字段。"""

    palette = item.palette.model_dump(mode="json") if hasattr(item.palette, "model_dump") else dict(item.palette)
    return {
        "id": item.id,
        "workspace_id": item.workspace_id,
        "key": item.key,
        "name": item.name,
        "description": item.description,
        "palette": palette,
        "created_at": item.created_at.isoformat() if hasattr(item.created_at, "isoformat") else item.created_at,
        "updated_at": item.updated_at.isoformat() if hasattr(item.updated_at, "isoformat") else item.updated_at,
        "archived": False,
    }


def _theme_model_payload(item: WorkspaceTheme) -> dict[str, Any]:
    """裁剪 ORM 主题记录并补充归档状态。"""

    payload = _theme_payload(item)
    payload["archived"] = item.deleted_at is not None
    return payload


def _style_model_payload(item: WorkspaceStyle) -> dict[str, Any]:
    """把样式 ORM 记录转换为不含内部关系的操作手册结果。"""

    return {
        "id": item.id,
        "workspace_id": item.workspace_id,
        "key": item.key,
        "name": item.name,
        "description": item.description,
        "page_width": item.page_width,
        "page_height": item.page_height,
        "base_font_size": item.base_font_size,
        "icon_default_stroke_width": item.icon_default_stroke_width,
        "show_pdf_export_button": item.show_pdf_export_button,
        "menu_mode": item.menu_mode,
        "theme_key": item.theme_key,
        "style_spec_markdown": item.style_spec_markdown,
        "archived": item.deleted_at is not None,
    }


def _required_target_id(target_id: int | None, message: str) -> int:
    """校验通用工具需要的单目标主键。"""

    if target_id is None or int(target_id) <= 0:
        raise AppException(status_code=400, code="AI_ENTITY_TARGET_REQUIRED", detail=message)
    return int(target_id)


def _ensure_workspace(actual_workspace_id: int | None, expected_workspace_id: int) -> None:
    """拒绝通用工具跨工作空间访问对象。"""

    if actual_workspace_id != expected_workspace_id:
        raise AppException(status_code=403, code="AI_ENTITY_SCOPE_DENIED", detail="目标对象不属于当前工作空间。")
