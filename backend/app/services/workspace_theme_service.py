"""文件功能：管理工作空间主题库、主题引用校验与 Runtime 主题文档组装。"""

from __future__ import annotations

from copy import deepcopy

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType
from app.models.font import WorkspaceFontConfig
from app.models.workspace import Project, Workspace
from app.models.workspace_theme import WorkspaceTheme
from app.repositories.workspace_repository import WorkspaceRepository
from app.repositories.workspace_theme_repository import WorkspaceThemeRepository
from app.schemas.common import ListQuery, PagedResponse
from app.schemas.theme import (
    ThemePalette,
    WorkspaceThemeAssetSummary,
    WorkspaceThemeCopyRequest,
    WorkspaceThemeCreateRequest,
    WorkspaceThemeItem,
    WorkspaceThemeUpdateRequest,
)

DEFAULT_THEME_KEY = "lightblue"
DEFAULT_THEME_NAME = "白底蓝色"
DEFAULT_THEME_DESCRIPTION = "白底蓝色主题，简约经典"
DEFAULT_THEME_LOGO_PATH = None
DEFAULT_THEME_INVERT_LOGO_PATH = None
DEFAULT_THEME_PROJECT_ICON_NAME = None
DEFAULT_THEME_HEADING_FONT = "思源黑体"
DEFAULT_THEME_BODY_FONT = "思源黑体"
DEFAULT_THEME_CODE_FONT = "SourceCodePro"
DEFAULT_THEME_PALETTE = ThemePalette.model_validate(
    {
        "text": {
            "primary": "#0D286A",
            "secondary": "#1D5297",
            "invert": "#ffffff",
        },
        "background": {
            "default": "#ffffff",
            "invert": "#0D286A",
        },
        "border": {
            "default": "#e5e7eb",
            "subtle": "#d1d5db",
        },
        "link": {
            "default": "#3b82f6",
            "hover": "#2563eb",
            "visited": "#7c3aed",
        },
        "accent": [
            "#0D286A",
            "#260E6D",
            "#9E8403",
            "#9E6B03",
            "#A110AB",
            "#C5003C",
        ],
    }
)


