"""文件功能：定义内容助手读取项目样式上下文与更新 Markdown 样式规范的工具。"""

from __future__ import annotations

from typing import Any

from app.ai.platform_tools import AgentToolContext, agent_tool
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import PROJECT_TOOL_READ_SCOPES, PROJECT_TOOL_WRITE_SCOPES, extract_user_id
from app.ai.tools.shared import resolve_tool_context
from app.core.exceptions import AppException
from app.schemas.project import ProjectUpdateRequest
from app.services.project_config_service import ProjectConfigService
from app.services.project_service import ProjectService


def build_project_style_config_tools(session_factory: async_sessionmaker[AsyncSession]) -> list[Any]:
    """构建项目样式上下文读取与规范更新工具列表。"""

    return [
        build_get_project_style_config_tool(session_factory),
        build_update_project_style_config_tool(session_factory),
    ]


def build_get_project_style_config_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建项目真实画布、主题摘要与样式规范读取工具。"""

    @agent_tool(show_result=False)
    async def get_project_style_config(run_context: AgentToolContext) -> dict[str, Any]:
        """读取当前项目的页面画布、主题摘要和样式规范。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=PROJECT_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id", "project_id"),
        )
        workspace_id = int(dependencies["workspace_id"])
        project_id = int(dependencies["project_id"])
        async with session_factory() as session:
            config_service = ProjectConfigService(session)
            project = await config_service.repository.get_by_id(project_id)
            if project is None:
                raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="项目不存在。")
            _ensure_project_workspace(project_workspace_id=project.workspace_id, expected_workspace_id=workspace_id)
            effective_theme_config = await config_service.resolve_runtime_theme_config(project)
            return {
                "page_width": project.page_width,
                "page_height": project.page_height,
                "base_font_size": project.base_font_size,
                "theme": _extract_theme_summary(effective_theme_config),
                "style_spec_markdown": project.style_spec_markdown,
            }

    return get_project_style_config


def build_update_project_style_config_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建需要用户确认的项目 Markdown 样式规范更新工具。"""

    @agent_tool(show_result=False, requires_confirmation=True)
    async def update_project_style_config(
        run_context: AgentToolContext,
        style_spec_markdown: str | None = None,
    ) -> dict[str, Any]:
        """更新当前项目 Markdown 样式规范；该写入会影响后续页面生成约束。"""

        if style_spec_markdown is None:
            raise AppException(
                status_code=400,
                code="AI_PROJECT_STYLE_CONFIG_REQUIRED",
                detail="修改项目样式规范时必须提供 style_spec_markdown。",
            )

        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=PROJECT_TOOL_WRITE_SCOPES,
            required_dependency_fields=("workspace_id", "project_id"),
        )
        workspace_id = int(dependencies["workspace_id"])
        project_id = int(dependencies["project_id"])
        operator_id = extract_user_id(str(claims.get("sub")))
        async with session_factory() as session:
            current_project = await ProjectConfigService(session).repository.get_by_id(project_id)
            if current_project is None:
                raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="项目不存在。")
            _ensure_project_workspace(
                project_workspace_id=current_project.workspace_id,
                expected_workspace_id=workspace_id,
            )
            try:
                payload = ProjectUpdateRequest(style_spec_markdown=style_spec_markdown)
            except ValidationError as exc:
                raise AppException(
                    status_code=400,
                    code="AI_PROJECT_STYLE_CONFIG_INVALID",
                    detail=f"项目样式配置参数不合法：{exc}",
                ) from exc
            updated = await ProjectService(session).update(project_id, payload, operator_id)
            return {
                "success": True,
                "message": "项目样式规范已更新。",
                "style_spec_markdown": updated.style_spec_markdown,
            }

    return update_project_style_config


def _extract_theme_summary(theme_config: dict[str, object]) -> dict[str, object]:
    """从当前生效主题配置中提取不含主题 key 的颜色与字体摘要。"""

    theme_entry = _resolve_current_theme_entry(theme_config)
    if theme_entry is None:
        return {"palette": {}, "typography": {}}
    palette = theme_entry.get("palette")
    typography = theme_entry.get("typography")
    return {
        "palette": palette if isinstance(palette, dict) else {},
        "typography": typography if isinstance(typography, dict) else {},
    }


def _resolve_current_theme_entry(theme_config: dict[str, object]) -> dict[str, object] | None:
    """按 Runtime 主题文档的 default.theme 或首个主题解析当前主题条目。"""

    if not isinstance(theme_config, dict):
        return None
    themes = theme_config.get("themes")
    if not isinstance(themes, dict) or not themes:
        return None
    default_section = theme_config.get("default")
    default_theme_key = str(default_section.get("theme") or "").strip() if isinstance(default_section, dict) else ""
    if default_theme_key:
        default_entry = themes.get(default_theme_key)
        if isinstance(default_entry, dict):
            return default_entry
    for theme_entry in themes.values():
        if isinstance(theme_entry, dict):
            return theme_entry
    return None


def _ensure_project_workspace(*, project_workspace_id: int, expected_workspace_id: int) -> None:
    """校验项目属于当前工作空间，避免跨工作空间读取或写入配置。"""

    if project_workspace_id != expected_workspace_id:
        raise AppException(
            status_code=403,
            code="AI_PROJECT_SCOPE_DENIED",
            detail="项目不属于当前工作空间，拒绝访问项目样式配置。",
        )
