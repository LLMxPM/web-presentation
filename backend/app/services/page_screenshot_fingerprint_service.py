"""文件功能：生成页面截图配置指纹，统一判断截图是否匹配当前项目展示配置。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.page import Page
from app.models.workspace import Project
from app.schemas.project_app_config import ProjectAppPageConfig
from app.services.project_config_service import ProjectConfigService


@dataclass(slots=True, frozen=True)
class PageScreenshotConfigSnapshot:
    """页面截图依赖的项目展示配置快照。"""

    page_config: ProjectAppPageConfig
    config_hash: str


class PageScreenshotFingerprintService:
    """截图指纹服务，负责把影响截图渲染的项目配置压缩成稳定 hash。"""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        session: AsyncSession,
        project_config_service: ProjectConfigService | None = None,
    ) -> None:
        self.session = session
        self.project_config_service = project_config_service or ProjectConfigService(session)

    async def build_page_snapshot(self, page: Page) -> PageScreenshotConfigSnapshot:
        """为指定页面生成当前项目展示配置快照。"""

        if page.project_id is None:
            page_config = ProjectAppPageConfig()
            return PageScreenshotConfigSnapshot(
                page_config=page_config,
                config_hash=self.build_hash(
                    page_config=page_config,
                    theme_key=None,
                    theme_config={},
                ),
            )

        project = await self.project_config_service.get_active_project_or_raise(page.project_id)
        return await self.build_project_snapshot(project)

    async def build_project_snapshot(self, project: Project) -> PageScreenshotConfigSnapshot:
        """为项目生成当前展示配置快照。"""

        page_config = self.project_config_service.resolve_project_page_config(project)
        theme_config = await self.project_config_service.resolve_runtime_theme_config(project)
        return PageScreenshotConfigSnapshot(
            page_config=page_config,
            config_hash=self.build_hash(
                page_config=page_config,
                theme_key=project.theme_key,
                theme_config=theme_config,
            ),
        )

    @classmethod
    def build_hash(
        cls,
        *,
        page_config: ProjectAppPageConfig,
        theme_key: str | None,
        theme_config: dict[str, object] | None,
    ) -> str:
        """把截图相关配置序列化为稳定 SHA-256 指纹。"""

        payload = {
            "schema_version": cls.SCHEMA_VERSION,
            "page": {
                "width": page_config.width,
                "height": page_config.height,
                "baseFontSize": page_config.baseFontSize,
                "iconDefaultStrokeWidth": page_config.iconDefaultStrokeWidth,
            },
            "theme_key": str(theme_key or "").strip() or None,
            "theme_config": cls._normalize_for_json(theme_config or {}),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _normalize_for_json(cls, value: Any) -> Any:
        """递归归一化对象，确保相同语义配置生成相同 JSON。"""

        if isinstance(value, dict):
            return {str(key): cls._normalize_for_json(value[key]) for key in sorted(value.keys(), key=str)}
        if isinstance(value, list):
            return [cls._normalize_for_json(item) for item in value]
        if isinstance(value, tuple):
            return [cls._normalize_for_json(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)
