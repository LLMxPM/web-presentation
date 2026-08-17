"""文件功能：构建内容助手固定通用工具，并把逻辑操作分派到现有业务服务与重资源工具。"""

from __future__ import annotations

import inspect
from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError
from pydantic_ai import ApprovalRequired
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import extract_user_id
from app.ai.platform_tools import AgentToolContext, AgentToolResult, PlatformTool, agent_tool
from app.ai.tools.code_check import build_check_component_code_tool, build_check_page_code_tool
from app.ai.tools.component import build_component_manager_tools
from app.ai.tools.generic.archive import archive_entities, build_archive_confirmation
from app.ai.tools.generic.models import (
    BusinessResourceType,
    EntityArchiveArguments,
    build_mutation_envelope,
    build_query_envelope,
    build_validation_envelope,
)
from app.ai.tools.generic.operation_models import (
    ThemeCreatePayload,
    ThemeUpdatePayload,
    get_operation_payload_model,
    get_query_filters_model,
)
from app.ai.tools.page import build_apply_page_edits_tool, build_get_page_content_tool
from app.ai.tools.project import build_project_tools
from app.ai.tools.resource import build_resource_manager_tools
from app.ai.tools.shared import resolve_tool_context
from app.ai.tools.workspace.assets import build_list_workspace_font_assets_tool
from app.core.exceptions import AppException
from app.models.enums import AssetType, RecordStatus
from app.schemas.common import ListQuery
from app.schemas.page import PageCopyToProjectRequest, PageListQuery
from app.schemas.project import ProjectCreateRequest, ProjectUpdateRequest
from app.schemas.presentation_style import ProjectPatchConfiguration, ProjectStyleConfiguration
from app.schemas.theme import WorkspaceThemeCreateRequest, WorkspaceThemeUpdateRequest
from app.schemas.workspace_style import WorkspaceStyleCreateRequest, WorkspaceStyleUpdateRequest
from app.services.page_service import PageService
from app.services.asset_service import AssetService
from app.services.project_service import ProjectService
from app.services.suggested_component_service import SuggestedComponentService
from app.services.workspace_style_service import WorkspaceStyleService
from app.services.workspace_component_service import WorkspaceComponentService
from app.services.workspace_theme_service import WorkspaceThemeService
from app.services.agent_work_scope_service import project_is_in_work_scope

AI_PAGE_QUERY_EXCLUDED_FIELDS = {
    "page_content",
    "created_by",
    "updated_by",
    "screenshot_url",
    "screenshot_version_no",
    "screenshot_config_hash",
    "screenshot_viewport_width",
    "screenshot_viewport_height",
    "screenshot_is_latest",
    "screenshot_updated_at",
}
AI_PROJECT_QUERY_EXCLUDED_FIELDS = {"first_page_screenshot_url"}


