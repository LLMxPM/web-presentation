"""文件功能：提供项目级 themes 配置模板校验、Runtime app 配置生成与动态图标配置输出能力。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.models.enums import RecordStatus
from app.models.page import Page
from app.models.workspace import Project
from app.repositories.project_repository import ProjectRepository
from app.schemas.project_app_config import (
    ProjectAppConfigDocument,
    ProjectAppPageConfig,
    build_project_app_config_document,
    dump_project_app_config_document_yaml,
    parse_project_app_config_document,
)
from app.services.project_route_service import ProjectRouteService
from app.services.runtime_icon_service import RuntimeIconService
from app.services.workspace_theme_service import WorkspaceThemeService

ProjectConfigName = Literal["app", "icons", "themes"]

PERSISTED_CONFIG_FIELD_MAP: dict[Literal["themes"], str] = {
    "themes": "theme_config_yaml",
}

CONFIG_FILE_MAP: dict[ProjectConfigName, str] = {
    "app": "app.config.yaml",
    "icons": "icons.config.yaml",
    "themes": "themes.config.yaml",
}


@lru_cache
def load_default_project_config_templates() -> dict[ProjectConfigName, str]:
    """读取项目初始化所需的默认 YAML 模板。"""

    runtime_config_root = Path(__file__).resolve().parents[3] / "runtime" / "public" / "config"
    templates: dict[ProjectConfigName, str] = {}
    for config_name, file_name in CONFIG_FILE_MAP.items():
        file_path = runtime_config_root / file_name
        if not file_path.is_file():
            raise RuntimeError(f"默认项目配置模板不存在：{file_path}")
        templates[config_name] = file_path.read_text(encoding="utf-8")
    return templates


class ProjectConfigService:
    """项目配置服务，负责模板填充、YAML 校验和运行时读取约束。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ProjectRepository(session)
        self.settings = get_settings()
        self.workspace_theme_service = WorkspaceThemeService(session)
        self.project_route_service = ProjectRouteService(session)
        self.runtime_icon_service = RuntimeIconService(session)

    def build_create_config_values(
        self,
        *,
        theme_config_yaml: str | None,
    ) -> dict[str, str]:
        """构建创建项目时的最终主题配置文本，缺省值自动回填默认模板。"""

        defaults = self.get_default_templates()
        resolved_values = {
            "theme_config_yaml": theme_config_yaml if theme_config_yaml is not None else defaults["themes"],
        }
        self.validate_config_values(**resolved_values)
        return resolved_values

    def validate_config_values(
        self,
        *,
        theme_config_yaml: str,
    ) -> None:
        """统一校验项目中持久化的 YAML 配置文本均为可解析对象。"""

        self.validate_yaml_text("themes", theme_config_yaml)

    def validate_yaml_text(self, config_name: ProjectConfigName, yaml_text: str) -> None:
        """校验单份 YAML 文本非空且语法可解析。"""

        self._ensure_yaml_not_blank(config_name, yaml_text)

        try:
            parsed_value = yaml.safe_load(yaml_text)
        except yaml.YAMLError as exc:
            raise AppException(
                status_code=400,
                code="PROJECT_CONFIG_INVALID_YAML",
                detail=f"{CONFIG_FILE_MAP[config_name]} YAML 语法错误：{exc}",
            ) from exc

        if config_name == "app":
            parse_project_app_config_document(yaml_text)

    async def get_config_text(self, project_id: int, config_name: ProjectConfigName) -> str:
        """读取指定项目的单份运行时配置，仅允许启用中的项目访问。"""

        project = await self.get_active_project_or_raise(project_id)
        if config_name == "app":
            return await self.build_runtime_app_yaml(project)
        if config_name == "icons":
            runtime_theme_config = await self.resolve_runtime_theme_config(project)
            runtime_route_config = await self.project_route_service.build_runtime_route_config(project.id)
            pages = await self._list_project_pages(project.id)
            icon_config = await self.runtime_icon_service.build_project_icon_config(
                workspace_id=project.workspace_id,
                project_icon_name=self.resolve_project_icon_name_from_theme_config(runtime_theme_config),
                runtime_route_config=runtime_route_config,
                pages=pages,
            )
            return yaml.safe_dump(icon_config, allow_unicode=True, sort_keys=False)
        if config_name == "themes":
            runtime_theme_config = await self.resolve_runtime_theme_config(project)
            return yaml.safe_dump(runtime_theme_config, allow_unicode=True, sort_keys=False)

        field_name = PERSISTED_CONFIG_FIELD_MAP[config_name]
        config_text = getattr(project, field_name, None)
        if not str(config_text or "").strip():
            raise AppException(
                status_code=409,
                code="PROJECT_CONFIG_MISSING",
                detail=f"项目缺少 {CONFIG_FILE_MAP[config_name]} 配置。",
            )
        return str(config_text)

    async def ensure_runtime_configs_ready(self, project_id: int) -> Project:
        """校验项目处于启用状态且必需配置已存在，可用于预览与构建。"""

        project = await self.get_active_project_or_raise(project_id)
        for config_name, field_name in PERSISTED_CONFIG_FIELD_MAP.items():
            if config_name == "themes" and str(project.theme_key or "").strip():
                continue
            if not str(getattr(project, field_name, None) or "").strip():
                raise AppException(
                    status_code=409,
                    code="PROJECT_CONFIG_MISSING",
                    detail=f"项目缺少 {CONFIG_FILE_MAP[config_name]} 配置，无法继续运行时操作。",
                )
        return project

    async def _list_project_pages(self, project_id: int) -> list[Page]:
        """读取项目下全部启用页面，供 Runtime 图标配置动态生成使用。"""

        return list(
            (
                await self.session.execute(
                    select(Page)
                    .where(Page.project_id == project_id)
                    .where(Page.status == RecordStatus.ACTIVE.value)
                )
            ).scalars()
        )

    async def get_project_config_base_url(self, project_id: int) -> str:
        """返回项目运行时配置根地址，并在生成前确认该项目可供运行时读取。"""

        await self.ensure_runtime_configs_ready(project_id)
        public_base_url = self.settings.backend_public_base_url.strip().rstrip("/")
        if not public_base_url:
            raise AppException(
                status_code=500,
                code="BACKEND_PUBLIC_BASE_URL_MISSING",
                detail="Backend 未配置 BACKEND_PUBLIC_BASE_URL。",
            )
        return f"{public_base_url}/api/runtime/projects/{project_id}/configs"

    async def get_active_project_or_raise(self, project_id: int) -> Project:
        """读取启用中的项目，不存在或不可用时统一抛错。"""

        project = await self.repository.get_by_id(project_id)
        if project is None:
            raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="项目不存在。")
        if project.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=409, code="PROJECT_NOT_ACTIVE", detail="当前项目未启用，无法提供运行时配置。")
        return project

    @staticmethod
    def get_default_templates() -> dict[ProjectConfigName, str]:
        """公开默认模板读取入口，供 CRUD、迁移与测试统一复用。"""

        try:
            return load_default_project_config_templates()
        except RuntimeError as exc:
            raise AppException(status_code=500, code="PROJECT_CONFIG_TEMPLATE_MISSING", detail=str(exc)) from exc

    async def build_runtime_app_document(
        self,
        project: Project,
        *,
        theme_config: dict[str, object] | None = None,
    ) -> ProjectAppConfigDocument:
        """根据项目结构化字段和主题图标生成 Runtime 使用的 app 配置文档。"""

        resolved_theme_config = theme_config if theme_config is not None else await self.resolve_runtime_theme_config(project)
        return build_project_app_config_document(
            title=project.name,
            description=project.description,
            icon=self.resolve_project_icon_name_from_theme_config(resolved_theme_config),
            page_width=project.page_width,
            page_height=project.page_height,
            base_font_size=project.base_font_size,
            icon_default_stroke_width=project.icon_default_stroke_width,
            show_pdf_export_button=project.show_pdf_export_button,
            menu_mode=project.menu_mode,
        )

    async def build_runtime_app_dict(
        self,
        project: Project,
        *,
        theme_config: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """输出供预览配置包直接复用的项目 app 配置对象。"""

        return (await self.build_runtime_app_document(project, theme_config=theme_config)).model_dump(mode="python")

    async def build_runtime_app_yaml(
        self,
        project: Project,
        *,
        theme_config: dict[str, object] | None = None,
    ) -> str:
        """输出 Runtime 拉取的项目 app 配置 YAML 文本。"""

        return dump_project_app_config_document_yaml(await self.build_runtime_app_document(project, theme_config=theme_config))

    @staticmethod
    def resolve_project_page_config(project: Project) -> ProjectAppPageConfig:
        """从项目结构化字段解析页面画布尺寸。"""

        return ProjectAppPageConfig(
            width=project.page_width,
            height=project.page_height,
            baseFontSize=project.base_font_size,
            iconDefaultStrokeWidth=project.icon_default_stroke_width,
        )

    async def resolve_runtime_theme_config(self, project: Project) -> dict[str, object]:
        """解析项目当前生效的主题配置对象，优先使用主题库。"""

        if str(project.theme_key or "").strip():
            return await self.workspace_theme_service.build_theme_config_document_by_key(project.workspace_id, project.theme_key)
        return yaml.safe_load(project.theme_config_yaml or "themes: {}") or {}

    async def resolve_project_icon_name(self, project: Project, *, theme_config: dict[str, object] | None = None) -> str | None:
        """解析项目在当前主题下的图标名称。"""

        resolved_theme_config = theme_config if theme_config is not None else await self.resolve_runtime_theme_config(project)
        return self.resolve_project_icon_name_from_theme_config(resolved_theme_config)

    @staticmethod
    def resolve_project_icon_name_from_theme_config(theme_config: dict[str, object] | None) -> str | None:
        """从 themes.config 对象中提取默认主题声明的项目图标。"""

        if not isinstance(theme_config, dict):
            return None

        themes = theme_config.get("themes")
        if not isinstance(themes, dict) or not themes:
            return None

        default_theme_key = ""
        default_section = theme_config.get("default")
        if isinstance(default_section, dict):
            default_theme_key = str(default_section.get("theme") or "").strip()
        if not default_theme_key:
            default_theme_key = next(iter(themes.keys()), "")
        theme_entry = themes.get(default_theme_key)
        if not isinstance(theme_entry, dict):
            return None

        app_section = theme_entry.get("app")
        if not isinstance(app_section, dict):
            return None
        icon_name = str(app_section.get("icon") or "").strip()
        return icon_name or None

    @staticmethod
    def _ensure_yaml_not_blank(config_name: ProjectConfigName, yaml_text: str) -> None:
        """统一校验 YAML 原文非空，避免 comment-only 或空字符串混入。"""

        if not str(yaml_text or "").strip():
            raise AppException(
                status_code=400,
                code="PROJECT_CONFIG_REQUIRED",
                detail=f"{CONFIG_FILE_MAP[config_name]} 不能为空。",
            )
