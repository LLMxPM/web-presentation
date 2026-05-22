"""文件功能：管理工作空间样式库，提供可复用项目展示配置与样式规范模板。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.workspace import Workspace
from app.models.workspace_style import WorkspaceStyle
from app.repositories.workspace_repository import WorkspaceRepository
from app.repositories.workspace_style_repository import WorkspaceStyleRepository
from app.schemas.common import ListQuery, PagedResponse
from app.schemas.project_app_config import (
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PAGE_WIDTH,
    DEFAULT_PROJECT_BASE_FONT_SIZE,
    DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH,
    DEFAULT_PROJECT_MENU_MODE,
    DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON,
    DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN,
)
from app.schemas.workspace_style import (
    WorkspaceStyleCopyRequest,
    WorkspaceStyleCreateRequest,
    WorkspaceStyleItem,
    WorkspaceStyleUpdateRequest,
)
from app.services.workspace_theme_service import WorkspaceThemeService

DEFAULT_WORKSPACE_STYLE_KEY = "default"
DEFAULT_WORKSPACE_STYLE_NAME = "默认样式"
DEFAULT_WORKSPACE_STYLE_DESCRIPTION = "系统默认项目展示样式。"


class WorkspaceStyleService:
    """工作空间样式服务，负责样式 CRUD、复制和主题引用校验。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspace_repository = WorkspaceRepository(session)
        self.style_repository = WorkspaceStyleRepository(session)
        self.workspace_theme_service = WorkspaceThemeService(session)

    async def list(self, workspace_id: int, query: ListQuery) -> PagedResponse[WorkspaceStyleItem]:
        """查询工作空间样式列表。"""

        await self._get_workspace_or_raise(workspace_id)
        items, total = await self.style_repository.list(workspace_id, query)
        return PagedResponse[WorkspaceStyleItem](
            items=[self._to_item(item) for item in items],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    async def get(self, workspace_id: int, style_id: int) -> WorkspaceStyleItem:
        """获取单个工作空间样式。"""

        return self._to_item(await self._get_style_or_raise(workspace_id, style_id))

    async def get_by_key(self, workspace_id: int, key: str) -> WorkspaceStyleItem:
        """按 key 获取单个工作空间样式。"""

        await self._get_workspace_or_raise(workspace_id)
        normalized_key = str(key or "").strip().lower()
        style = await self.style_repository.get_by_key(workspace_id, normalized_key)
        if style is None:
            raise AppException(status_code=404, code="WORKSPACE_STYLE_NOT_FOUND", detail="样式不存在。")
        return self._to_item(style)

    async def create(
        self,
        workspace_id: int,
        payload: WorkspaceStyleCreateRequest,
        operator_id: int,
    ) -> WorkspaceStyleItem:
        """创建工作空间样式。"""

        await self._get_workspace_or_raise(workspace_id)
        await self._ensure_style_key_available(workspace_id, payload.key)
        resolved_theme_key = await self._resolve_theme_key(workspace_id, payload.theme_key)
        style = WorkspaceStyle(
            workspace_id=workspace_id,
            key=payload.key,
            name=payload.name,
            description=payload.description,
            page_width=payload.page_width,
            page_height=payload.page_height,
            base_font_size=payload.base_font_size,
            icon_default_stroke_width=payload.icon_default_stroke_width,
            show_pdf_export_button=payload.show_pdf_export_button,
            menu_mode=payload.menu_mode,
            theme_key=resolved_theme_key,
            style_spec_markdown=payload.style_spec_markdown,
            created_by=operator_id,
            updated_by=operator_id,
        )
        await self.style_repository.create(style)
        await self.session.commit()
        return await self.get(workspace_id, style.id)

    async def copy(
        self,
        workspace_id: int,
        style_id: int,
        payload: WorkspaceStyleCopyRequest,
        operator_id: int,
    ) -> WorkspaceStyleItem:
        """复制工作空间样式，并自动生成不冲突的 key。"""

        source_style = await self._get_style_or_raise(workspace_id, style_id)
        next_key = await self._build_available_key(workspace_id, payload.key or f"{source_style.key}_copy")
        copied_style = WorkspaceStyle(
            workspace_id=workspace_id,
            key=next_key,
            name=payload.name or f"{source_style.name}（副本）",
            description=source_style.description,
            page_width=source_style.page_width,
            page_height=source_style.page_height,
            base_font_size=source_style.base_font_size,
            icon_default_stroke_width=source_style.icon_default_stroke_width,
            show_pdf_export_button=source_style.show_pdf_export_button,
            menu_mode=source_style.menu_mode,
            theme_key=source_style.theme_key,
            style_spec_markdown=source_style.style_spec_markdown,
            created_by=operator_id,
            updated_by=operator_id,
        )
        await self.style_repository.create(copied_style)
        await self.session.commit()
        return await self.get(workspace_id, copied_style.id)

    async def update(
        self,
        workspace_id: int,
        style_id: int,
        payload: WorkspaceStyleUpdateRequest,
        operator_id: int,
    ) -> WorkspaceStyleItem:
        """更新工作空间样式；不会影响已经复制到项目中的配置。"""

        style = await self._get_style_or_raise(workspace_id, style_id)
        payload_fields = payload.model_fields_set

        if "key" in payload_fields and payload.key is not None and payload.key != style.key:
            await self._ensure_style_key_available(workspace_id, payload.key, exclude_style_id=style.id)
            style.key = payload.key
        if "name" in payload_fields and payload.name is not None:
            style.name = payload.name
        if "description" in payload_fields:
            style.description = payload.description
        if "page_width" in payload_fields and payload.page_width is not None:
            style.page_width = payload.page_width
        if "page_height" in payload_fields and payload.page_height is not None:
            style.page_height = payload.page_height
        if "base_font_size" in payload_fields and payload.base_font_size is not None:
            style.base_font_size = payload.base_font_size
        if "icon_default_stroke_width" in payload_fields and payload.icon_default_stroke_width is not None:
            style.icon_default_stroke_width = payload.icon_default_stroke_width
        if "show_pdf_export_button" in payload_fields and payload.show_pdf_export_button is not None:
            style.show_pdf_export_button = payload.show_pdf_export_button
        if "menu_mode" in payload_fields and payload.menu_mode is not None:
            style.menu_mode = payload.menu_mode
        if "theme_key" in payload_fields:
            style.theme_key = await self._resolve_theme_key(workspace_id, payload.theme_key)
        if "style_spec_markdown" in payload_fields:
            style.style_spec_markdown = payload.style_spec_markdown or ""

        style.updated_by = operator_id
        await self.session.commit()
        return await self.get(workspace_id, style.id)

    async def delete(self, workspace_id: int, style_id: int) -> None:
        """删除工作空间样式；样式不与项目关联，因此可直接硬删除。"""

        style = await self._get_style_or_raise(workspace_id, style_id)
        await self.session.delete(style)
        await self.session.commit()

    async def create_default_style_for_workspace(self, workspace: Workspace, operator_id: int | None = None) -> WorkspaceStyle:
        """为新工作空间补齐默认样式，便于项目创建时直接套用。"""

        existing_style = await self.style_repository.get_by_key(workspace.id, DEFAULT_WORKSPACE_STYLE_KEY)
        if existing_style is not None:
            return existing_style
        style = WorkspaceStyle(
            workspace_id=workspace.id,
            key=DEFAULT_WORKSPACE_STYLE_KEY,
            name=DEFAULT_WORKSPACE_STYLE_NAME,
            description=DEFAULT_WORKSPACE_STYLE_DESCRIPTION,
            page_width=DEFAULT_PAGE_WIDTH,
            page_height=DEFAULT_PAGE_HEIGHT,
            base_font_size=DEFAULT_PROJECT_BASE_FONT_SIZE,
            icon_default_stroke_width=DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH,
            show_pdf_export_button=DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON,
            menu_mode=DEFAULT_PROJECT_MENU_MODE,
            theme_key=workspace.default_theme_key,
            style_spec_markdown=DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN,
            created_by=operator_id,
            updated_by=operator_id,
        )
        await self.style_repository.create(style)
        await self.session.flush()
        return style

    @staticmethod
    def _to_item(style: WorkspaceStyle) -> WorkspaceStyleItem:
        """将样式实体转换为接口响应。"""

        return WorkspaceStyleItem.model_validate(
            {
                "id": style.id,
                "workspace_id": style.workspace_id,
                "key": style.key,
                "name": style.name,
                "description": style.description,
                "page_width": style.page_width,
                "page_height": style.page_height,
                "base_font_size": style.base_font_size,
                "icon_default_stroke_width": style.icon_default_stroke_width,
                "show_pdf_export_button": style.show_pdf_export_button,
                "menu_mode": style.menu_mode,
                "theme_key": style.theme_key,
                "style_spec_markdown": style.style_spec_markdown,
                "created_at": style.created_at,
                "updated_at": style.updated_at,
                "created_by": style.created_by,
                "updated_by": style.updated_by,
            }
        )

    async def _get_workspace_or_raise(self, workspace_id: int) -> Workspace:
        """读取工作空间，不存在时抛出标准错误。"""

        workspace = await self.workspace_repository.get_by_id(workspace_id)
        if workspace is None:
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="工作空间不存在。")
        return workspace

    async def _get_style_or_raise(self, workspace_id: int, style_id: int) -> WorkspaceStyle:
        """读取样式实体，不存在时抛错。"""

        style = await self.style_repository.get_by_id(workspace_id, style_id)
        if style is None:
            raise AppException(status_code=404, code="WORKSPACE_STYLE_NOT_FOUND", detail="样式不存在。")
        return style

    async def _ensure_style_key_available(
        self,
        workspace_id: int,
        key: str,
        *,
        exclude_style_id: int | None = None,
    ) -> None:
        """确保样式 key 在工作空间内唯一。"""

        existing_style = await self.style_repository.get_by_key(workspace_id, key)
        if existing_style is not None and existing_style.id != exclude_style_id:
            raise AppException(status_code=409, code="WORKSPACE_STYLE_KEY_DUPLICATE", detail="样式 key 已存在。")

    async def _resolve_theme_key(self, workspace_id: int, theme_key: str | None) -> str | None:
        """校验样式引用的主题 key；空值表示应用样式时不覆盖项目主题。"""

        return await self.workspace_theme_service.ensure_theme_key_exists(workspace_id, theme_key)

    async def _build_available_key(self, workspace_id: int, base_key: str) -> str:
        """基于候选 key 生成当前工作空间内可用的样式 key。"""

        normalized_base = str(base_key or DEFAULT_WORKSPACE_STYLE_KEY).strip().lower()[:64]
        if await self.style_repository.get_by_key(workspace_id, normalized_base) is None:
            return normalized_base

        prefix = normalized_base[:55].rstrip("_-") or DEFAULT_WORKSPACE_STYLE_KEY
        index = 2
        while True:
            candidate = f"{prefix}_{index}"
            if await self.style_repository.get_by_key(workspace_id, candidate) is None:
                return candidate
            index += 1