def build_generic_business_tools(session_factory: async_sessionmaker[AsyncSession]) -> list[Any]:
    """构建内容助手固定通用业务工具集合。"""

    internal_tools = _build_internal_tool_map(session_factory)

    @agent_tool(show_result=False)
    async def get_operation_guide(
        run_context: AgentToolContext,
        operation_key: Annotated[str | None, Field(description="稳定操作键；不传时返回全部操作的紧凑索引。")] = None,
    ) -> dict[str, Any]:
        """读取对象操作手册、参数结构、限制和示例。"""

        await resolve_tool_context(
            session_factory,
            run_context,
            required_scopes=(),
            required_dependency_fields=("workspace_id",),
        )
        from app.ai.tool_specs import get_operation_guide_spec, list_operation_guide_options

        normalized_key = str(operation_key or "").strip()
        if not normalized_key:
            return {
                "operations": list_operation_guide_options(),
                "note": "请选择 operation_key 再次查询，以取得精确参数 Schema。",
            }
        guide = get_operation_guide_spec(normalized_key)
        if guide is None:
            raise AppException(
                status_code=404,
                code="AI_OPERATION_GUIDE_NOT_FOUND",
                detail="未找到对应操作手册；请从索引中选择有效 operation_key。",
            )
        return guide.to_payload()

    @agent_tool(show_result=False)
    async def get_code_standards(
        run_context: AgentToolContext,
        standard_type: Annotated[Literal["page", "component"], Field(description="要查询的代码规范类型。页面源码使用 page，组件源码使用 component。")],
    ) -> dict[str, Any]:
        """读取当前用户页面或组件的有效代码规范 Markdown。"""

        _, claims = await resolve_tool_context(
            session_factory,
            run_context,
            required_scopes=(),
            required_dependency_fields=("workspace_id",),
        )
        from app.ai.tool_specs import AGENT_COORDINATOR_AGENT_ID
        from app.services.ai_agent_config_service import AiAgentConfigService

        user_id = extract_user_id(str(claims.get("sub")))
        async with session_factory() as session:
            configs = await AiAgentConfigService(session, user_id=user_id).list_code_standard_configs(
                AGENT_COORDINATOR_AGENT_ID
            )
        config = next(item for item in configs if item.standard_type == standard_type)
        return {
            "agent_id": config.agent_id,
            "standard_type": config.standard_type,
            "source": config.source,
            "customized": config.customized,
            "content": config.content,
        }

    @agent_tool(show_result=False)
    async def list_entities(
        run_context: AgentToolContext,
        resource_type: Annotated[BusinessResourceType, Field(description="要罗列或搜索的业务对象类型。")],
        filters: Annotated[dict[str, Any] | None, Field(description="当前 resource_type 的列表筛选参数，必须符合操作手册中的精确 Schema。")] = None,
        collection: Annotated[Literal["items", "tags"], Field(description="集合类型；通常使用 items，仅 asset 支持 tags。")] = "items",
    ) -> dict[str, Any]:
        """统一罗列、搜索业务对象；不读取单项详情或源码。"""

        dependencies, claims = await resolve_tool_context(
            session_factory,
            run_context,
            required_scopes=(),
            required_dependency_fields=("workspace_id",),
        )
        action = "tags" if resource_type == "asset" and collection == "tags" else "list"
        if collection == "tags" and resource_type != "asset":
            raise AppException(status_code=400, code="AI_ENTITY_COLLECTION_UNSUPPORTED", detail="只有 asset 支持 tags 集合。")
        data = await _dispatch_entity_query(
            session_factory,
            internal_tools,
            run_context,
            dependencies=dependencies,
            claims=claims,
            resource_type=resource_type,
            action=action,
            target_id=None,
            filters=dict(filters or {}),
        )
        return build_query_envelope(resource_type=resource_type, action=action, data=data)

    @agent_tool(show_result=False)
    async def get_entity(
        run_context: AgentToolContext,
        resource_type: Annotated[Literal["project", "page", "component", "asset", "theme", "style", "runtime_kit"], Field(description="要读取的单项对象类型。")],
        view: Annotated[Literal["detail", "content", "configuration", "route_tree", "versions", "version_content", "dependencies"], Field(description="单项读取视图，必须与 resource_type 匹配。")],
        target_id: Annotated[int | None, Field(gt=0, description="项目、页面、组件、资源、主题或样式 ID；Runtime Kit detail 不使用。")] = None,
        lookup: Annotated[dict[str, Any] | None, Field(description="非 ID 定位参数；目前仅 Runtime Kit detail 使用 name 和可选 kind。")] = None,
        options: Annotated[dict[str, Any] | None, Field(description="视图选项；例如 version_content 的 version_no。")] = None,
    ) -> dict[str, Any]:
        """统一读取单个对象的详情、源码或结构化视图。"""

        dependencies, claims = await resolve_tool_context(
            session_factory,
            run_context,
            required_scopes=(),
            required_dependency_fields=("workspace_id",),
        )
        query_options = dict(options or {})
        if resource_type == "runtime_kit":
            query_options.update(dict(lookup or {}))
        elif lookup:
            raise AppException(status_code=400, code="AI_ENTITY_LOOKUP_UNSUPPORTED", detail="当前对象只支持使用 target_id 定位。")
        data = await _dispatch_entity_query(
            session_factory,
            internal_tools,
            run_context,
            dependencies=dependencies,
            claims=claims,
            resource_type=resource_type,
            action=view,
            target_id=target_id,
            filters=query_options,
        )
        message = _build_detail_query_message(resource_type, target_id, data) if view == "detail" else "查询完成。"
        return build_query_envelope(resource_type=resource_type, action=view, data=data, message=message)

    @agent_tool(show_result=False, sequential=True)
    async def create_entity(
        run_context: AgentToolContext,
        resource_type: Annotated[Literal["project", "page", "component", "asset", "theme", "style"], Field(description="要创建的业务对象类型。")],
        mode: Annotated[Literal["new", "copy", "upload"], Field(description="创建来源模式；必须与 resource_type 匹配。")],
        payload: Annotated[dict[str, Any], Field(description="创建参数；字段必须严格符合对应操作手册。")],
    ) -> dict[str, Any]:
        """统一创建业务对象；payload 的真实字段由操作手册说明并由后端 Schema 校验。"""

        return await _create_entity(session_factory, internal_tools, run_context, resource_type, mode, dict(payload))

    @agent_tool(show_result=False, sequential=True)
    async def update_entity(
        run_context: AgentToolContext,
        resource_type: Annotated[Literal["project", "page", "component", "asset", "theme", "style"], Field(description="要修改的业务对象类型。")],
        target_id: Annotated[int, Field(gt=0, description="真实查询得到的目标对象 ID。")],
        payload: Annotated[dict[str, Any], Field(description="修改参数；只提交需要修改的字段，并严格符合操作手册。")],
        action: Annotated[Literal["metadata", "content", "configuration", "apply_style", "route_tree", "build_assets"], Field(description="修改动作；必须与 resource_type 组成操作手册支持的组合。")] = "metadata",
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
        resource_type: Literal["project", "page", "component", "asset", "theme", "style"],
        target_ids: list[int],
        archive_reason: str | None = None,
    ) -> dict[str, Any]:
        """归档一至一百个同类型对象；批量调用在真正写入前要求用户确认。"""

        arguments = EntityArchiveArguments(
            resource_type=resource_type,
            target_ids=target_ids,
            archive_reason=archive_reason,
        )
        approved = bool(run_context.dependencies.get("current_tool_call_approved"))
        needs_confirmation_check = len(arguments.target_ids) > 1 or (
            arguments.resource_type in {"project", "page"}
            and run_context.dependencies.get("project_id") is not None
        )
        if not approved and needs_confirmation_check:
            confirmation = await build_archive_confirmation(session_factory, run_context, arguments)
            focus_project_id = run_context.dependencies.get("project_id")
            target_project_ids = (
                {int(item["id"]) for item in confirmation.get("targets", [])}
                if arguments.resource_type == "project"
                else {
                    int(item["project_id"])
                    for item in confirmation.get("targets", [])
                    if item.get("project_id") is not None
                }
            )
            cross_focus = focus_project_id is not None and any(
                item != int(focus_project_id) for item in target_project_ids
            )
            if len(arguments.target_ids) > 1 or cross_focus:
                title = (
                    f"确认批量归档 {len(arguments.target_ids)} 个对象吗？"
                    if len(arguments.target_ids) > 1
                    else "确认归档焦点外项目或页面吗？"
                )
                raise ApprovalRequired(metadata={"confirmation_title": title, **confirmation})
        return await archive_entities(session_factory, run_context, arguments)

    @agent_tool(show_result=False, sequential=True)
    async def execute_action(
        run_context: AgentToolContext,
        resource_type: Annotated[Literal["component"], Field(description="生命周期命令所属对象类型。")],
        action: Annotated[Literal["publish"], Field(description="已登记的生命周期 action。")],
        target_id: Annotated[int, Field(gt=0, description="要执行生命周期命令的目标 ID。")],
        payload: Annotated[dict[str, Any] | None, Field(description="action 专属参数；必须严格符合操作手册。")] = None,
    ) -> dict[str, Any]:
        """执行改变已有对象业务状态、且不属于字段更新的生命周期命令。"""

        return await _execute_action(
            session_factory,
            internal_tools,
            run_context,
            resource_type=resource_type,
            action=action,
            target_id=target_id,
            payload=dict(payload or {}),
        )

    @agent_tool(show_result=False)
    async def validate_entity(
        run_context: AgentToolContext,
        resource_type: Annotated[Literal["page", "component", "asset"], Field(description="要校验的业务对象类型。")],
        action: Annotated[Literal["check", "preview"], Field(description="只读校验动作；必须与 resource_type 匹配。")],
        target_id: Annotated[int | None, Field(gt=0, description="current、edits 和资源预览使用的目标 ID。")] = None,
        payload: Annotated[dict[str, Any] | None, Field(description="候选来源或预览参数；必须符合精确操作手册。")] = None,
    ) -> dict[str, Any]:
        """检查当前或候选页面、组件源码，或预览资源内容差异，不写入业务数据。"""

        return await _validate_entity(
            session_factory,
            internal_tools,
            run_context,
            resource_type=resource_type,
            action=action,
            target_id=target_id,
            payload=dict(payload or {}),
        )

    tools = [
        get_operation_guide,
        get_code_standards,
        list_entities,
        get_entity,
        create_entity,
        update_entity,
        archive_entity,
        validate_entity,
        execute_action,
    ]
    from app.ai.generic_business_tool_schema import project_generic_business_tool_schema
    from app.ai.tool_specs import list_operation_guide_specs

    guides = list_operation_guide_specs()
    for tool in tools:
        tool.parameters = project_generic_business_tool_schema(tool.name, tool.parameters, guides)
    return tools


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


