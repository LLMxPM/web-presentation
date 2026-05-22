"""文件功能：定义智能体可调用的页面与组件代码检查工具。"""

from __future__ import annotations

from typing import Any

from agno.run import RunContext
from agno.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import CODE_CHECK_TOOL_SCOPES, COMPONENT_TOOL_READ_SCOPES, PAGE_TOOL_READ_SCOPES
from app.ai.tools.shared import (
    SourceEditInput,
    allow_preview_schema_object_parameter,
    normalize_preview_schema_argument,
    resolve_tool_context,
)
from app.core.exceptions import AppException
from app.models.enums import WorkspaceComponentType
from app.services.code_check_service import CodeCheckService


def build_check_page_code_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建页面源码只读检查工具。"""

    @tool(show_result=False)
    async def check_page_code(
        run_context: RunContext,
        page_id: int | None = None,
        content: str | None = None,
        edits: list[SourceEditInput] | None = None,
    ) -> dict[str, Any]:
        """检查当前页面、指定页面或结构化 edits 应用后的候选页面源码是否能被 Runtime 编译。"""

        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=(*PAGE_TOOL_READ_SCOPES, *CODE_CHECK_TOOL_SCOPES),
            required_dependency_fields=("workspace_id",),
        )
        target_page_id = page_id if page_id is not None else dependencies.get("page_id")
        target_project_id = dependencies.get("project_id")
        if target_page_id is None and content is None:
            raise AppException(status_code=400, code="PAGE_ID_REQUIRED", detail="缺少 page_id，无法检查页面代码。")
        async with session_factory() as session:
            return await CodeCheckService(session).check_page_code(
                page_id=int(target_page_id) if target_page_id is not None else None,
                project_id=int(target_project_id) if target_project_id is not None else None,
                workspace_id=int(dependencies["workspace_id"]),
                user_id=_extract_user_id(claims),
                content=content,
                edits=edits,
            )

    return check_page_code


def build_check_component_code_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建组件源码只读检查工具。"""

    @tool(show_result=False)
    async def check_component_code(
        run_context: RunContext,
        component_id: int | None = None,
        content: str | None = None,
        edits: list[SourceEditInput] | None = None,
        preview_schema: str | dict[str, Any] | None = None,
        component_type: WorkspaceComponentType | None = None,
    ) -> dict[str, Any]:
        """检查当前组件、指定组件或结构化 edits 应用后的候选组件源码是否能被 Runtime 编译。"""

        _ = component_type
        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=(*COMPONENT_TOOL_READ_SCOPES, *CODE_CHECK_TOOL_SCOPES),
            required_dependency_fields=("workspace_id",),
        )
        target_component_id = component_id if component_id is not None else dependencies.get("component_id")
        async with session_factory() as session:
            return await CodeCheckService(session).check_component_code(
                component_id=int(target_component_id) if target_component_id is not None else None,
                workspace_id=int(dependencies["workspace_id"]),
                user_id=_extract_user_id(claims),
                content=content,
                edits=edits,
                preview_schema=normalize_preview_schema_argument(preview_schema),
            )

    allow_preview_schema_object_parameter(check_component_code)
    return check_component_code


def _extract_user_id(claims: dict[str, Any]) -> str:
    """从工具令牌 claims 中提取用户 ID，用于标记临时 artifact 租户。"""

    subject = str(claims.get("sub") or "system")
    return subject.split(":", maxsplit=1)[1] if subject.startswith("user:") else subject
