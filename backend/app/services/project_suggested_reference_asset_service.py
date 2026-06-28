"""文件功能：维护项目建议引用内容资源，并提供 AI 上下文精简摘要。"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetRole, AssetType, RecordStatus
from app.models.project_suggested_reference_asset import ProjectSuggestedReferenceAsset
from app.models.workspace import Project
from app.repositories.project_repository import ProjectRepository
from app.schemas.asset import resolve_asset_content_editable, resolve_asset_role
from app.schemas.project import ProjectSuggestedReferenceAssetItem
from app.services.asset_render_metadata_service import AssetRenderMetadataService

PROJECT_SUGGESTED_REFERENCE_ASSET_TYPES = (
    AssetType.IMAGE,
    AssetType.VIDEO,
    AssetType.DRAWIO,
    AssetType.MERMAID,
    AssetType.CHART,
    AssetType.FORMULA,
)
PROJECT_SUGGESTED_REFERENCE_ASSET_TYPE_VALUES = tuple(item.value for item in PROJECT_SUGGESTED_REFERENCE_ASSET_TYPES)


class ProjectSuggestedReferenceAssetService:
    """项目建议引用资源服务，负责权限外的业务校验和有序持久化。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.project_repository = ProjectRepository(session)

    async def list_assets(self, project_id: int, *, workspace_id: int | None = None) -> list[WorkspaceAsset]:
        """读取项目建议引用资源模型列表，按用户保存顺序返回。"""

        await self._get_project_or_raise(project_id, workspace_id=workspace_id)
        statement = (
            select(WorkspaceAsset)
            .join(ProjectSuggestedReferenceAsset, ProjectSuggestedReferenceAsset.asset_id == WorkspaceAsset.id)
            .where(ProjectSuggestedReferenceAsset.project_id == project_id)
            .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceAsset.source_asset_id.is_(None))
            .where(WorkspaceAsset.history_kind.is_(None))
            .where(WorkspaceAsset.asset_type.in_(PROJECT_SUGGESTED_REFERENCE_ASSET_TYPE_VALUES))
            .order_by(ProjectSuggestedReferenceAsset.sort_order.asc(), ProjectSuggestedReferenceAsset.id.asc())
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def list_asset_items(
        self,
        project_id: int,
        *,
        workspace_id: int | None = None,
    ) -> list[ProjectSuggestedReferenceAssetItem]:
        """读取适合接口和 AI 上下文使用的精简资源摘要。"""

        assets = await self.list_assets(project_id, workspace_id=workspace_id)
        return [self.dump_asset_item(asset) for asset in assets]

    async def replace_assets(self, project_id: int, asset_ids: list[int]) -> list[ProjectSuggestedReferenceAssetItem]:
        """覆盖保存项目建议引用资源，校验资源属于项目工作空间且为 active 内容资源。"""

        project = await self._get_project_or_raise(project_id)
        normalized_asset_ids = self._normalize_asset_ids(asset_ids)
        assets_by_id = await self._load_assets_by_id(project.workspace_id, normalized_asset_ids)
        ordered_assets = [assets_by_id[asset_id] for asset_id in normalized_asset_ids]
        for asset in ordered_assets:
            self._ensure_suggestible_content_asset(asset)

        await self._delete_project_links(project_id)
        for index, asset in enumerate(ordered_assets):
            self.session.add(
                ProjectSuggestedReferenceAsset(
                    project_id=project_id,
                    asset_id=asset.id,
                    sort_order=index * 10,
                )
            )
        await self.session.commit()
        return [self.dump_asset_item(asset) for asset in ordered_assets]

    async def clear_project_assets(self, project_id: int, *, commit: bool = True) -> None:
        """清空项目建议引用资源；迁移项目工作空间时复用该能力。"""

        await self._delete_project_links(project_id)
        if commit:
            await self.session.commit()

    async def _get_project_or_raise(self, project_id: int, *, workspace_id: int | None = None) -> Project:
        """读取项目并按需校验工作空间归属。"""

        project = await self.project_repository.get_by_id(project_id)
        if project is None or (workspace_id is not None and project.workspace_id != workspace_id):
            raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="项目不存在。")
        return project

    async def _load_assets_by_id(self, workspace_id: int, asset_ids: list[int]) -> dict[int, WorkspaceAsset]:
        """批量读取指定工作空间内资源，并保证请求中的每个资源都存在。"""

        if not asset_ids:
            return {}
        statement = (
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.id.in_(asset_ids))
        )
        assets = list((await self.session.execute(statement)).scalars().all())
        assets_by_id = {asset.id: asset for asset in assets}
        missing_ids = [asset_id for asset_id in asset_ids if asset_id not in assets_by_id]
        if missing_ids:
            raise AppException(status_code=400, code="PROJECT_SUGGESTED_ASSET_INVALID", detail="建议引用资源不存在或不属于项目工作空间。")
        return assets_by_id

    async def _delete_project_links(self, project_id: int) -> None:
        """删除项目既有建议引用资源关联。"""

        await self.session.execute(
            delete(ProjectSuggestedReferenceAsset).where(ProjectSuggestedReferenceAsset.project_id == project_id)
        )

    @staticmethod
    def _normalize_asset_ids(asset_ids: list[int]) -> list[int]:
        """规范化资源 ID 列表，去重并保留用户选择顺序。"""

        normalized_ids: list[int] = []
        seen_ids: set[int] = set()
        for value in asset_ids:
            asset_id = int(value)
            if asset_id in seen_ids:
                continue
            seen_ids.add(asset_id)
            normalized_ids.append(asset_id)
        return normalized_ids

    @staticmethod
    def _ensure_suggestible_content_asset(asset: WorkspaceAsset) -> None:
        """确保资源可以作为项目建议引用内容资源。"""

        if asset.status != RecordStatus.ACTIVE.value or asset.source_asset_id is not None or asset.history_kind:
            raise AppException(
                status_code=400,
                code="PROJECT_SUGGESTED_ASSET_INVALID",
                detail="仅 active 普通资源可作为项目建议引用资源。",
            )
        asset_type = AssetType(asset.asset_type)
        if asset_type not in PROJECT_SUGGESTED_REFERENCE_ASSET_TYPES:
            raise AppException(
                status_code=400,
                code="PROJECT_SUGGESTED_ASSET_INVALID",
                detail="项目建议引用资源只支持内容资源，不支持图标或字体资源。",
            )
        if resolve_asset_role(asset_type) != AssetRole.CONTENT:
            raise AppException(
                status_code=400,
                code="PROJECT_SUGGESTED_ASSET_INVALID",
                detail="项目建议引用资源只支持内容资源，不支持图标或字体资源。",
            )

    @staticmethod
    def dump_asset_item(asset: WorkspaceAsset) -> ProjectSuggestedReferenceAssetItem:
        """转换资源为不会暴露 URL 与标签的稳定摘要。"""

        ratio_summary = AssetRenderMetadataService.summarize_metadata(asset.render_metadata)
        return ProjectSuggestedReferenceAssetItem(
            id=asset.id,
            name=asset.name,
            original_name=asset.original_name,
            description=asset.description,
            asset_type=AssetType(asset.asset_type),
            content_editable=resolve_asset_content_editable(asset.asset_type, asset.original_name, asset.content_type),
            approx_aspect_ratio=ratio_summary["approx_aspect_ratio"],
            approx_aspect_ratio_value=ratio_summary["approx_aspect_ratio_value"],
            aspect_ratio_source=ratio_summary["aspect_ratio_source"],
        )
