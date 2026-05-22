"""文件功能：管理无状态预览 artifact 的构建、持久化与签名地址生成。"""

from __future__ import annotations

import uuid
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.page import Page
from app.services.project_artifact_builder import AssetDeliveryMode, ProjectArtifactBuilder, ProjectPageModuleOverride
from app.schemas.release import PreviewArtifactResponse, PreviewEntryDescriptor
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.token_service import TokenService


class PreviewService:
    """项目/页面预览服务，负责构建短生命周期 preview artifact。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.artifact_builder = ProjectArtifactBuilder(session)

    async def create_preview_artifact(
        self,
        *,
        project_id: int,
        entry_descriptor: PreviewEntryDescriptor | None,
        tenant_id: str,
        page_module_overrides: dict[str, ProjectPageModuleOverride] | None = None,
        transient_pages: list[Page] | None = None,
        asset_delivery_mode: AssetDeliveryMode = "public",
    ) -> PreviewArtifactResponse:
        """基于项目当前状态创建无状态预览 artifact，并返回带签名的预览入口。"""

        settings = get_settings()
        snapshot = await self.artifact_builder.build_snapshot(
            project_id=project_id,
            entry_descriptor=entry_descriptor,
            page_module_overrides=page_module_overrides,
            transient_pages=transient_pages,
            asset_delivery_mode=asset_delivery_mode,
        )
        entry_descriptor_payload = snapshot.entry_descriptor.model_dump(mode="python", exclude_none=True)

        manifest = {
            "artifact_kind": "preview_artifact",
            "tenant_id": tenant_id,
            "preview_kind": snapshot.preview_kind,
            "owner_scope": {
                "scope_type": "project",
                "project_id": str(project_id),
                "workspace_id": str(snapshot.project.workspace_id),
            },
            "entry_descriptor": entry_descriptor_payload,
            "asset_base_url": snapshot.asset_base_url,
            "modules": snapshot.modules_metadata,
            "assets": snapshot.asset_mapping,
            "asset_metadata": snapshot.asset_metadata,
        }
        artifact_id = await RuntimeArtifactStore().put_artifact(
            tenant_id=tenant_id,
            workspace_id=snapshot.project.workspace_id,
            project_id=project_id,
            artifact_kind="preview_artifact",
            manifest=manifest,
            config_bundle=snapshot.config_bundle,
            modules_data=snapshot.modules_data,
        )
        preview_token = TokenService.generate_preview_context_token(
            tenant_id=tenant_id,
            artifact_id=artifact_id,
            preview_kind=snapshot.preview_kind,
            scope_type="project",
            workspace_id=snapshot.project.workspace_id,
            project_id=project_id,
            entry_descriptor=entry_descriptor_payload,
            asset_base_url=snapshot.asset_base_url,
            trace_id=f"req-{uuid.uuid4().hex[:8]}",
        )
        preview_url = (
            f"{settings.backend_public_base_url.rstrip('/')}/preview/artifacts/"
            f"{artifact_id}?{urlencode({'token': preview_token})}"
        )

        return PreviewArtifactResponse(
            preview_url=preview_url,
            artifact_id=artifact_id,
            preview_kind=snapshot.preview_kind,
            entry_descriptor=snapshot.entry_descriptor,
            viewport_width=snapshot.page_config.width,
            viewport_height=snapshot.page_config.height,
            project_id=project_id,
            workspace_id=snapshot.project.workspace_id,
        )

    async def _build_workspace_asset_mapping(
        self,
        workspace_id: int,
    ) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
        """构建 preview manifest 的资源映射与资源渲染元数据。"""

        return await self.artifact_builder.build_workspace_asset_snapshot(workspace_id)

    async def _build_release_module_graph(
        self,
        pages: list[Page],
        *,
        manifest_page_paths: set[str] | None = None,
    ) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
        """按页面入口递归收集页面与组件版本的完整模块图。"""

        return await self.artifact_builder.build_release_module_graph(
            pages,
            manifest_page_paths=manifest_page_paths,
        )

    @staticmethod
    def _append_release_module(
        *,
        modules_metadata: dict[str, dict[str, str]],
        modules_data_by_path: dict[str, dict[str, str]],
        logical_path: str,
        content: str,
        include_in_manifest: bool,
    ) -> None:
        """将一个逻辑模块快照追加到 release_modules，并按需登记到 manifest。"""

        ProjectArtifactBuilder.append_release_module(
            modules_metadata=modules_metadata,
            modules_data_by_path=modules_data_by_path,
            logical_path=logical_path,
            content=content,
            include_in_manifest=include_in_manifest,
        )

    @staticmethod
    def _build_component_logical_path(component_code: str, version_no: int) -> str:
        """将组件编码和版本号转为 Release 中的逻辑模块路径。"""

        return ProjectArtifactBuilder.build_component_logical_path(component_code, version_no)

    @staticmethod
    def _collect_runtime_route_component_paths(runtime_route_config: dict[str, list[dict[str, object]]]) -> set[str]:
        """收集运行时路由配置中实际引用的页面组件别名路径。"""

        return ProjectArtifactBuilder.collect_runtime_route_component_paths(runtime_route_config)

    @staticmethod
    def _resolve_direct_entry_page(all_project_pages: list[Page], module_path: str) -> Page | None:
        """根据单页面预览入口解析目标页面；非页面模块入口时返回空。"""

        return ProjectArtifactBuilder.resolve_direct_entry_page(all_project_pages, module_path)

    @staticmethod
    def _normalize_direct_entry_module_path(module_path: str) -> str:
        """将单页面预览入口统一规范化为 `src/views/*.vue` 形式。"""

        return ProjectArtifactBuilder.normalize_direct_entry_module_path(module_path)

    @staticmethod
    def _merge_preview_root_pages(route_pages: list[Page], standalone_entry_page: Page | None) -> list[Page]:
        """合并路由页面与单页面预览入口，避免重复收集。"""

        return ProjectArtifactBuilder.merge_preview_root_pages(route_pages, standalone_entry_page)

    @staticmethod
    def _build_manifest_page_paths(route_pages: list[Page], standalone_entry_page: Page | None) -> set[str]:
        """生成页面模块白名单；单页面预览入口页始终不进入 manifest。"""

        return ProjectArtifactBuilder.build_manifest_page_paths(route_pages, standalone_entry_page)
