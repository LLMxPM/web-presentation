"""文件功能：定义资源助手的资源读取、内容写入、复制与归档工具。"""

from __future__ import annotations

import json
import re
from typing import Any

from agno.run import RunContext
from agno.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import RESOURCE_TOOL_READ_SCOPES, RESOURCE_TOOL_WRITE_SCOPES
from app.ai.tools.shared import resolve_tool_context
from app.core.config import get_settings
from app.models.enums import AssetType, RecordStatus
from app.schemas.asset import AssetResponse
from app.services.asset_service import AssetService
from app.services.project_suggested_reference_asset_service import ProjectSuggestedReferenceAssetService


def build_resource_manager_tools(session_factory: async_sessionmaker[AsyncSession]) -> list[Any]:
    """构建资源助手可用的全部工具。"""

    return [
        build_list_resource_assets_tool(session_factory),
        build_list_project_suggested_reference_assets_tool(session_factory),
        build_get_resource_asset_content_tool(session_factory),
        build_list_resource_tags_tool(session_factory),
        build_create_resource_asset_tool(session_factory),
        build_preview_resource_content_diff_tool(session_factory),
        build_apply_resource_content_diff_tool(session_factory),
        build_update_resource_asset_metadata_tool(session_factory),
        build_copy_resource_asset_tool(session_factory),
        build_archive_resource_asset_tool(session_factory),
    ]


def build_list_resource_assets_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建资源列表工具。"""

    @tool(show_result=False)
    async def list_resource_assets(
        run_context: RunContext,
        asset_type: AssetType | None = None,
        tag: str | None = None,
        keyword: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """读取当前工作空间 active 普通资源摘要，可按类型、标签和关键词过滤。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=RESOURCE_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        bounded_limit = max(1, min(int(limit), 100))
        normalized_keyword = str(keyword or "").strip().lower()
        normalized_tag = str(tag or "").strip().lower()
        async with session_factory() as session:
            assets, _ = await AssetService(session).list_assets(
                int(dependencies["workspace_id"]),
                asset_type=asset_type,
                status=RecordStatus.ACTIVE,
                include_history=False,
                keyword=keyword,
                page=1,
                page_size=100,
            )
            items = []
            for asset in assets:
                if normalized_tag and normalized_tag not in {str(item).strip().lower() for item in asset.tags or []}:
                    continue
                if normalized_keyword and normalized_keyword not in _build_asset_search_text(asset):
                    continue
                items.append(_dump_asset_list_item(asset))
                if len(items) >= bounded_limit:
                    break
            return {"total": len(items), "items": items}

    return list_resource_assets