class WorkspaceThemeService:
    """工作空间主题服务，负责主题主数据管理与引用解析。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspace_repository = WorkspaceRepository(session)
        self.theme_repository = WorkspaceThemeRepository(session)

    async def list(self, workspace_id: int, query: ListQuery) -> PagedResponse[WorkspaceThemeItem]:
        """查询工作空间主题列表。"""

        await self._get_workspace_or_raise(workspace_id)
        items, total = await self.theme_repository.list(workspace_id, query)
        return PagedResponse[WorkspaceThemeItem](
            items=[await self._to_item(item) for item in items],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    async def get(self, workspace_id: int, theme_id: int) -> WorkspaceThemeItem:
        """获取单个工作空间主题。"""

        theme = await self._get_theme_or_raise(workspace_id, theme_id)
        return await self._to_item(theme)

    async def create(
        self,
        workspace_id: int,
        payload: WorkspaceThemeCreateRequest,
        operator_id: int,
    ) -> WorkspaceThemeItem:
        """创建工作空间主题。"""

        await self._get_workspace_or_raise(workspace_id)
        await self._ensure_theme_key_available(workspace_id, payload.key)
        resolved_payload = await self._resolve_theme_payload(workspace_id, payload)
        theme = WorkspaceTheme(
            workspace_id=workspace_id,
            key=payload.key,
            name=payload.name,
            description=payload.description,
            logo_asset_id=resolved_payload["logo_asset_id"],
            invert_logo_asset_id=resolved_payload["invert_logo_asset_id"],
            project_icon_asset_id=resolved_payload["project_icon_asset_id"],
            logo_path=resolved_payload["logo_path"],
            invert_logo_path=resolved_payload["invert_logo_path"],
            project_icon_name=resolved_payload["project_icon_name"],
            heading_font_id=resolved_payload["heading_font_id"],
            body_font_id=resolved_payload["body_font_id"],
            code_font_id=resolved_payload["code_font_id"],
            heading_font_label=resolved_payload["heading_font_label"],
            body_font_label=resolved_payload["body_font_label"],
            code_font_label=resolved_payload["code_font_label"],
            palette=payload.palette.model_dump(mode="python"),
            created_by=operator_id,
            updated_by=operator_id,
        )
        await self.theme_repository.create(theme)
        await self.session.commit()
        return await self.get(workspace_id, theme.id)

    async def copy(
        self,
        workspace_id: int,
        theme_id: int,
        payload: WorkspaceThemeCopyRequest,
        operator_id: int,
    ) -> WorkspaceThemeItem:
        """复制工作空间主题，并自动生成不冲突的 key。"""

        source_theme = await self._get_theme_or_raise(workspace_id, theme_id)
        next_key = await self._build_available_key(workspace_id, payload.key or f"{source_theme.key}_copy")
        next_name = payload.name or f"{source_theme.name}（副本）"
        copied_theme = WorkspaceTheme(
            workspace_id=workspace_id,
            key=next_key,
            name=next_name,
            description=source_theme.description,
            logo_asset_id=source_theme.logo_asset_id,
            invert_logo_asset_id=source_theme.invert_logo_asset_id,
            project_icon_asset_id=source_theme.project_icon_asset_id,
            logo_path=source_theme.logo_path,
            invert_logo_path=source_theme.invert_logo_path,
            project_icon_name=source_theme.project_icon_name,
            heading_font_id=source_theme.heading_font_id,
            body_font_id=source_theme.body_font_id,
            code_font_id=source_theme.code_font_id,
            heading_font_label=source_theme.heading_font_label,
            body_font_label=source_theme.body_font_label,
            code_font_label=source_theme.code_font_label,
            palette=deepcopy(dict(source_theme.palette)),
            created_by=operator_id,
            updated_by=operator_id,
        )
        await self.theme_repository.create(copied_theme)
        await self.session.commit()
        return await self.get(workspace_id, copied_theme.id)

    async def update(
        self,
        workspace_id: int,
        theme_id: int,
        payload: WorkspaceThemeUpdateRequest,
        operator_id: int,
    ) -> WorkspaceThemeItem:
        """更新工作空间主题，并在 key 变更时同步引用方。"""

        theme = await self._get_theme_or_raise(workspace_id, theme_id)
        original_key = theme.key

        next_key = payload.key or theme.key
        if next_key != theme.key:
            await self._ensure_theme_key_available(workspace_id, next_key, exclude_theme_id=theme.id)

        resolved_payload = await self._resolve_theme_payload(workspace_id, payload, current_theme=theme)
        theme.key = next_key
        if "name" in payload.model_fields_set and payload.name is not None:
            theme.name = payload.name
        if "description" in payload.model_fields_set:
            theme.description = payload.description
        theme.logo_asset_id = resolved_payload["logo_asset_id"]
        theme.invert_logo_asset_id = resolved_payload["invert_logo_asset_id"]
        theme.project_icon_asset_id = resolved_payload["project_icon_asset_id"]
        theme.logo_path = resolved_payload["logo_path"]
        theme.invert_logo_path = resolved_payload["invert_logo_path"]
        theme.project_icon_name = resolved_payload["project_icon_name"]
        theme.heading_font_id = resolved_payload["heading_font_id"]
        theme.body_font_id = resolved_payload["body_font_id"]
        theme.code_font_id = resolved_payload["code_font_id"]
        theme.heading_font_label = resolved_payload["heading_font_label"]
        theme.body_font_label = resolved_payload["body_font_label"]
        theme.code_font_label = resolved_payload["code_font_label"]
        if "palette" in payload.model_fields_set and payload.palette is not None:
            theme.palette = payload.palette.model_dump(mode="python")
        theme.updated_by = operator_id

        if next_key != original_key:
            await self._cascade_theme_key_change(workspace_id, original_key, next_key)

        await self.session.commit()
        return await self.get(workspace_id, theme.id)

    async def delete(self, workspace_id: int, theme_id: int) -> None:
        """硬删除工作空间主题；若仍被引用则拒绝删除。"""

        theme = await self._get_theme_or_raise(workspace_id, theme_id)
        await self.assert_theme_can_delete(workspace_id, theme.key)
        await self.session.delete(theme)
        await self.session.commit()

    async def create_default_theme_for_workspace(self, workspace: Workspace, operator_id: int | None = None) -> WorkspaceTheme:
        """为工作空间补齐系统默认主题，并在缺失默认 key 时回写工作空间。"""

        existing_theme = await self.theme_repository.get_by_key(workspace.id, DEFAULT_THEME_KEY)
        if existing_theme is not None:
            if workspace.default_theme_key != existing_theme.key:
                workspace.default_theme_key = existing_theme.key
                workspace.updated_by = operator_id
                await self.session.flush()
            return existing_theme

        theme = WorkspaceTheme(
            workspace_id=workspace.id,
            key=DEFAULT_THEME_KEY,
            name=DEFAULT_THEME_NAME,
            description=DEFAULT_THEME_DESCRIPTION,
            logo_asset_id=None,
            invert_logo_asset_id=None,
            project_icon_asset_id=None,
            logo_path=DEFAULT_THEME_LOGO_PATH,
            invert_logo_path=DEFAULT_THEME_INVERT_LOGO_PATH,
            project_icon_name=DEFAULT_THEME_PROJECT_ICON_NAME,
            heading_font_id=None,
            body_font_id=None,
            code_font_id=None,
            heading_font_label=DEFAULT_THEME_HEADING_FONT,
            body_font_label=DEFAULT_THEME_BODY_FONT,
            code_font_label=DEFAULT_THEME_CODE_FONT,
            palette=DEFAULT_THEME_PALETTE.model_dump(mode="python"),
            created_by=operator_id,
            updated_by=operator_id,
        )
        await self.theme_repository.create(theme)
        workspace.default_theme_key = theme.key
        workspace.updated_by = operator_id
        await self.session.flush()
        return theme

    async def ensure_theme_key_exists(self, workspace_id: int, theme_key: str | None) -> str | None:
        """校验主题 key 在工作空间内存在；空值原样返回。"""

        normalized_key = str(theme_key or "").strip()
        if not normalized_key:
            return None
        if await self.theme_repository.get_by_key(workspace_id, normalized_key) is None:
            raise AppException(status_code=400, code="WORKSPACE_THEME_NOT_FOUND", detail="目标主题不存在。")
        return normalized_key

    async def build_theme_config_document_by_key(self, workspace_id: int, theme_key: str) -> dict[str, object]:
        """按主题 key 组装 Runtime 消费的主题配置对象。"""

        theme = await self.theme_repository.get_by_key(workspace_id, theme_key)
        if theme is None:
            raise AppException(status_code=400, code="WORKSPACE_THEME_NOT_FOUND", detail="目标主题不存在。")
        return await self.build_theme_config_document(theme)

    async def build_theme_config_document(self, theme: WorkspaceTheme) -> dict[str, object]:
        """将主题实体组装为 Runtime 兼容的 themes.config 对象。"""

        logo_asset, invert_logo_asset, project_icon_asset, heading_font, body_font, code_font = await self._load_theme_relations(theme)
        heading_font_asset_name = await self._resolve_runtime_font_asset_name(theme.workspace_id, heading_font)
        body_font_asset_name = await self._resolve_runtime_font_asset_name(theme.workspace_id, body_font)
        code_font_asset_name = await self._resolve_runtime_font_asset_name(theme.workspace_id, code_font)
        theme_entry = {
            "name": theme.name,
            "description": theme.description or "",
            "palette": dict(theme.palette),
            "typography": {
                "headingfont": heading_font_asset_name if heading_font_asset_name else theme.heading_font_label,
                "bodyfont": body_font_asset_name if body_font_asset_name else theme.body_font_label,
                "codefont": code_font_asset_name if code_font_asset_name else theme.code_font_label,
            },
        }
        logo_path = logo_asset.name if logo_asset is not None else theme.logo_path
        invert_logo_path = invert_logo_asset.name if invert_logo_asset is not None else theme.invert_logo_path
        project_icon_name = project_icon_asset.name if project_icon_asset is not None else theme.project_icon_name
        if logo_path:
            theme_entry["logo"] = logo_path
        if invert_logo_path:
            theme_entry["invertLogo"] = invert_logo_path
        if project_icon_name:
            theme_entry["app"] = {"icon": project_icon_name}

        return {
            "themes": {
                theme.key: theme_entry,
            },
            "default": {
                "theme": theme.key,
            },
        }

    async def build_theme_config_yaml_by_key(self, workspace_id: int, theme_key: str) -> str:
        """按主题 key 返回 YAML 文本。"""

        document = await self.build_theme_config_document_by_key(workspace_id, theme_key)
        return yaml.safe_dump(document, allow_unicode=True, sort_keys=False)

    async def list_theme_font_asset_names(self, workspace_id: int) -> list[str]:
        """收集工作空间全部主题最终会输出的字体资产名。"""

        theme_items = await self.theme_repository.list_by_workspace(workspace_id)
        font_names: list[str] = []
        for theme in theme_items:
            _, _, _, heading_font, body_font, code_font = await self._load_theme_relations(theme)
            for font_item in (heading_font, body_font, code_font):
                runtime_asset_name = await self._resolve_runtime_font_asset_name(workspace_id, font_item)
                if runtime_asset_name and runtime_asset_name not in font_names:
                    font_names.append(runtime_asset_name)
        return font_names

    async def list_theme_font_reference_tokens(self, workspace_id: int) -> list[str]:
        """收集工作空间全部主题最终会输出的字体引用 token。"""

        theme_items = await self.theme_repository.list_by_workspace(workspace_id)
        reference_tokens: list[str] = []
        for theme in theme_items:
            logo_asset, invert_logo_asset, project_icon_asset, heading_font, body_font, code_font = await self._load_theme_relations(theme)
            del logo_asset, invert_logo_asset, project_icon_asset
            for token in await self._build_theme_font_reference_tokens(
                workspace_id=workspace_id,
                heading_font=heading_font,
                body_font=body_font,
                code_font=code_font,
            ):
                if token not in reference_tokens:
                    reference_tokens.append(token)
        return reference_tokens

    async def get_theme_font_asset_names_by_key(self, workspace_id: int, theme_key: str) -> list[str]:
        """收集单个主题最终会输出的字体资产名。"""

        theme = await self.theme_repository.get_by_key(workspace_id, theme_key)
        if theme is None:
            raise AppException(status_code=400, code="WORKSPACE_THEME_NOT_FOUND", detail="目标主题不存在。")

        _, _, _, heading_font, body_font, code_font = await self._load_theme_relations(theme)
        font_names: list[str] = []
        for font_item in (heading_font, body_font, code_font):
            runtime_asset_name = await self._resolve_runtime_font_asset_name(workspace_id, font_item)
            if runtime_asset_name and runtime_asset_name not in font_names:
                font_names.append(runtime_asset_name)
        return font_names

    async def get_theme_font_reference_tokens_by_key(self, workspace_id: int, theme_key: str) -> list[str]:
        """收集单个主题最终会输出的字体引用 token。"""

        theme = await self.theme_repository.get_by_key(workspace_id, theme_key)
        if theme is None:
            raise AppException(status_code=400, code="WORKSPACE_THEME_NOT_FOUND", detail="目标主题不存在。")

        _, _, _, heading_font, body_font, code_font = await self._load_theme_relations(theme)
        return await self._build_theme_font_reference_tokens(
            workspace_id=workspace_id,
            heading_font=heading_font,
            body_font=body_font,
            code_font=code_font,
        )

    async def get_project_icon_name_by_key(self, workspace_id: int, theme_key: str | None) -> str | None:
        """根据主题 key 解析当前主题下的项目图标名称。"""

        normalized_key = str(theme_key or "").strip()
        if not normalized_key:
            return None

        theme = await self.theme_repository.get_by_key(workspace_id, normalized_key)
        if theme is None:
            raise AppException(status_code=400, code="WORKSPACE_THEME_NOT_FOUND", detail="目标主题不存在。")

        project_icon_asset = await self._get_theme_project_icon_asset_or_none(workspace_id, theme.project_icon_asset_id)
        return project_icon_asset.name if project_icon_asset is not None else str(theme.project_icon_name or "").strip() or None

    async def is_asset_referenced(self, workspace_id: int, asset_id: int) -> bool:
        """判断资产是否被任意主题引用为 logo 或项目图标。"""

        total = await self.session.scalar(
            select(WorkspaceTheme.id)
            .where(
                (WorkspaceTheme.logo_asset_id == asset_id)
                | (WorkspaceTheme.invert_logo_asset_id == asset_id)
                | (WorkspaceTheme.project_icon_asset_id == asset_id)
            )
            .limit(1)
        )
        return total is not None

    async def is_font_referenced(self, workspace_id: int, font_id: int) -> bool:
        """判断字体配置是否被任意可见主题引用。"""

        total = await self.session.scalar(
            select(WorkspaceTheme.id)
            .where(WorkspaceTheme.workspace_id == workspace_id)
            .where(WorkspaceTheme.deleted_at.is_(None))
            .where(
                (WorkspaceTheme.heading_font_id == font_id)
                | (WorkspaceTheme.body_font_id == font_id)
                | (WorkspaceTheme.code_font_id == font_id)
            )
            .limit(1)
        )
        return total is not None

    async def purge_soft_deleted_theme_font_references(self, workspace_id: int, font_id: int) -> None:
        """硬删除旧软删除主题，释放历史数据中残留的字体外键。"""

        stmt = (
            select(WorkspaceTheme)
            .where(WorkspaceTheme.workspace_id == workspace_id)
            .where(WorkspaceTheme.deleted_at.is_not(None))
            .where(
                (WorkspaceTheme.heading_font_id == font_id)
                | (WorkspaceTheme.body_font_id == font_id)
                | (WorkspaceTheme.code_font_id == font_id)
            )
        )
        for theme in (await self.session.execute(stmt)).scalars().all():
            await self.session.delete(theme)
        await self.session.flush()

    async def assert_theme_can_delete(self, workspace_id: int, theme_key: str) -> None:
        """校验主题未被工作空间默认配置或项目引用。"""

        workspace = await self._get_workspace_or_raise(workspace_id)
        if workspace.default_theme_key == theme_key:
            raise AppException(
                status_code=409,
                code="WORKSPACE_THEME_IN_USE",
                detail="该主题仍被工作空间默认主题引用，无法删除。",
            )

        project_id = await self.session.scalar(
            select(Project.id)
            .where(Project.workspace_id == workspace_id)
            .where(Project.deleted_at.is_(None))
            .where(Project.theme_key == theme_key)
            .limit(1)
        )
        if project_id is not None:
            raise AppException(
                status_code=409,
                code="WORKSPACE_THEME_IN_USE",
                detail="该主题仍被项目配置引用，无法删除。",
            )

    async def _to_item(self, theme: WorkspaceTheme) -> WorkspaceThemeItem:
        """将主题实体转换为接口响应。"""

        logo_asset, invert_logo_asset, project_icon_asset, heading_font, body_font, code_font = await self._load_theme_relations(theme)
        return WorkspaceThemeItem.model_validate(
            {
                "id": theme.id,
                "workspace_id": theme.workspace_id,
                "key": theme.key,
                "name": theme.name,
                "description": theme.description,
                "logo_asset_id": theme.logo_asset_id,
                "invert_logo_asset_id": theme.invert_logo_asset_id,
                "project_icon_asset_id": theme.project_icon_asset_id,
                "project_icon_name": project_icon_asset.name if project_icon_asset is not None else theme.project_icon_name,
                "heading_font_id": theme.heading_font_id,
                "body_font_id": theme.body_font_id,
                "code_font_id": theme.code_font_id,
                "heading_font_label": theme.heading_font_label,
                "body_font_label": theme.body_font_label,
                "code_font_label": theme.code_font_label,
                "palette": theme.palette,
                "logo_asset": self._build_asset_summary(theme.workspace_id, logo_asset),
                "invert_logo_asset": self._build_asset_summary(theme.workspace_id, invert_logo_asset),
                "project_icon_asset": self._build_asset_summary(theme.workspace_id, project_icon_asset),
                "heading_font": heading_font,
                "body_font": body_font,
                "code_font": code_font,
                "resolved_theme_config_yaml": yaml.safe_dump(
                    await self.build_theme_config_document(theme),
                    allow_unicode=True,
                    sort_keys=False,
                ),
                "created_at": theme.created_at,
                "updated_at": theme.updated_at,
                "created_by": theme.created_by,
                "updated_by": theme.updated_by,
            }
        )

    async def _get_workspace_or_raise(self, workspace_id: int) -> Workspace:
        """读取工作空间，不存在时抛出标准错误。"""

        workspace = await self.workspace_repository.get_by_id(workspace_id)
        if workspace is None:
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="工作空间不存在。")
        return workspace

    async def _get_theme_or_raise(self, workspace_id: int, theme_id: int) -> WorkspaceTheme:
        """读取主题实体，不存在时抛错。"""

        theme = await self.theme_repository.get_by_id(workspace_id, theme_id)
        if theme is None:
            raise AppException(status_code=404, code="WORKSPACE_THEME_NOT_FOUND", detail="主题不存在。")
        return theme

    async def _ensure_theme_key_available(
        self,
        workspace_id: int,
        key: str,
        *,
        exclude_theme_id: int | None = None,
    ) -> None:
        """确保主题 key 在工作空间内唯一。"""

        existing_theme = await self.theme_repository.get_by_key(workspace_id, key)
        if existing_theme is not None and existing_theme.id != exclude_theme_id:
            raise AppException(status_code=409, code="WORKSPACE_THEME_KEY_DUPLICATE", detail="主题 key 已存在。")

    async def _resolve_theme_payload(
        self,
        workspace_id: int,
        payload: WorkspaceThemeCreateRequest | WorkspaceThemeUpdateRequest,
        *,
        current_theme: WorkspaceTheme | None = None,
    ) -> dict[str, object]:
        """解析主题请求中的资源引用并补齐回退字段。"""

        payload_fields = getattr(payload, "model_fields_set", set())
        logo_asset_id = self._resolve_optional_update_field(payload_fields, "logo_asset_id", payload.logo_asset_id, current_theme.logo_asset_id if current_theme else None)
        invert_logo_asset_id = self._resolve_optional_update_field(
            payload_fields,
            "invert_logo_asset_id",
            payload.invert_logo_asset_id,
            current_theme.invert_logo_asset_id if current_theme else None,
        )
        project_icon_asset_id = self._resolve_optional_update_field(
            payload_fields,
            "project_icon_asset_id",
            payload.project_icon_asset_id,
            current_theme.project_icon_asset_id if current_theme else None,
        )
        heading_font_id = self._resolve_optional_update_field(
            payload_fields,
            "heading_font_id",
            payload.heading_font_id,
            current_theme.heading_font_id if current_theme else None,
        )
        body_font_id = self._resolve_optional_update_field(
            payload_fields,
            "body_font_id",
            payload.body_font_id,
            current_theme.body_font_id if current_theme else None,
        )
        code_font_id = self._resolve_optional_update_field(
            payload_fields,
            "code_font_id",
            payload.code_font_id,
            current_theme.code_font_id if current_theme else None,
        )

        logo_asset = await self._get_theme_logo_asset_or_none(workspace_id, logo_asset_id)
        invert_logo_asset = await self._get_theme_logo_asset_or_none(workspace_id, invert_logo_asset_id)
        project_icon_asset = await self._get_theme_project_icon_asset_or_none(workspace_id, project_icon_asset_id)
        heading_font = await self._get_workspace_font_or_none(workspace_id, heading_font_id)
        body_font = await self._get_workspace_font_or_none(workspace_id, body_font_id)
        code_font = await self._get_workspace_font_or_none(workspace_id, code_font_id)

        return {
            "logo_asset_id": logo_asset.id if logo_asset is not None else None,
            "invert_logo_asset_id": invert_logo_asset.id if invert_logo_asset is not None else None,
            "project_icon_asset_id": project_icon_asset.id if project_icon_asset is not None else None,
            "logo_path": logo_asset.name if logo_asset is not None else current_theme.logo_path if current_theme else None,
            "invert_logo_path": (
                invert_logo_asset.name if invert_logo_asset is not None else current_theme.invert_logo_path if current_theme else None
            ),
            "project_icon_name": (
                project_icon_asset.name
                if project_icon_asset is not None
                else current_theme.project_icon_name if current_theme else DEFAULT_THEME_PROJECT_ICON_NAME
            ),
            "heading_font_id": heading_font.id if heading_font is not None else None,
            "body_font_id": body_font.id if body_font is not None else None,
            "code_font_id": code_font.id if code_font is not None else None,
            "heading_font_label": heading_font.font_family if heading_font is not None else current_theme.heading_font_label if current_theme else DEFAULT_THEME_HEADING_FONT,
            "body_font_label": body_font.font_family if body_font is not None else current_theme.body_font_label if current_theme else DEFAULT_THEME_BODY_FONT,
            "code_font_label": code_font.font_family if code_font is not None else current_theme.code_font_label if current_theme else DEFAULT_THEME_CODE_FONT,
        }

    async def _get_theme_logo_asset_or_none(self, workspace_id: int, asset_id: int | None) -> WorkspaceAsset | None:
        """读取可用于主题 logo 的资产。"""

        if asset_id is None:
            return None

        asset = await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.id == asset_id)
        )
        if asset is None:
            raise AppException(status_code=400, code="WORKSPACE_THEME_ASSET_NOT_FOUND", detail="主题引用的 logo 资产不存在。")
        if asset.asset_type not in {AssetType.ICON.value, AssetType.IMAGE.value}:
            raise AppException(status_code=400, code="WORKSPACE_THEME_ASSET_INVALID", detail="主题 logo 仅支持图标或图片资源。")
        return asset

    async def _get_theme_project_icon_asset_or_none(self, workspace_id: int, asset_id: int | None) -> WorkspaceAsset | None:
        """读取可用于主题项目图标的资产，仅允许 icon 类型。"""

        if asset_id is None:
            return None

        asset = await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.id == asset_id)
        )
        if asset is None:
            raise AppException(status_code=400, code="WORKSPACE_THEME_ASSET_NOT_FOUND", detail="主题引用的项目图标资产不存在。")
        if asset.asset_type != AssetType.ICON.value:
            raise AppException(status_code=400, code="WORKSPACE_THEME_ASSET_INVALID", detail="主题项目图标仅支持 icon 资源。")
        return asset

    async def _get_workspace_font_or_none(self, workspace_id: int, font_id: int | None) -> WorkspaceFontConfig | None:
        """读取工作空间字体配置。"""

        if font_id is None:
            return None

        font_config = await self.session.scalar(
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.id == font_id)
        )
        if font_config is None:
            raise AppException(status_code=400, code="WORKSPACE_THEME_FONT_NOT_FOUND", detail="主题引用的字体配置不存在。")
        return font_config

    async def _load_theme_relations(
        self,
        theme: WorkspaceTheme,
    ) -> tuple[WorkspaceAsset | None, WorkspaceAsset | None, WorkspaceAsset | None, WorkspaceFontConfig | None, WorkspaceFontConfig | None, WorkspaceFontConfig | None]:
        """批量读取主题的资源和字体引用。"""

        logo_asset = await self._get_theme_logo_asset_or_none(theme.workspace_id, theme.logo_asset_id)
        invert_logo_asset = await self._get_theme_logo_asset_or_none(theme.workspace_id, theme.invert_logo_asset_id)
        project_icon_asset = await self._get_theme_project_icon_asset_or_none(theme.workspace_id, theme.project_icon_asset_id)
        heading_font = await self._get_workspace_font_or_none(theme.workspace_id, theme.heading_font_id)
        body_font = await self._get_workspace_font_or_none(theme.workspace_id, theme.body_font_id)
        code_font = await self._get_workspace_font_or_none(theme.workspace_id, theme.code_font_id)
        return logo_asset, invert_logo_asset, project_icon_asset, heading_font, body_font, code_font

    async def _build_available_key(self, workspace_id: int, requested_key: str) -> str:
        """为复制场景生成不冲突的主题 key。"""

        normalized_key = str(requested_key or "").strip()
        if not normalized_key:
            normalized_key = f"{DEFAULT_THEME_KEY}_copy"

        if await self.theme_repository.get_by_key(workspace_id, normalized_key) is None:
            return normalized_key

        index = 2
        while True:
            candidate_key = f"{normalized_key}{index}"
            if await self.theme_repository.get_by_key(workspace_id, candidate_key) is None:
                return candidate_key
            index += 1

    async def _cascade_theme_key_change(self, workspace_id: int, old_key: str, new_key: str) -> None:
        """当主题 key 修改时，同步更新工作空间与项目引用。"""

        workspace = await self._get_workspace_or_raise(workspace_id)
        if workspace.default_theme_key == old_key:
            workspace.default_theme_key = new_key

        project_items = (
            await self.session.execute(
                select(Project)
                .where(Project.workspace_id == workspace_id)
                .where(Project.deleted_at.is_(None))
                .where(Project.theme_key == old_key)
            )
        ).scalars().all()
        for project in project_items:
            project.theme_key = new_key

    @staticmethod
    def _build_asset_summary(workspace_id: int, asset: WorkspaceAsset | None) -> WorkspaceThemeAssetSummary | None:
        """将主题关联资产转换为响应摘要。"""

        if asset is None:
            return None

        from app.core.config import get_settings

        settings = get_settings()
        return WorkspaceThemeAssetSummary.model_validate(
            {
                "id": asset.id,
                "name": asset.name,
                "original_name": asset.original_name,
                "asset_type": asset.asset_type,
                "analysis_metadata": asset.analysis_metadata,
                "url": f"{settings.backend_public_base_url.rstrip('/')}/public/assets/{workspace_id}/{asset.file_hash}",
            }
        )

    @staticmethod
    def _resolve_optional_update_field(
        payload_fields: set[str],
        field_name: str,
        field_value: int | None,
        current_value: int | None,
    ) -> int | None:
        """根据字段是否显式传入，解析更新请求中的可空引用字段。"""

        if payload_fields and field_name not in payload_fields:
            return current_value
        return field_value

    async def _resolve_runtime_font_asset_name(
        self,
        workspace_id: int,
        font_config: WorkspaceFontConfig | None,
    ) -> str | None:
        """解析主题运行时应输出的字体资源逻辑名，优先以资产表当前 name 为准。"""

        if font_config is None:
            return None

        asset = await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.id == font_config.asset_id)
        )
        runtime_asset_name = str(asset.name if asset is not None and asset.name else "").strip()
        recorded_asset_name = str(font_config.asset_name or "").strip()
        if not runtime_asset_name:
            raise AppException(
                status_code=409,
                code="FONT_ASSET_NAME_MISSING",
                detail=f'字体配置 "{recorded_asset_name or font_config.id}" 缺少对应资产逻辑名，无法生成主题配置。',
            )
        if recorded_asset_name != runtime_asset_name:
            raise AppException(
                status_code=409,
                code="FONT_ASSET_NAME_MISMATCH",
                detail=(
                    f'字体配置记录的 asset_name="{recorded_asset_name}" 与资产当前 name="{runtime_asset_name}" 不一致，'
                    "请先修正字体配置数据后再继续。"
                ),
            )
        return runtime_asset_name

    async def _build_theme_font_reference_tokens(
        self,
        *,
        workspace_id: int,
        heading_font: WorkspaceFontConfig | None,
        body_font: WorkspaceFontConfig | None,
        code_font: WorkspaceFontConfig | None,
    ) -> list[str]:
        """把主题显式绑定的字体资源名展开为 token 列表。"""

        heading_font_token = await self._resolve_runtime_font_asset_name(workspace_id, heading_font)
        body_font_token = await self._resolve_runtime_font_asset_name(workspace_id, body_font)
        code_font_token = await self._resolve_runtime_font_asset_name(workspace_id, code_font)
        reference_tokens: list[str] = []
        for token in (heading_font_token, body_font_token, code_font_token):
            normalized_token = str(token or "").strip()
            if normalized_token and normalized_token not in reference_tokens:
                reference_tokens.append(normalized_token)
        return reference_tokens
