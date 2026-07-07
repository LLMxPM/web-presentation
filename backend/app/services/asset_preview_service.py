"""文件功能：为工作空间资源生成 Runtime 按需预览 artifact。"""

from __future__ import annotations

import uuid
from urllib.parse import urlencode

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.asset import WorkspaceAsset
from app.schemas.asset import resolve_asset_content_editable
from app.schemas.project_app_config import (
    DEFAULT_PROJECT_ICON,
    DEFAULT_PROJECT_MENU_MODE,
    DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON,
    build_project_app_config_document,
)
from app.schemas.release import PreviewArtifactResponse, PreviewEntryDescriptor
from app.services.asset_service import AssetService
from app.services.asset_manifest_metadata_service import build_asset_manifest_metadata
from app.services.component_preview_service import ComponentPreviewService
from app.services.preview_service import PreviewService
from app.services.project_config_service import ProjectConfigService
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.token_service import TokenService
from app.services.workspace_font_service import WorkspaceFontService

ASSET_PREVIEW_WIDTH = 1280
ASSET_PREVIEW_HEIGHT = 720


class AssetPreviewService:
    """资源预览服务，负责创建单资源 Runtime 预览 artifact。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.asset_service = AssetService(session)
        self.preview_service = PreviewService(session)
        self.component_preview_service = ComponentPreviewService(session)

    async def create_preview_artifact(
        self,
        *,
        workspace_id: int,
        asset_id: int,
        tenant_id: str,
    ) -> PreviewArtifactResponse:
        """为指定资源创建短生命周期预览 artifact。"""

        settings = get_settings()
        asset = await self.asset_service._get_asset_or_raise(workspace_id, asset_id)
        sandbox_project = await self.component_preview_service._ensure_workspace_preview_project(workspace_id)
        asset_base_url = f"{settings.backend_public_base_url.rstrip('/')}/public/assets/{workspace_id}"
        asset_mapping, asset_metadata = await self.preview_service._build_workspace_asset_mapping(workspace_id)
        self._append_asset_manifest_entry(asset_mapping, asset_metadata, asset)
        entry_descriptor = PreviewEntryDescriptor(entry_type="asset_host")
        entry_descriptor_payload = entry_descriptor.model_dump(mode="python", exclude_none=True)
        asset_preview_payload = self._build_asset_preview_payload(asset, asset_base_url)

        manifest = {
            "artifact_kind": "preview_artifact",
            "tenant_id": tenant_id,
            "preview_kind": "asset",
            "owner_scope": {
                "scope_type": "workspace_asset",
                "workspace_id": str(workspace_id),
                "asset_id": str(asset.id),
            },
            "entry_descriptor": entry_descriptor_payload,
            "asset_base_url": asset_base_url,
            "modules": {},
            "assets": asset_mapping,
            "asset_metadata": asset_metadata,
        }
        config_bundle = await self._build_config_bundle(
            workspace_id=workspace_id,
            asset=asset,
            asset_preview_payload=asset_preview_payload,
        )
        artifact_id = await RuntimeArtifactStore().put_artifact(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            project_id=sandbox_project.id,
            artifact_kind="preview_artifact",
            manifest=manifest,
            config_bundle=config_bundle,
            modules_data=[],
        )
        preview_token = TokenService.generate_preview_context_token(
            tenant_id=tenant_id,
            artifact_id=artifact_id,
            preview_kind="asset",
            scope_type="workspace_asset",
            workspace_id=workspace_id,
            entry_descriptor=entry_descriptor_payload,
            asset_base_url=asset_base_url,
            trace_id=f"req-{uuid.uuid4().hex[:8]}",
            asset_id=asset.id,
        )
        preview_url = (
            f"{settings.backend_public_base_url.rstrip('/')}/preview/artifacts/"
            f"{artifact_id}?{urlencode({'token': preview_token})}"
        )

        return PreviewArtifactResponse(
            preview_url=preview_url,
            artifact_id=artifact_id,
            preview_kind="asset",
            entry_descriptor=entry_descriptor,
            viewport_width=ASSET_PREVIEW_WIDTH,
            viewport_height=ASSET_PREVIEW_HEIGHT,
            workspace_id=workspace_id,
            asset_id=asset.id,
            asset_name=asset.name,
        )

    async def _build_config_bundle(
        self,
        *,
        workspace_id: int,
        asset: WorkspaceAsset,
        asset_preview_payload: dict[str, object],
    ) -> dict[str, object]:
        """构建资源预览宿主页所需的最小预加载配置。"""

        default_templates = ProjectConfigService.get_default_templates()
        theme_config = yaml.safe_load(default_templates["themes"] or "themes: {}") or {}
        font_bundle = await WorkspaceFontService(self.session).build_font_bundle_for_workspace(workspace_id)
        app_config = build_project_app_config_document(
            title=f"资源预览 - {asset.name}",
            description=asset.description,
            icon=DEFAULT_PROJECT_ICON,
            page_width=ASSET_PREVIEW_WIDTH,
            page_height=ASSET_PREVIEW_HEIGHT,
            show_pdf_export_button=DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON,
            menu_mode=DEFAULT_PROJECT_MENU_MODE,
        )
        return {
            "app": app_config.model_dump(mode="python"),
            "routes": {"routes": []},
            "icons": {"static_icons": []},
            "themes": theme_config,
            "fonts": font_bundle.model_dump(),
            "module_resolver": {},
            "asset_preview": asset_preview_payload,
        }

    @staticmethod
    def _append_asset_manifest_entry(
        asset_mapping: dict[str, str],
        asset_metadata: dict[str, dict[str, object]],
        asset: WorkspaceAsset,
    ) -> None:
        """确保当前资源即使是历史副本，也能在 manifest 中按 name 解析。"""

        asset_name = str(asset.name or "").strip()
        file_hash = str(asset.file_hash or "").strip()
        if not asset_name or not file_hash:
            return
        asset_mapping[asset_name] = file_hash
        asset_metadata[asset_name] = build_asset_manifest_metadata(asset)

    @staticmethod
    def _build_asset_preview_payload(asset: WorkspaceAsset, asset_base_url: str) -> dict[str, object]:
        """输出 Runtime 资源预览宿主页消费的资源配置。"""

        return {
            "asset_id": asset.id,
            "name": asset.name,
            "original_name": asset.original_name,
            "asset_type": asset.asset_type,
            "render_type": asset.asset_type,
            "content_type": asset.content_type,
            "url": f"{asset_base_url.rstrip('/')}/{asset.file_hash}",
            "content_editable": resolve_asset_content_editable(
                asset.asset_type,
                asset.original_name,
                asset.content_type,
            ),
            "file_hash": asset.file_hash,
        }
