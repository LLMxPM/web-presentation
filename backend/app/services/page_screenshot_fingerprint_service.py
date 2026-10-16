"""文件功能：生成页面截图配置指纹，统一判断截图是否匹配当前项目展示配置。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.platform_fonts import PLATFORM_FONT_REVISION
from app.core.runtime_module_policy import load_runtime_kit_manifest
from app.models.page import Page
from app.models.page_version import PageVersion
from app.models.workspace import Project
from app.schemas.project_app_config import ProjectAppPageConfig
from app.services.asset_binding_service import OWNER_KIND_PAGE_VERSION
from app.services.model3d_reference_collector import Model3dReferenceCollector
from app.services.project_config_service import ProjectConfigService


@dataclass(slots=True, frozen=True)
class PageScreenshotConfigSnapshot:
    """页面截图依赖的项目展示配置快照，附带已解析主题以便叠加页面级资源身份。"""

    page_config: ProjectAppPageConfig
    config_hash: str
    theme_key: str | None = None
    theme_config: dict[str, object] = field(default_factory=dict)


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
        """为指定页面生成当前项目展示配置快照，并叠加页面级三维引用身份。"""

        if page.project_id is None:
            base = PageScreenshotConfigSnapshot(
                page_config=ProjectAppPageConfig(),
                config_hash=self.build_hash(
                    page_config=ProjectAppPageConfig(),
                    theme_key=None,
                    theme_config={},
                ),
                theme_key=None,
                theme_config={},
            )
            return await self._with_page_model3d_identity(page, base)
        project = await self.project_config_service.get_active_project_or_raise(page.project_id)
        return await self._with_page_model3d_identity(page, await self.build_project_snapshot(project))

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
            theme_key=project.theme_key,
            theme_config=theme_config,
        )

    async def build_page_snapshot_from_project(
        self,
        page: Page,
        project_snapshot: PageScreenshotConfigSnapshot,
    ) -> PageScreenshotConfigSnapshot:
        """在已解析的项目配置快照上附加页面级三维引用身份，供批量刷新逐页复用。"""

        return await self._with_page_model3d_identity(page, project_snapshot)

    async def _with_page_model3d_identity(
        self,
        page: Page,
        base: PageScreenshotConfigSnapshot,
    ) -> PageScreenshotConfigSnapshot:
        """把页面绑定的三维资源实时身份并入 config hash；无三维引用时保持基础快照。"""

        model3d_tokens = await self._collect_page_model3d_tokens(page)
        if not model3d_tokens:
            return base
        return PageScreenshotConfigSnapshot(
            page_config=base.page_config,
            config_hash=self.build_hash(
                page_config=base.page_config,
                theme_key=base.theme_key,
                theme_config=base.theme_config,
                model3d_tokens=model3d_tokens,
            ),
            theme_key=base.theme_key,
            theme_config=base.theme_config,
        )

    async def _collect_page_model3d_tokens(self, page: Page) -> list[str]:
        """解析页面当前版本的绑定名集合到实时文件身份；旧版本无绑定时返回空。"""

        if page.workspace_id is None:
            return []
        version_id = await self.session.scalar(
            select(PageVersion.id)
            .where(PageVersion.page_id == page.id)
            .where(PageVersion.version_no == page.current_version_no)
        )
        if version_id is None:
            return []
        return await Model3dReferenceCollector(self.session).list_owner_live_asset_tokens(
            workspace_id=int(page.workspace_id),
            owner_kind=OWNER_KIND_PAGE_VERSION,
            owner_key=str(int(version_id)),
        )

    @classmethod
    def build_hash(
        cls,
        *,
        page_config: ProjectAppPageConfig,
        theme_key: str | None,
        theme_config: dict[str, object] | None,
        model3d_tokens: list[str] | None = None,
    ) -> str:
        """把截图相关配置序列化为稳定 SHA-256 指纹。

        ``model3d_tokens`` 为页面引用的三维资源实时身份；“三维引用身份 + 引擎身份”
        一并入指纹：资源替换或引擎策略变化后旧截图必须重新捕获。
        """

        payload = {
            "schema_version": cls.SCHEMA_VERSION,
            "platform_font_revision": PLATFORM_FONT_REVISION,
            "page": {
                "width": page_config.width,
                "height": page_config.height,
                "baseFontSize": page_config.baseFontSize,
                "iconDefaultStrokeWidth": page_config.iconDefaultStrokeWidth,
            },
            "theme_key": str(theme_key or "").strip() or None,
            "theme_config": cls._normalize_for_json(theme_config or {}),
        }
        normalized_tokens = sorted(str(token) for token in (model3d_tokens or []) if str(token or "").strip())
        if normalized_tokens:
            payload["model3d"] = {
                "references": normalized_tokens,
                "engine": cls._normalize_for_json(load_runtime_kit_manifest().get("model3d_engine") or {}),
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