async def _dispatch_entity_query(
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

    filters_model = get_query_filters_model(resource_type, action)
    if filters_model is None:
        raise AppException(status_code=400, code="AI_ENTITY_QUERY_UNSUPPORTED", detail="该对象不支持指定查询 action。")
    filters = _validate_arguments_model(filters_model, filters)
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
                _ensure_active_status(item.status, "项目")
                return _sanitize_ai_project_item(item.model_dump(mode="json"))
            if action == "configuration" and target_id is not None:
                _ensure_project_in_work_scope(dependencies, target_id)
                item = await service.get(target_id, user_id=user_id)
                _ensure_workspace(item.workspace_id, workspace_id)
                _ensure_active_status(item.status, "项目")
                components = await SuggestedComponentService(session).list_project_component_items(
                    target_id,
                    workspace_id=workspace_id,
                )
                return _configuration_payload(item, components)
        if action == "route_tree":
            project_id = _required_target_id(target_id, "查询项目子资源时必须提供 target_id。")
            context = await _with_project_scope(session_factory, run_context, project_id)
            return await _call_internal(tools["get_project_route_tree"], context, filters)
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
        if action in {"detail", "versions", "version_content", "dependencies"}:
            async with session_factory() as session:
                service = PageService(session)
                item = await service.get(page_id, user_id=user_id)
                _ensure_workspace(item.workspace_id, workspace_id)
                _ensure_project_in_work_scope(dependencies, item.project_id)
                _ensure_active_status(item.status, "页面")
                if action == "detail":
                    return _sanitize_ai_page_item(item.model_dump(mode="json"))
                if action == "versions":
                    return [entry.model_dump(mode="json") for entry in await service.list_versions(page_id, user_id=user_id)]
                if action == "version_content":
                    return (await service.get_version_content(page_id, int(filters["version_no"]), user_id=user_id)).model_dump(mode="json")
                return (await service.get_current_module_dependencies(page_id, user_id=user_id)).model_dump(mode="json")
        if action == "content":
            context = await _with_page_scope(session_factory, run_context, page_id)
            return await _call_internal(tools["get_page_content"], context, {"page_id": page_id})
    if resource_type == "theme":
        return await _query_themes(session_factory, workspace_id, action, target_id, filters)
    if resource_type == "style":
        if action == "configuration":
            style_id = _required_target_id(target_id, "读取样式配置时必须提供 target_id。")
            async with session_factory() as session:
                item = await WorkspaceStyleService(session).get(workspace_id, style_id)
                components = await SuggestedComponentService(session).list_style_component_items(workspace_id, style_id)
                return _configuration_payload(item, components)
        return await _query_styles(session_factory, workspace_id, action, target_id, filters)
    if resource_type == "component" and action == "list":
        scope = str(filters.pop("scope", "all") or "all")
        project_id = filters.pop("project_id", None) or dependencies.get("project_id")
        if scope == "suggested":
            resolved_project_id = _required_target_id(project_id, "查询项目建议组件时必须提供 project_id 或处于项目焦点。")
            await _with_project_scope(session_factory, run_context, resolved_project_id)
            async with session_factory() as session:
                items = await SuggestedComponentService(session).list_project_component_items(
                    resolved_project_id,
                    workspace_id=workspace_id,
                )
                return _filter_suggested_items(items, filters)
    if resource_type == "component" and action == "version_content":
        component_id = _required_target_id(target_id, "读取组件版本内容时必须提供 target_id。")
        async with session_factory() as session:
            service = WorkspaceComponentService(session)
            component = await service.get(component_id, user_id=user_id)
            _ensure_workspace(component.workspace_id, workspace_id)
            _ensure_active_status(component.status, "组件")
            return (await service.get_version_content(component_id, int(filters["version_no"]), user_id=user_id)).model_dump(mode="json")
    query_context = run_context
    if resource_type == "asset" and action == "list" and filters.get("project_id") is not None:
        query_context = await _with_project_scope(session_factory, run_context, int(filters.pop("project_id")))

    tool_name = _query_tool_name(resource_type, action)
    if tool_name:
        payload = dict(filters)
        if target_id is not None:
            payload[_target_parameter(resource_type)] = target_id
        return await _call_internal(tools[tool_name], query_context, payload)
    raise AppException(status_code=400, code="AI_ENTITY_QUERY_UNSUPPORTED", detail="该对象不支持指定查询 action。")


async def _create_entity(
    session_factory: async_sessionmaker[AsyncSession],
    tools: dict[str, PlatformTool],
    run_context: AgentToolContext,
    resource_type: str,
    mode: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """分派创建操作并保证工作空间 ID 来自运行上下文。"""

    payload = _validate_operation_payload(resource_type, "create", mode, payload)
    dependencies, claims = await resolve_tool_context(session_factory, run_context, required_scopes=(), required_dependency_fields=("workspace_id",))
    workspace_id = int(dependencies["workspace_id"])
    operator_id = extract_user_id(str(claims.get("sub")))
    source_id = int(payload.pop("source_id")) if "source_id" in payload else None
    if mode == "copy" and resource_type == "page":
        await _with_page_scope(session_factory, run_context, _required_target_id(source_id, "复制页面时必须提供 source_id。"))
        destination_project_id = int(payload.pop("project_id"))
        await _require_cross_focus_write_confirmation(session_factory, run_context, destination_project_id, "复制页面")
        async with session_factory() as session:
            copied = await PageService(session).copy_to_project(
                int(source_id),
                PageCopyToProjectRequest.model_validate({"target_project_id": destination_project_id, **payload}),
                operator_id,
            )
            _ensure_workspace(copied.workspace_id, workspace_id)
            result = copied.model_dump(mode="json")
        return _wrap_internal_mutation(resource_type, "create", result, target_id=copied.id, source_id=source_id, effect="create")
    if mode == "copy" and resource_type in {"theme", "style"}:
        result = await _copy_theme_or_style(
            session_factory,
            run_context,
            resource_type,
            _required_target_id(source_id, "复制时必须提供 source_id。"),
            payload,
        )
        return _wrap_internal_mutation(
            resource_type,
            "create",
            result,
            target_id=_extract_result_target_id(result),
            source_id=source_id,
            effect="create",
        )
    if mode == "copy" and resource_type == "asset":
        async with session_factory() as session:
            source_asset = await AssetService(session)._get_asset_or_raise(
                workspace_id,
                _required_target_id(source_id, "复制资源时必须提供 source_id。"),
            )
            _ensure_active_status(source_asset.status, "资源")
        result = await _call_internal(
            tools["copy_resource_asset"],
            run_context,
            {"asset_id": _required_target_id(source_id, "复制资源时必须提供 source_id。"), **payload},
        )
        return _wrap_internal_mutation(
            resource_type,
            "create",
            result,
            target_id=_extract_result_target_id(result),
            source_id=source_id,
            effect="create",
        )
    if mode == "upload" and resource_type == "asset":
        result = await _call_internal(tools["save_uploaded_image_as_resource"], run_context, payload)
        return _wrap_internal_mutation(
            resource_type,
            "create",
            result,
            target_id=_extract_result_target_id(result),
            effect="create",
        )
    if mode != "new":
        raise AppException(status_code=400, code="AI_ENTITY_CREATE_UNSUPPORTED", detail="该对象类型不支持指定创建模式。")
    if resource_type == "project":
        if str(dependencies.get("work_scope_mode") or "workspace") == "selected_projects":
            raise AppException(
                status_code=403,
                code="AI_PROJECT_CREATE_OUTSIDE_WORK_SCOPE",
                detail="显式项目工作集模式下不能创建尚未进入工作集的新项目；请先切换为全部项目。",
            )
        if "build_assets" in payload:
            build_assets = payload.pop("build_assets")
            if build_assets is not None:
                payload["build_extra_assets_json"] = build_assets
        payload["status"] = RecordStatus.ACTIVE.value
        payload["workspace_id"] = workspace_id
        async with session_factory() as session:
            result = (await ProjectService(session).create(ProjectCreateRequest.model_validate(payload), operator_id)).model_dump(mode="json")
        return _wrap_internal_mutation(resource_type, "create", result, target_id=int(result["id"]), effect="create")
    if resource_type == "theme":
        safe = ThemeCreatePayload.model_validate(payload)
        async with session_factory() as session:
            created = await WorkspaceThemeService(session).create(
                workspace_id,
                WorkspaceThemeCreateRequest.model_validate(safe.model_dump()),
                operator_id,
            )
            result = _theme_payload(created)
        return _wrap_internal_mutation(resource_type, "create", result, target_id=created.id, effect="create")
    if resource_type == "style":
        async with session_factory() as session:
            created = await WorkspaceStyleService(session).create(
                workspace_id,
                WorkspaceStyleCreateRequest.model_validate(payload),
                operator_id,
            )
            result = created.model_dump(mode="json")
        return _wrap_internal_mutation(resource_type, "create", result, target_id=created.id, effect="create")
    if resource_type == "page":
        project_id = int(payload.pop("project_id", 0) or 0)
        await _require_cross_focus_write_confirmation(session_factory, run_context, project_id, "创建页面")
        context = await _with_project_scope(session_factory, run_context, project_id)
        payload["page_content"] = payload.pop("content")
        result = await _call_internal(tools["create_project_page"], context, payload)
        return _wrap_internal_mutation(
            resource_type,
            "create",
            result,
            target_id=_extract_result_target_id(result),
            effect="create",
        )
    tool_name = {"component": "create_component", "asset": "create_resource_asset"}.get(resource_type)
    if tool_name:
        if resource_type == "asset":
            payload["asset_type"] = AssetType(str(payload["asset_type"]))
        result = await _call_internal(tools[tool_name], run_context, payload)
        return _wrap_internal_mutation(
            resource_type,
            "create",
            result,
            target_id=_extract_result_target_id(result),
            effect="create",
        )
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
    """分派更新操作，共享配置通过项目或样式服务原子写入。"""

    payload = _validate_operation_payload(resource_type, "update", action, payload)
    dependencies, claims = await resolve_tool_context(session_factory, run_context, required_scopes=(), required_dependency_fields=("workspace_id",))
    workspace_id = int(dependencies["workspace_id"])
    operator_id = extract_user_id(str(claims.get("sub")))
    if resource_type == "project":
        if action == "route_tree":
            context = await _with_project_scope(session_factory, run_context, target_id)
            return await _call_internal(tools["update_project_route_tree"], context, payload)
        if action == "metadata":
            request_payload = payload
        elif action == "configuration":
            request_payload = {"configuration": ProjectPatchConfiguration(mode="patch", **payload).model_dump(mode="json")}
        elif action == "apply_style":
            request_payload = {
                "configuration": ProjectStyleConfiguration(mode="style", style_id=int(payload["style_id"])).model_dump(mode="json")
            }
        elif action == "build_assets":
            request_payload = {"build_extra_assets_json": payload}
        else:
            raise AppException(status_code=400, code="AI_ENTITY_UPDATE_UNSUPPORTED", detail="项目不支持指定更新 action。")
        async with session_factory() as session:
            current = await ProjectService(session).get(target_id, user_id=operator_id)
            _ensure_workspace(current.workspace_id, workspace_id)
            _ensure_project_in_work_scope(dependencies, target_id)
            await _raise_cross_focus_confirmation(run_context, claims, target_id, "修改项目")
            return (await ProjectService(session).update(target_id, ProjectUpdateRequest.model_validate(request_payload), operator_id)).model_dump(mode="json")
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
        request_payload = payload if action == "metadata" else {"configuration": payload}
        async with session_factory() as session:
            updated = await WorkspaceStyleService(session).update(
                workspace_id,
                target_id,
                WorkspaceStyleUpdateRequest.model_validate(request_payload),
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
    payload: dict[str, Any],
) -> dict[str, Any]:
    """执行已登记的生命周期命令，并返回 lifecycle mutation。"""

    payload = _validate_operation_payload(resource_type, "action", action, payload)
    if (resource_type, action) != ("component", "publish"):
        raise AppException(status_code=400, code="AI_ACTION_UNSUPPORTED", detail="该生命周期命令未开放。")
    component_id = _required_target_id(target_id, "发布组件时必须提供 target_id。")
    result = await _call_internal(tools["publish_component"], run_context, {"component_id": component_id, **payload})
    return _wrap_internal_mutation(
        resource_type,
        "action",
        result,
        action=action,
        target_id=component_id,
        effect="lifecycle",
    )


async def _validate_entity(
    session_factory: async_sessionmaker[AsyncSession],
    tools: dict[str, PlatformTool],
    run_context: AgentToolContext,
    *,
    resource_type: str,
    action: str,
    target_id: int | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """执行不落库校验，并把业务不通过归一化为 data.valid=false。"""

    payload = _validate_operation_payload(resource_type, "validate", action, payload)
    if resource_type == "asset" and action == "preview":
        asset_id = _required_target_id(target_id, "预览资源内容差异时必须提供 target_id。")
        result = await _call_internal(
            tools["preview_resource_content_diff"],
            run_context,
            {"asset_id": asset_id, **payload},
        )
        return build_validation_envelope(resource_type=resource_type, action=action, data=result)
    if action != "check" or resource_type not in {"page", "component"}:
        raise AppException(status_code=400, code="AI_ENTITY_VALIDATION_UNSUPPORTED", detail="该校验组合未开放。")
    mode = str(payload.pop("mode"))
    project_id = payload.pop("project_id", None)
    if target_id is not None and project_id is not None:
        raise AppException(status_code=422, code="AI_VALIDATION_PROJECT_CONFLICT", detail="提供 target_id 时不能再提交 project_id。")
    if mode in {"current", "edits"} and target_id is None:
        raise AppException(status_code=422, code="AI_VALIDATION_TARGET_REQUIRED", detail=f"mode={mode} 时必须提供 target_id。")
    context = run_context
    arguments = dict(payload)
    if target_id is not None:
        arguments[_target_parameter(resource_type)] = int(target_id)
        if resource_type == "page":
            context = await _with_page_scope(session_factory, run_context, int(target_id))
    elif resource_type == "page":
        if project_id is None:
            raise AppException(status_code=422, code="AI_VALIDATION_PROJECT_REQUIRED", detail="无 target_id 的页面完整源码校验必须提供 project_id。")
        context = await _with_project_scope(session_factory, run_context, int(project_id))
    result = await _call_internal(
        tools["check_page_code" if resource_type == "page" else "check_component_code"],
        context,
        arguments,
    )
    return build_validation_envelope(resource_type=resource_type, action=action, data=result)


def _validate_operation_payload(
    resource_type: str,
    operation: str,
    action: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """使用操作手册同源模型校验 payload，并保留调用方显式提交的字段。"""

    payload_model = get_operation_payload_model(resource_type, operation, action)
    if payload_model is None:
        raise AppException(status_code=400, code="AI_OPERATION_UNSUPPORTED", detail="该对象与操作组合未开放。")
    return _validate_arguments_model(payload_model, payload)


def _validate_arguments_model(model: type[Any], arguments: dict[str, Any]) -> dict[str, Any]:
    """把 Pydantic 参数错误转换为模型可恢复的统一业务错误。"""

    try:
        return model.model_validate(arguments).model_dump(mode="python", exclude_unset=True)
    except ValidationError as exc:
        issues = [
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in exc.errors(include_url=False)
        ]
        raise AppException(
            status_code=422,
            code="AI_OPERATION_ARGUMENTS_INVALID",
            detail=f"操作参数不符合操作手册：{'；'.join(issues)}。请查询对应精确手册后重试。",
        ) from exc


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
        _ensure_active_status(project.status, "项目")
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
        _ensure_active_status(page.status, "页面")
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
    """裁剪项目首页截图字段并按工作集过滤项目列表。"""

    items = [_sanitize_ai_project_item(item) for item in data.get("items", [])]
    if str(dependencies.get("work_scope_mode") or "workspace") == "workspace":
        return {**data, "items": items}
    allowed = {int(item) for item in dependencies.get("allowed_project_ids") or []}
    filtered_items = [item for item in items if int(item.get("id") or 0) in allowed]
    return {**data, "items": filtered_items, "total": len(filtered_items)}


def _sanitize_ai_project_item(item: dict[str, Any]) -> dict[str, Any]:
    """裁剪 AI 项目查询不需要的首页截图地址。"""

    return {key: value for key, value in item.items() if key not in AI_PROJECT_QUERY_EXCLUDED_FIELDS}


def _filter_suggested_items(items: list[Any], filters: dict[str, Any]) -> dict[str, Any]:
    """按通用组件列表筛选条件裁剪项目建议组件。"""

    keyword = str(filters.get("keyword") or "").strip().lower()
    component_type = str(filters.get("component_type") or "").strip()
    limit = max(1, min(int(filters.get("limit", 50)), 100))
    payload = [item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item) for item in items]
    if component_type:
        payload = [item for item in payload if str(item.get("component_type") or "") == component_type]
    if keyword:
        payload = [
            item for item in payload
            if keyword in " ".join(
                str(item.get(field) or "").lower()
                for field in ("name", "import_name", "summary", "code")
            )
        ]
    total = len(payload)
    return {"items": payload[:limit], "total": total, "source": "project_suggested"}


def _filter_page_items(data: dict[str, Any], dependencies: dict[str, Any]) -> dict[str, Any]:
    """裁剪页面敏感字段并按所属项目过滤列表，空 selected_projects 返回空集合。"""

    items = [_sanitize_ai_page_item(item) for item in data.get("items", [])]
    if str(dependencies.get("work_scope_mode") or "workspace") == "workspace":
        return {**data, "items": items}
    allowed = {int(item) for item in dependencies.get("allowed_project_ids") or []}
    filtered_items = [item for item in items if int(item.get("project_id") or 0) in allowed]
    return {**data, "items": filtered_items, "total": len(filtered_items)}


def _sanitize_ai_page_item(item: dict[str, Any]) -> dict[str, Any]:
    """裁剪 AI 页面查询不需要的源码、审计字段和截图元数据。"""

    return {key: value for key, value in item.items() if key not in AI_PAGE_QUERY_EXCLUDED_FIELDS}


def _build_detail_query_message(resource_type: str, target_id: int | None, data: Any) -> str:
    """为详情查询生成后续视图调用提示，保持提示与真实工具参数一致。"""

    if target_id is None:
        return "查询完成。"
    if resource_type == "project":
        return (
            f'查询完成。如需读取项目展示配置，请继续调用 get_entity(resource_type="project", '
            f'view="configuration", target_id={target_id})；如需读取项目路由树，请调用 '
            f'get_entity(resource_type="project", view="route_tree", target_id={target_id})。'
        )
    if resource_type == "page":
        return (
            f'查询完成。如需读取页面当前源码，请调用 get_entity(resource_type="page", view="content", '
            f'target_id={target_id})；如需读取版本历史，请调用 get_entity(resource_type="page", '
            f'view="versions", target_id={target_id})；如需读取指定版本源码，请先取得 version_no，'
            f'再调用 get_entity(resource_type="page", view="version_content", target_id={target_id}, '
            'options={"version_no": <version_no>})；如需读取依赖索引，请调用 '
            f'get_entity(resource_type="page", view="dependencies", target_id={target_id})。'
        )
    if resource_type == "style":
        return (
            f'查询完成。如需读取样式完整展示配置和建议组件，请继续调用 get_entity(resource_type="style", '
            f'view="configuration", target_id={target_id})。'
        )
    if resource_type == "asset" and isinstance(data, dict) and data.get("content_editable") is True:
        return (
            f'查询完成。如需读取该可编辑资源的文本内容，请继续调用 get_entity(resource_type="asset", '
            f'view="content", target_id={target_id})。'
        )
    return "查询完成。"


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
    """只查询工作空间中的启用样式。"""

    async with session_factory() as session:
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
        ("asset", "detail"): "get_resource_asset_detail",
        ("asset", "content"): "get_resource_asset_content",
        ("asset", "tags"): "list_resource_tags",
        ("runtime_kit", "list"): "list_runtime_kit_capabilities",
        ("runtime_kit", "detail"): "get_runtime_kit_capability",
        ("font", "list"): "list_workspace_font_assets",
    }.get((resource_type, action))


def _target_parameter(resource_type: str) -> str:
    """返回既有工具使用的目标 ID 参数名。"""

    return {"component": "component_id", "asset": "asset_id", "page": "page_id"}.get(resource_type, "target_id")


def _configuration_payload(item: Any, components: list[Any]) -> dict[str, Any]:
    """把项目或样式的扁平存储响应转换为共享配置快照。"""

    return {
        "presentation": {
            "page_width": item.page_width,
            "page_height": item.page_height,
            "base_font_size": item.base_font_size,
            "icon_default_stroke_width": item.icon_default_stroke_width,
            "show_pdf_export_button": item.show_pdf_export_button,
            "menu_mode": getattr(item.menu_mode, "value", item.menu_mode),
            "theme_key": item.theme_key,
            "style_spec_markdown": item.style_spec_markdown,
        },
        "suggested_components": {
            "component_ids": [int(component.id) for component in components],
        },
    }


def _wrap_internal_mutation(
    resource_type: str,
    operation: str,
    result: Any,
    *,
    action: str | None = None,
    target_id: int | None = None,
    source_id: int | None = None,
    effect: Literal["create", "update", "lifecycle"] = "update",
) -> dict[str, Any]:
    """把内部工具结果包装为统一 mutation envelope。"""

    target = None if target_id is None else {"id": target_id, "resource_type": resource_type}
    source = None if source_id is None else {"id": source_id, "resource_type": resource_type}
    return build_mutation_envelope(
        resource_type=resource_type,
        operation=operation,
        action=action,
        message=_result_message(result, f"{resource_type} 操作已完成。"),
        target=target,
        source=source,
        mutation_kind={"page": "project-pages", "asset": "asset"}.get(resource_type, resource_type),
        data=result,
        effect=effect,
    )


def _extract_result_target_id(result: Any) -> int | None:
    """从内部创建结果的常见形状中提取新对象 ID。"""

    if not isinstance(result, dict):
        return None
    for field_name in ("id", "page_id", "component_id", "asset_id"):
        if result.get(field_name) is not None:
            return int(result[field_name])
    for field_name in ("page", "component", "asset", "theme", "style"):
        nested = result.get(field_name)
        if isinstance(nested, dict) and nested.get("id") is not None:
            return int(nested["id"])
    return None


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
        status=RecordStatus.ACTIVE,
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


def _ensure_active_status(status: Any, label: str) -> None:
    """拒绝通过已知 ID 读取归档对象，保持 AI 查询边界只包含启用内容。"""

    value = getattr(status, "value", status)
    if str(value) != RecordStatus.ACTIVE.value:
        raise AppException(status_code=404, code="AI_ENTITY_NOT_FOUND", detail=f"{label}不存在或已归档。")