def build_list_project_suggested_reference_assets_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建项目建议引用资源列表工具。"""

    @tool(show_result=False)
    async def list_project_suggested_reference_assets(run_context: RunContext) -> dict[str, Any]:
        """读取当前项目建议优先参考的内容资源摘要，不返回 URL 和标签。"""

        dependencies, _ = await resolve_tool_context(
            session_factory,
            run_context,
            required_scopes=RESOURCE_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id", "project_id"),
        )
        async with session_factory() as session:
            items = await ProjectSuggestedReferenceAssetService(session).list_asset_items(
                int(dependencies["project_id"]),
                workspace_id=int(dependencies["workspace_id"]),
            )
            return {"total": len(items), "items": [item.model_dump(mode="json") for item in items]}

    return list_project_suggested_reference_assets


def build_get_resource_asset_content_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建资源文本内容读取工具。"""

    @tool(show_result=False)
    async def get_resource_asset_content(run_context: RunContext, asset_id: int) -> dict[str, Any]:
        """读取 SVG 图片、SVG 图标、Draw.io、Mermaid、Chart 或 Formula 资源的文本内容。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=RESOURCE_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        async with session_factory() as session:
            service = AssetService(session)
            asset = await service._get_asset_or_raise(int(dependencies["workspace_id"]), int(asset_id))
            content = await service.get_asset_content(int(dependencies["workspace_id"]), int(asset_id))
            return {"asset": _dump_asset(asset), "content": content}

    return get_resource_asset_content


def build_list_resource_tags_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建资源标签读取工具。"""

    @tool(show_result=False)
    async def list_resource_tags(run_context: RunContext) -> list[str]:
        """列出当前工作空间资源库中出现过的标签。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=RESOURCE_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        async with session_factory() as session:
            return await AssetService(session).list_tags(int(dependencies["workspace_id"]))

    return list_resource_tags


def build_create_resource_asset_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建资源内容创建工具。"""

    @tool(show_result=False, pre_hook=_repair_tags_argument_before_validation)
    async def create_resource_asset(
        run_context: RunContext,
        asset_type: AssetType,
        name: str,
        original_name: str,
        content: str,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """创建 SVG 图片、SVG 图标、Draw.io、Mermaid、Chart 或 Formula 资源；不支持位图 image、video 和 font 内容生成。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=RESOURCE_TOOL_WRITE_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        async with session_factory() as session:
            asset = await AssetService(session).create_content_asset(
                int(dependencies["workspace_id"]),
                asset_type=asset_type,
                name=name,
                original_name=original_name,
                content=content,
                description=description,
                tags=_normalize_tags_argument(tags) or [],
            )
            return {"success": True, "message": "资源已创建。", "asset": _dump_asset(asset)}

    return create_resource_asset


def build_preview_resource_content_diff_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建资源内容写入预览工具。"""

    @tool(show_result=False)
    async def preview_resource_content_diff(run_context: RunContext, asset_id: int, content: str) -> dict[str, Any]:
        """预览将新内容写入资源后的 unified diff，不落库。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=RESOURCE_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        async with session_factory() as session:
            return await AssetService(session).preview_content_update(int(dependencies["workspace_id"]), int(asset_id), content)

    return preview_resource_content_diff


def build_apply_resource_content_diff_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建资源内容写入工具。"""

    @tool(show_result=False)
    async def apply_resource_content_diff(
        run_context: RunContext,
        asset_id: int,
        content: str,
        change_note: str | None = None,
    ) -> dict[str, Any]:
        """写入资源新内容；写入前自动创建 archived 历史副本，不走 HITL 确认。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=RESOURCE_TOOL_WRITE_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        async with session_factory() as session:
            asset = await AssetService(session).update_asset_content(
                int(dependencies["workspace_id"]),
                int(asset_id),
                content,
                change_note=change_note or "AI 资源助手写入内容",
            )
            return {"success": True, "message": "资源内容已写入，写入前副本已自动归档。", "asset": _dump_asset(asset)}

    return apply_resource_content_diff


def build_update_resource_asset_metadata_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建资源元数据更新工具。"""

    @tool(show_result=False, pre_hook=_repair_tags_argument_before_validation)
    async def update_resource_asset_metadata(
        run_context: RunContext,
        asset_id: int,
        name: str | None = None,
        original_name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """更新资源 name、展示文件名、描述或标签；不修改内容。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=RESOURCE_TOOL_WRITE_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        async with session_factory() as session:
            asset = await AssetService(session).update_asset_metadata(
                int(dependencies["workspace_id"]),
                int(asset_id),
                name=name,
                original_name=original_name,
                description=description,
                tags=_normalize_tags_argument(tags) if tags is not None else None,
            )
            return {"success": True, "message": "资源元数据已更新。", "asset": _dump_asset(asset)}

    return update_resource_asset_metadata


def build_copy_resource_asset_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建资源复制工具。"""

    @tool(show_result=False, pre_hook=_repair_tags_argument_before_validation)
    async def copy_resource_asset(
        run_context: RunContext,
        asset_id: int,
        name: str | None = None,
        original_name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        status: RecordStatus = RecordStatus.ACTIVE,
        archive_reason: str | None = None,
    ) -> dict[str, Any]:
        """复制资源记录并复用物理文件；可用于从历史副本复制为新资源。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=RESOURCE_TOOL_WRITE_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        async with session_factory() as session:
            asset = await AssetService(session).copy_asset(
                int(dependencies["workspace_id"]),
                int(asset_id),
                name=name,
                original_name=original_name,
                description=description,
                tags=_normalize_tags_argument(tags) if tags is not None else None,
                status=status,
                archive_reason=archive_reason,
            )
            return {"success": True, "message": "资源已复制。", "asset": _dump_asset(asset)}

    return copy_resource_asset


def build_archive_resource_asset_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建资源归档工具。"""

    @tool(show_result=False)
    async def archive_resource_asset(
        run_context: RunContext,
        asset_id: int,
        archive_reason: str | None = None,
    ) -> dict[str, Any]:
        """归档资源；归档不影响已存在引用，不走 HITL 确认。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=RESOURCE_TOOL_WRITE_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        async with session_factory() as session:
            asset = await AssetService(session).archive_asset(
                int(dependencies["workspace_id"]),
                int(asset_id),
                archive_reason=archive_reason,
            )
            return {"success": True, "message": "资源已归档，现有引用仍可解析。", "asset": _dump_asset(asset)}

    return archive_resource_asset


def _dump_asset(asset: Any) -> dict[str, Any]:
    """转换资源为工具响应中的稳定 JSON 结构。"""

    payload = AssetResponse.model_validate(asset).model_dump(mode="json")
    settings = get_settings()
    payload["url"] = f"{settings.backend_public_base_url.rstrip('/')}/public/assets/{asset.workspace_id}/{asset.file_hash}"
    return payload


def _dump_asset_list_item(asset: Any) -> dict[str, Any]:
    """转换资源为面向 LLM 列表选择的简化摘要。"""

    payload = _dump_asset(asset)
    return {
        "id": payload["id"],
        "name": payload["name"],
        "original_name": payload["original_name"],
        "description": payload.get("description"),
        "asset_type": payload["asset_type"],
        "asset_role": payload["asset_role"],
        "render_type": payload["render_type"],
        "tags": payload.get("tags") or [],
        "content_editable": payload["content_editable"],
        "updated_at": payload["updated_at"],
    }


def _build_asset_search_text(asset: Any) -> str:
    """构建资源关键词搜索文本。"""

    return " ".join(
        [
            str(asset.name or ""),
            str(asset.original_name or ""),
            str(asset.description or ""),
            str(asset.asset_type or ""),
            " ".join(str(tag) for tag in asset.tags or []),
        ]
    ).lower()


_TAG_SPLIT_PATTERN = re.compile(r"[,，、;；\r\n]+")


def _repair_tags_argument_before_validation(fc: Any | None = None) -> None:
    """在 Pydantic 校验前修复模型把 tags 二次编码为字符串的常见情况。"""

    arguments = getattr(fc, "arguments", None)
    if not isinstance(arguments, dict) or "tags" not in arguments:
        return

    raw_tags = arguments.get("tags")
    if isinstance(raw_tags, str) or isinstance(raw_tags, list):
        arguments["tags"] = _normalize_tags_argument(raw_tags)


def _normalize_tags_argument(value: list[Any] | str | None) -> list[str] | None:
    """把资源工具 tags 入参归一化为字符串列表，并兼容 JSON 数组字符串。"""

    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.lower() in {"none", "null"}:
            return None
        parsed = _parse_tag_json_string(stripped)
        if parsed is not _UNPARSED_JSON:
            return _normalize_tags_argument(parsed)
        return _normalize_tag_items(_TAG_SPLIT_PATTERN.split(stripped))
    return _normalize_tag_items(value)


_UNPARSED_JSON = object()


def _parse_tag_json_string(value: str) -> Any:
    """仅尝试解析 JSON 数组或 JSON 字符串形式的标签输入。"""

    if not value.startswith(("[", '"')):
        return _UNPARSED_JSON
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return _UNPARSED_JSON


def _normalize_tag_items(items: list[Any]) -> list[str]:
    """清理标签列表中的空项并保持去重顺序。"""

    tags: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in tags:
            tags.append(text)
    return tags
