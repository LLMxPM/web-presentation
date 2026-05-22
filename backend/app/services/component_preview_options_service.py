"""文件功能：集中解析和校验组件预览页面与组件占位选项。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.workspace import Workspace
from app.schemas.component_preview_options import (
    ComponentPreviewOptions,
    build_default_component_preview_options,
)
from app.services.project_config_service import ProjectConfigService
from app.services.workspace_theme_service import WorkspaceThemeService


class ComponentPreviewOptionsService:
    """负责合成组件预览 artifact 的页面与占位选项。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.project_config_service = ProjectConfigService(session)
        self.workspace_theme_service = WorkspaceThemeService(session)

    async def resolve_options(
        self,
        workspace: Workspace,
        *option_values: object | None,
    ) -> ComponentPreviewOptions:
        """以工作空间默认主题为基线，叠加 manifest 或请求中的预览选项。"""

        merged_value: dict[str, Any] = build_default_component_preview_options(
            workspace.default_theme_key
        ).model_dump(mode="python")

        for option_value in option_values:
            normalized_value = self._normalize_option_value(option_value)
            if normalized_value:
                self._merge_dict(merged_value, normalized_value)

        try:
            options = ComponentPreviewOptions.model_validate(merged_value)
        except ValidationError as exc:
            raise AppException(
                status_code=400,
                code="COMPONENT_PREVIEW_OPTIONS_INVALID",
                detail=f"组件预览选项结构错误：{exc}",
            ) from exc

        await self._validate_page_theme(workspace.id, options)
        return options

    async def _validate_page_theme(self, workspace_id: int, options: ComponentPreviewOptions) -> None:
        """校验页面主题来源，并在无主题 key 时校验自定义 YAML。"""

        theme_key = str(options.page.theme_key or "").strip()
        theme_yaml = str(options.page.theme_config_yaml or "").strip()
        if theme_key:
            options.page.theme_key = await self.workspace_theme_service.ensure_theme_key_exists(workspace_id, theme_key)
            return

        if not theme_yaml:
            theme_yaml = self.project_config_service.get_default_templates()["themes"]
            options.page.theme_config_yaml = theme_yaml
        self.project_config_service.validate_yaml_text("themes", theme_yaml)

    @classmethod
    def _normalize_option_value(cls, option_value: object | None) -> dict[str, Any]:
        """将 Pydantic 模型或字典选项归一化为只包含显式字段的字典。"""

        if option_value is None:
            return {}
        if isinstance(option_value, BaseModel):
            source_value = option_value.model_dump(mode="python", exclude_unset=True)
        elif isinstance(option_value, dict):
            source_value = deepcopy(option_value)
        else:
            raise AppException(
                status_code=400,
                code="COMPONENT_PREVIEW_OPTIONS_INVALID",
                detail="组件预览选项必须是 JSON 对象。",
            )

        page_value = source_value.get("page")
        if isinstance(page_value, dict) and str(page_value.get("theme_config_yaml") or "").strip() and "theme_key" not in page_value:
            page_value["theme_key"] = None
        return source_value

    @classmethod
    def _merge_dict(cls, target: dict[str, Any], source: dict[str, Any]) -> None:
        """递归合并配置字典，保留未覆盖的默认值。"""

        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                cls._merge_dict(target[key], value)
                continue
            target[key] = value
