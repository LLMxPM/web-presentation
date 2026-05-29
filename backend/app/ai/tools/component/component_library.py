"""文件功能：定义组件助手的组件库读取、草稿、Edits 与删除工具。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from agno.run import RunContext
from agno.tools import tool
from agno.tools.function import ToolResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import (
    COMPONENT_TOOL_DELETE_SCOPES,
    COMPONENT_TOOL_READ_SCOPES,
    COMPONENT_TOOL_WRITE_SCOPES,
    extract_user_id,
)
from app.ai.tools.code_check import build_check_component_code_tool
from app.ai.tools.component.component_detail_prompt import build_component_detail_prompt
from app.ai.tools.resource.resource_library import (
    build_get_resource_asset_content_tool,
    build_list_resource_assets_tool,
    build_list_resource_tags_tool,
)
from app.ai.tools.shared import (
    SourceEditInput,
    allow_preview_schema_object_parameter,
    apply_source_edits,
    build_component_import_usage,
    calculate_source_hash,
    normalize_preview_schema_argument,
    resolve_tool_context,
)
from app.core.exceptions import AppException
from app.core.runtime_module_policy import (
    get_runtime_kit_capability as get_runtime_kit_capability_item,
    list_runtime_kit_capabilities as list_runtime_kit_capability_items,
)
from app.models.enums import PageFileType, RecordStatus, WorkspaceComponentType
from app.schemas.component import (
    WorkspaceComponentCreateRequest,
    WorkspaceComponentItem,
    WorkspaceComponentListQuery,
    WorkspaceComponentPublishRequest,
    WorkspaceComponentUpdateRequest,
)
from app.services.code_check_service import CodeCheckService, build_code_check_failed_result
from app.services.workspace_component_service import WorkspaceComponentService


def build_component_manager_tools(session_factory: async_sessionmaker[AsyncSession]) -> list[Any]:
    """构建组件助手可用的全部工具。"""

    return [
        build_list_components_tool(session_factory),
        build_get_component_detail_tool(session_factory),
        build_list_component_versions_tool(session_factory),
        build_get_component_dependencies_tool(session_factory),
        build_list_runtime_kit_capabilities_tool(session_factory),
        build_get_runtime_kit_capability_tool(session_factory),
        build_list_resource_assets_tool(session_factory),
        build_get_resource_asset_content_tool(session_factory),
        build_list_resource_tags_tool(session_factory),
        build_check_component_code_tool(session_factory),
        build_create_component_tool(session_factory),
        build_apply_component_edits_tool(session_factory),
        build_update_component_metadata_tool(session_factory),
        build_publish_component_tool(session_factory),
        build_delete_component_tool(session_factory),
    ]


def build_list_components_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建工作空间组件列表读取工具。"""

    @tool(show_result=False)
    async def list_components(
        run_context: RunContext,
        component_type: WorkspaceComponentType | None = None,
        keyword: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """读取当前工作空间组件库中的组件摘要。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        bounded_limit = max(1, min(int(limit), 100))
        async with session_factory() as session:
            result = await WorkspaceComponentService(session).list(
                WorkspaceComponentListQuery(
                    page=1,
                    page_size=bounded_limit,
                    workspace_id=int(dependencies["workspace_id"]),
                    keyword=str(keyword or "").strip() or None,
                    component_type=component_type,
                )
            )
            return {
                "total": result.total,
                "items": [
                    {
                        "component_id": item.id,
                        "component_code": item.code,
                        "name": item.name,
                        "import_name": item.import_name,
                        "component_type": item.component_type,
                        "summary": item.summary,
                        "current_version_no": item.current_version_no,
                        "status": item.status.value,
                    }
                    for item in result.items
                ],
            }

    return list_components


def build_get_component_detail_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建组件详情读取工具。"""

    @tool(show_result=False)
    async def get_component_detail(run_context: RunContext, component_id: int) -> ToolResult:
        """读取指定组件元数据，并以适合 LLM 精确编辑的文本格式返回源码。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        async with session_factory() as session:
            component = await WorkspaceComponentService(session).get(int(component_id))
            _ensure_component_workspace(component.workspace_id, int(dependencies["workspace_id"]))
            return ToolResult(content=build_component_detail_prompt(component))

    return get_component_detail


def build_list_component_versions_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建组件版本列表读取工具。"""

    @tool(show_result=False)
    async def list_component_versions(run_context: RunContext, component_id: int) -> list[dict[str, Any]]:
        """读取指定组件的版本历史摘要。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        async with session_factory() as session:
            service = WorkspaceComponentService(session)
            component = await service.get(int(component_id))
            _ensure_component_workspace(component.workspace_id, int(dependencies["workspace_id"]))
            versions = await service.list_versions(component.id)
            return [item.model_dump(mode="json") for item in versions]

    return list_component_versions


def build_get_component_dependencies_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建组件当前依赖读取工具。"""

    @tool(show_result=False)
    async def get_component_dependencies(run_context: RunContext, component_id: int) -> dict[str, Any]:
        """读取指定组件当前版本的依赖索引。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        async with session_factory() as session:
            service = WorkspaceComponentService(session)
            component = await service.get(int(component_id))
            _ensure_component_workspace(component.workspace_id, int(dependencies["workspace_id"]))
            result = await service.get_current_dependencies(component.id)
            return result.model_dump(mode="json")

    return get_component_dependencies


def build_list_runtime_kit_capabilities_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建 Runtime Kit 公开能力目录查询工具。"""

    @tool(show_result=False)
    async def list_runtime_kit_capabilities(
        run_context: RunContext,
        kind: str | None = None,
        base_name: str | None = None,
        version_no: int | None = None,
        include_all_versions: bool = False,
        keyword: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """查询 Agent 可引用的 Runtime Kit 只读能力，覆盖 component、composable、util 与 type。"""

        await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        normalized_kind = _normalize_runtime_kit_kind(kind)
        normalized_keyword = str(keyword or "").strip().lower()
        normalized_category = str(category or "").strip()
        normalized_base_name = str(base_name or "").strip()
        bounded_limit = max(1, min(int(limit), 100))

        matched_items: list[dict[str, Any]] = []
        total_matches = 0
        for item in _list_agent_runtime_kit_capabilities(
            base_name=normalized_base_name or None,
            version_no=version_no,
            include_all_versions=include_all_versions,
        ):
            if normalized_kind and item["kind"] != normalized_kind:
                continue
            if normalized_category and item["category"] != normalized_category:
                continue
            if normalized_keyword and normalized_keyword not in _build_runtime_kit_capability_search_text(item):
                continue
            total_matches += 1
            if len(matched_items) < bounded_limit:
                matched_items.append(_dump_runtime_kit_capability_summary(item))
        return {
            "total": total_matches,
            "items": matched_items,
            "message": "Runtime Kit 能力仅用于生成页面或组件源码中的公开 import，不代表可调用后端工具。",
        }

    return list_runtime_kit_capabilities


def build_get_runtime_kit_capability_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建单个 Runtime Kit 公开能力详情查询工具。"""

    @tool(show_result=False)
    async def get_runtime_kit_capability(
        run_context: RunContext,
        name: str,
        kind: str | None = None,
    ) -> dict[str, Any]:
        """读取 Agent 可引用的单个 Runtime Kit 能力详情和 import 用法。"""

        await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise AppException(status_code=400, code="RUNTIME_KIT_CAPABILITY_NAME_REQUIRED", detail="能力名称不能为空。")
        normalized_kind = _normalize_runtime_kit_kind(kind)
        item = get_runtime_kit_capability_item(normalized_name, kind=normalized_kind)
        if item is None or "agent" not in item.get("audiences", []):
            raise AppException(
                status_code=404,
                code="RUNTIME_KIT_CAPABILITY_NOT_FOUND",
                detail="Runtime Kit 能力不存在或未开放给 Agent。",
            )
        return _dump_runtime_kit_capability_detail(item)

    return get_runtime_kit_capability


def build_create_component_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建组件创建工具。"""

    @tool(show_result=False)
    async def create_component(
        run_context: RunContext,
        name: str,
        import_name: str,
        content: str,
        component_type: WorkspaceComponentType = WorkspaceComponentType.CONTENT_BLOCK,
        summary: str | None = None,
        preview_schema: str | dict[str, Any] | None = None,
        change_note: str | None = None,
    ) -> dict[str, Any]:
        """创建工作空间组件草稿，正式引用前需要发布。"""

        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_WRITE_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        operator_id = extract_user_id(str(claims.get("sub")))
        async with session_factory() as session:
            created = await WorkspaceComponentService(session).create(
                WorkspaceComponentCreateRequest(
                    workspace_id=int(dependencies["workspace_id"]),
                    content=content,
                    file_type=PageFileType.VUE,
                    name=name,
                    import_name=import_name,
                    component_type=component_type,
                    summary=summary,
                    preview_schema=normalize_preview_schema_argument(preview_schema),
                    status=RecordStatus.ACTIVE,
                    change_note=change_note or "AI 助手创建组件",
                ),
                operator_id,
            )
            return {
                "success": True,
                "message": "组件草稿已创建，发布后才可被页面或其他组件引用。",
                "component": created.model_dump(mode="json"),
            }

    allow_preview_schema_object_parameter(create_component)
    return create_component


def build_apply_component_edits_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建应用组件源码 Edits 的工具。"""

    @tool(show_result=False)
    async def apply_component_edits(
        run_context: RunContext,
        component_id: int,
        edits: list[SourceEditInput],
        base_draft_hash: str,
        base_published_version_no: int,
        change_note: str | None = None,
    ) -> dict[str, Any]:
        """对指定组件源码应用结构化 edits 并保存为草稿。"""

        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_WRITE_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        operator_id = extract_user_id(str(claims.get("sub")))
        async with session_factory() as session:
            service = WorkspaceComponentService(session)
            component = await service.get(int(component_id))
            _ensure_component_workspace(component.workspace_id, int(dependencies["workspace_id"]))
            _ensure_component_edit_lock(
                component,
                base_draft_hash=base_draft_hash,
                base_published_version_no=base_published_version_no,
            )
            try:
                edit_result = apply_source_edits(component.content, edits)
            except AppException as exc:
                return build_code_check_failed_result(code=exc.code, message=exc.detail, source="edits")
            validation_result = await CodeCheckService(session).check_component_code(
                component_id=component.id,
                workspace_id=component.workspace_id,
                user_id=operator_id,
                content=edit_result.next_content,
            )
            validation_result = _with_apply_validation_metadata(
                validation_result,
                canonical_diff=edit_result.canonical_diff,
                edits_applied=edit_result.applied_edit_count,
                message="组件代码校验失败，未保存草稿。",
            )
            if not _is_validation_passed(validation_result):
                validation_result["component_id"] = component.id
                validation_result["component_code"] = component.code
                return validation_result
            updated = await service.update(
                component.id,
                WorkspaceComponentUpdateRequest(
                    content=edit_result.next_content,
                    change_note=change_note or "AI 助手组件源码更新",
                ),
                operator_id,
            )
            return {
                "success": True,
                "message": "组件源码草稿已更新，发布后才会生成新的可引用版本。",
                "component_id": updated.id,
                "component_code": updated.code,
                "version_no": updated.current_version_no,
                "draft_hash": calculate_source_hash(updated.content),
                "base_published_version_no": updated.draft_base_version_no,
                "edits_applied": edit_result.applied_edit_count,
                "canonical_diff": edit_result.canonical_diff,
                "component": updated.model_dump(mode="json"),
            }

    return apply_component_edits


def _is_validation_passed(result: dict[str, Any]) -> bool:
    """判断 Runtime 代码检查结果是否通过。"""

    return bool(result.get("success") is True or result.get("status") == "passed")


def _with_apply_validation_metadata(
    result: dict[str, Any],
    *,
    canonical_diff: str,
    edits_applied: int,
    message: str,
) -> dict[str, Any]:
    """为组件 apply 内置校验结果补齐 edits 元数据和失败提示。"""

    enriched = dict(result)
    enriched["canonical_diff"] = enriched.get("canonical_diff") or canonical_diff
    enriched["edits_applied"] = edits_applied
    if not _is_validation_passed(enriched):
        enriched["success"] = False
        enriched["status"] = "failed"
        enriched["message"] = message
    return enriched


def build_update_component_metadata_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建更新组件元数据和预览 schema 的工具。"""

    @tool(show_result=False)
    async def update_component_metadata(
        run_context: RunContext,
        component_id: int,
        name: str | None = None,
        import_name: str | None = None,
        component_type: WorkspaceComponentType | None = None,
        summary: str | None = None,
        preview_schema: str | dict[str, Any] | None = None,
        change_note: str | None = None,
    ) -> dict[str, Any]:
        """更新组件名称、源码引用名、分类、描述或 preview_schema。"""

        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_WRITE_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        operator_id = extract_user_id(str(claims.get("sub")))
        async with session_factory() as session:
            service = WorkspaceComponentService(session)
            component = await service.get(int(component_id))
            _ensure_component_workspace(component.workspace_id, int(dependencies["workspace_id"]))
            update_payload: dict[str, Any] = {
                "preview_schema": component.preview_schema
                if preview_schema is None
                else normalize_preview_schema_argument(preview_schema),
                "change_note": change_note or "AI 助手组件元数据更新",
            }
            if name is not None:
                update_payload["name"] = name
            if import_name is not None:
                update_payload["import_name"] = import_name
            if component_type is not None:
                update_payload["component_type"] = component_type
            if summary is not None:
                update_payload["summary"] = summary
            updated = await service.update(
                component.id,
                WorkspaceComponentUpdateRequest(**update_payload),
                operator_id,
            )
            return {
                "success": True,
                "message": "组件元数据已更新。",
                "component": updated.model_dump(mode="json"),
            }

    allow_preview_schema_object_parameter(update_component_metadata)
    return update_component_metadata


def build_publish_component_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建发布组件草稿为正式版本的工具。"""

    @tool(show_result=False)
    async def publish_component(
        run_context: RunContext,
        component_id: int,
        release_name: str | None = None,
        change_note: str | None = None,
    ) -> dict[str, Any]:
        """发布组件当前草稿，生成可被页面和其他组件引用的正式版本。"""

        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_WRITE_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        operator_id = extract_user_id(str(claims.get("sub")))
        async with session_factory() as session:
            service = WorkspaceComponentService(session)
            component = await service.get(int(component_id))
            _ensure_component_workspace(component.workspace_id, int(dependencies["workspace_id"]))
            published = await service.publish(
                component.id,
                WorkspaceComponentPublishRequest(
                    release_name=release_name,
                    change_note=change_note or "AI 助手发布组件",
                ),
                operator_id,
            )
            return {
                "success": True,
                "message": "组件草稿已发布为正式版本，可被页面或其他组件按版本引用。",
                "component": published.model_dump(mode="json"),
                "import_usage": build_component_import_usage(
                    published.code,
                    published.current_version_no,
                    published.name,
                    published.import_name,
                ),
            }

    return publish_component


def build_delete_component_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建软删除组件工具。"""

    @tool(show_result=False, requires_confirmation=True)
    async def delete_component(run_context: RunContext, component_id: int) -> dict[str, Any]:
        """软删除指定工作空间组件。"""

        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_DELETE_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        operator_id = extract_user_id(str(claims.get("sub")))
        async with session_factory() as session:
            service = WorkspaceComponentService(session)
            component = await service.get(int(component_id))
            _ensure_component_workspace(component.workspace_id, int(dependencies["workspace_id"]))
            await service.delete(component.id)
            return {
                "success": True,
                "operator_id": operator_id,
                "message": "组件已删除。",
                "component_id": component.id,
                "component_code": component.code,
            }

    return delete_component


def _ensure_component_workspace(component_workspace_id: int, expected_workspace_id: int) -> None:
    """校验组件属于当前工作空间，避免跨工作空间读写。"""

    if component_workspace_id != expected_workspace_id:
        raise AppException(
            status_code=403,
            code="AI_COMPONENT_SCOPE_DENIED",
            detail="组件不属于当前工作空间，拒绝访问。",
        )


def _ensure_component_edit_lock(
    component: WorkspaceComponentItem,
    *,
    base_draft_hash: str,
    base_published_version_no: int,
) -> None:
    """校验组件草稿锁，避免覆盖已变化的未发布草稿。"""

    if calculate_source_hash(component.content) != str(base_draft_hash or "").strip():
        raise AppException(
            status_code=409,
            code="AI_COMPONENT_DRAFT_STALE",
            detail="组件草稿已变化，请重新读取组件详情后再修改。",
        )
    if int(component.draft_base_version_no) != int(base_published_version_no):
        raise AppException(
            status_code=409,
            code="AI_COMPONENT_DRAFT_BASE_STALE",
            detail="组件草稿基线已变化，请重新读取组件详情后再修改。",
        )


def _normalize_runtime_kit_kind(kind: str | None) -> str | None:
    """校验 Runtime Kit 能力类型筛选值。"""

    normalized_kind = str(kind or "").strip()
    if not normalized_kind:
        return None
    if normalized_kind not in {"component", "composable", "util", "type"}:
        raise AppException(
            status_code=400,
            code="RUNTIME_KIT_CAPABILITY_KIND_INVALID",
            detail="Runtime Kit 能力类型仅支持 component、composable、util 或 type。",
        )
    return normalized_kind


def _list_agent_runtime_kit_capabilities(
    *,
    base_name: str | None = None,
    version_no: int | None = None,
    include_all_versions: bool = False,
) -> list[dict[str, Any]]:
    """返回开放给 Agent 的 Runtime Kit 能力项。"""

    return [
        item
        for item in list_runtime_kit_capability_items(
            base_name=base_name,
            version_no=version_no,
            include_all_versions=include_all_versions,
        )
        if "agent" in item.get("audiences", [])
    ]


def _build_runtime_kit_capability_search_text(item: dict[str, Any]) -> str:
    """把 Runtime Kit 能力项拼成用于关键词过滤的文本。"""

    return " ".join(
        [
            str(item.get("kind") or ""),
            str(item.get("base_name") or ""),
            str(item.get("version_no") or ""),
            str(item.get("name") or ""),
            str(item.get("category") or ""),
            str(item.get("description") or ""),
            str(item.get("display_name") or ""),
            str(item.get("summary") or ""),
            str(item.get("import_path") or ""),
            " ".join(str(tag) for tag in item.get("tags", []) or []),
            " ".join(str(line) for line in item.get("usage", []) or []),
            " ".join(str(line) for line in item.get("constraints", []) or []),
        ]
    ).lower()


def _dump_runtime_kit_capability_summary(item: dict[str, Any]) -> dict[str, Any]:
    """输出 Runtime Kit 能力列表中的精简字段。"""

    return {
        "kind": item["kind"],
        "base_name": item["base_name"],
        "version_no": item["version_no"],
        "name": item["name"],
        "display_name": item["display_name"],
        "summary": item["summary"],
        "category": item["category"],
        "import_path": item["import_path"],
        "tags": item["tags"],
        "previewable": item["previewable"],
        "manifest_version": item["manifest_version"],
    }


def _dump_runtime_kit_capability_detail(item: dict[str, Any]) -> dict[str, Any]:
    """输出 Runtime Kit 能力详情，供 Agent 生成 import 和用法参考。"""

    return {
        **_dump_runtime_kit_capability_summary(item),
        "description": item["description"],
        "usage": item["usage"],
        "returns": item["returns"],
        "return_example": item["return_example"],
        "constraints": item["constraints"],
        "preview_schema": _filter_agent_runtime_kit_preview_schema(item["preview_schema"]),
        "preview_options": item["preview_options"],
        "audiences": item["audiences"],
        "message": "该能力只能通过公开 import_path 在页面或组件源码中引用，不能作为后端工具调用。",
    }


def _filter_agent_runtime_kit_preview_schema(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """过滤不应暴露给 Agent 的 preview_schema 字段。"""

    if not isinstance(value, dict):
        return value

    schema = deepcopy(value)
    props = schema.get("props")
    hidden_prop_names: set[str] = set()
    if isinstance(props, dict):
        filtered_props: dict[str, Any] = {}
        for prop_name, prop_schema in props.items():
            if isinstance(prop_schema, dict) and prop_schema.get("agent_visible") is False:
                hidden_prop_names.add(str(prop_name))
                continue
            if isinstance(prop_schema, dict):
                prop_schema.pop("agent_visible", None)
            filtered_props[str(prop_name)] = prop_schema
        schema["props"] = filtered_props

    presets = schema.get("presets")
    if hidden_prop_names and isinstance(presets, list):
        for preset in presets:
            if not isinstance(preset, dict):
                continue
            preset_props = preset.get("props")
            if isinstance(preset_props, dict):
                for prop_name in hidden_prop_names:
                    preset_props.pop(prop_name, None)
    return schema
