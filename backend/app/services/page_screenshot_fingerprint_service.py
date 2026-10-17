"""文件功能：生成页面截图配置指纹，统一判断截图是否匹配当前项目展示配置与资源身份。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
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
from app.services.owner_resource_token_resolver import OwnerResourceTokenResolver, OwnerResourceTokens
from app.services.project_config_service import ProjectConfigService


@dataclass(slots=True, frozen=True)
class PageScreenshotConfigSnapshot:
    """页面截图依赖的项目展示配置快照，附带已解析主题以便叠加页面级资源身份。"""

    page_config: ProjectAppPageConfig
    config_hash: str
    theme_key: str | None = None
    theme_config: dict[str, object] = field(default_factory=dict)


class PageScreenshotFingerprintService:
    """截图指纹服务，负责把影响截图渲染的项目配置与引用资源身份压缩成稳定 hash。"""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        session: AsyncSession,
        project_config_service: ProjectConfigService | None = None,
    ) -> None:
        self.session = session
        self.project_config_service = project_config_service or ProjectConfigService(session)

    async def build_page_snapshot(self, page: Page) -> PageScreenshotConfigSnapshot:
        """为指定页面生成当前项目展示配置快照，并叠加页面级资源实时身份。"""

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
            return await self._with_page_resource_identity(page, base)
        project = await self.project_config_service.get_active_project_or_raise(page.project_id)
        return await self._with_page_resource_identity(page, await self.build_project_snapshot(project))

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
        """在已解析的项目配置快照上附加页面级资源身份，供批量刷新逐页复用。"""

        return await self._with_page_resource_identity(page, project_snapshot)

    async def build_page_snapshots_from_project(
        self,
        pages: Sequence[Page],
        project_snapshot: PageScreenshotConfigSnapshot,
    ) -> dict[int, PageScreenshotConfigSnapshot]:
        """批量附加页面级资源实时身份；版本与资源各按层批量查询，避免逐页 N+1。"""

        if not pages:
            return {}
        page_ids = [int(page.id) for page in pages]
        version_rows = (
            await self.session.execute(
                select(PageVersion.page_id, PageVersion.id, PageVersion.version_no)
                .where(PageVersion.page_id.in_(page_ids))
            )
        ).all()
        version_id_by_page_key = {
            (int(row.page_id), int(row.version_no)): int(row.id)
            for row in version_rows
        }
        workspace_id = int(pages[0].workspace_id) if pages[0].workspace_id is not None else None
        if workspace_id is None:
            return {int(page.id): project_snapshot for page in pages}
        owner_version_ids = [
            version_id
            for page in pages
            if (version_id := version_id_by_page_key.get((int(page.id), int(page.current_version_no)))) is not None
        ]
        resolved_map = await OwnerResourceTokenResolver(self.session).resolve_page_version_tokens_bulk(
            workspace_id=workspace_id,
            page_version_ids=owner_version_ids,
        )
        snapshots: dict[int, PageScreenshotConfigSnapshot] = {}
        for page in pages:
            version_id = version_id_by_page_key.get((int(page.id), int(page.current_version_no)))
            resource_tokens = (
                resolved_map.get(version_id, OwnerResourceTokens())
                if version_id is not None
                else OwnerResourceTokens()
            )
            snapshots[int(page.id)] = self._apply_resource_tokens(project_snapshot, resource_tokens)
        return snapshots

    async def _with_page_resource_identity(
        self,
        page: Page,
        base: PageScreenshotConfigSnapshot,
    ) -> PageScreenshotConfigSnapshot:
        """把页面引用资源的实时身份并入 config hash；无资源引用时保持基础快照。"""

        resource_tokens = await self._collect_page_resource_tokens(page)
        return self._apply_resource_tokens(base, resource_tokens)

    def _apply_resource_tokens(
        self,
        base: PageScreenshotConfigSnapshot,
        resource_tokens: OwnerResourceTokens,
    ) -> PageScreenshotConfigSnapshot:
        """把已解析的资源身份 token 并入基础快照；空 token 直接返回基础快照。"""

        if not resource_tokens.tokens:
            return base
        return PageScreenshotConfigSnapshot(
            page_config=base.page_config,
            config_hash=self.build_hash(
                page_config=base.page_config,
                theme_key=base.theme_key,
                theme_config=base.theme_config,
                resource_tokens=resource_tokens.tokens,
                has_model3d=resource_tokens.has_model3d,
            ),
            theme_key=base.theme_key,
            theme_config=base.theme_config,
        )

    async def _collect_page_resource_tokens(self, page: Page) -> OwnerResourceTokens:
        """解析页面当前版本闭包的资源实时身份；无版本或无引用时返回空。"""

        if page.workspace_id is None:
            return OwnerResourceTokens()
        version_id = await self.session.scalar(
            select(PageVersion.id)
            .where(PageVersion.page_id == page.id)
            .where(PageVersion.version_no == page.current_version_no)
        )
        if version_id is None:
            return OwnerResourceTokens()
        return await OwnerResourceTokenResolver(self.session).resolve_page_version_tokens(
            workspace_id=int(page.workspace_id),
            page_version_id=int(version_id),
        )

    @classmethod
    def build_hash(
        cls,
        *,
        page_config: ProjectAppPageConfig,
        theme_key: str | None,
        theme_config: dict[str, object] | None,
        resource_tokens: list[str] | None = None,
        has_model3d: bool = False,
    ) -> str:
        """把截图相关配置序列化为稳定 SHA-256 指纹。

        ``resource_tokens`` 为页面引用资源的实时身份（含三维）：资源替换后旧截图必须重新捕获；
        三维引擎身份随三维引用一并入指纹，引擎策略变化同样要求重截。
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
        normalized_tokens = sorted(str(token) for token in (resource_tokens or []) if str(token or "").strip())
        if normalized_tokens:
            payload["resources"] = normalized_tokens
        if has_model3d:
            payload["model3d"] = {
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
