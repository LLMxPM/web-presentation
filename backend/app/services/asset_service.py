"""文件功能：处理工作空间资源的物理存储、内容写入、归档历史与引用保护。"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from fastapi import UploadFile
from sqlalchemy import String, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.time_utils import format_in_app_timezone, utc_now
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, RecordStatus
from app.models.font import WorkspaceFontConfig
from app.models.page import Page
from app.models.page_component_resource import PageVersionComponentResource
from app.models.page_version import PageVersion
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.models.workspace_theme import WorkspaceTheme
from app.schemas.asset import AssetReferenceSummary, resolve_asset_content_editable, resolve_asset_role
from app.services.asset_storage_drivers import BaseStorageDriver, get_driver
from app.services.icon_analysis_service import IconAnalysisService
from app.repositories.component_resource_index_repository import ComponentResourceIndexRepository
from app.services.asset_render_metadata_service import AssetRenderMetadataService, AspectRatioSource
from app.services.component_resource_index_service import ComponentResourceIndexService
from app.services.workspace_font_service import WorkspaceFontService


class AssetService:
    """管理工作空间资源的上传、文本写入、复制、归档、恢复与删除。"""

    ALLOWED_ASSET_EXTENSIONS: dict[AssetType, set[str]] = {
        AssetType.ICON: {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"},
        AssetType.FONT: {".woff2", ".woff", ".ttf", ".otf"},
        AssetType.IMAGE: {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"},
        AssetType.VIDEO: {".mp4", ".webm", ".ogg", ".ogv", ".mov", ".m4v"},
        AssetType.DRAWIO: {".drawio", ".xml"},
        AssetType.MERMAID: {".mmd", ".mermaid", ".txt"},
        AssetType.CHART: {".json", ".yaml", ".yml"},
        AssetType.FORMULA: {".tex", ".txt"},
    }
    CONTENT_EDITABLE_TYPES = {
        AssetType.ICON,
        AssetType.IMAGE,
        AssetType.DRAWIO,
        AssetType.MERMAID,
        AssetType.CHART,
        AssetType.FORMULA,
    }
    TEXT_CONTENT_MAX_BYTES = 512 * 1024
    HISTORY_KIND_WRITE_SNAPSHOT = "write_snapshot"
    HISTORY_NAME_PREFIX = "__history__"
    SVG_FORBIDDEN_RE = re.compile(
        r"(<\s*script\b|<\s*foreignobject\b|\son[a-z0-9_-]+\s*=|(?:href|xlink:href)\s*=\s*['\"]\s*(?:https?:)?//|url\(\s*['\"]?\s*(?:https?:)?//)",
        re.IGNORECASE,
    )

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.driver = get_driver()

    async def list_assets(
        self,
        workspace_id: int,
        *,
        asset_type: AssetType | None = None,
        exclude_asset_type: AssetType | None = None,
        asset_role: Any | None = None,
        render_type: AssetType | None = None,
        status: RecordStatus | str | None = RecordStatus.ACTIVE,
        include_history: bool = False,
        history_only: bool = False,
        keyword: str | None = None,
        tag: str | None = None,
        page: int = 1,
        page_size: int = 100,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> tuple[list[WorkspaceAsset], int]:
        """按分页、状态、类型和关键词列出工作空间资源。"""

        stmt = select(WorkspaceAsset).where(WorkspaceAsset.workspace_id == workspace_id)
        count_stmt = select(func.count(WorkspaceAsset.id)).where(WorkspaceAsset.workspace_id == workspace_id)
        resolved_type = render_type or asset_type
        if resolved_type:
            stmt = stmt.where(WorkspaceAsset.asset_type == resolved_type.value)
            count_stmt = count_stmt.where(WorkspaceAsset.asset_type == resolved_type.value)
        elif exclude_asset_type is not None:
            stmt = stmt.where(WorkspaceAsset.asset_type != exclude_asset_type.value)
            count_stmt = count_stmt.where(WorkspaceAsset.asset_type != exclude_asset_type.value)
        if asset_role:
            role_value = getattr(asset_role, "value", asset_role)
            role_types = [item.value for item in AssetType if resolve_asset_role(item).value == role_value]
            stmt = stmt.where(WorkspaceAsset.asset_type.in_(role_types))
            count_stmt = count_stmt.where(WorkspaceAsset.asset_type.in_(role_types))
        if status is not None:
            status_value = status.value if isinstance(status, RecordStatus) else str(status)
            stmt = stmt.where(WorkspaceAsset.status == status_value)
            count_stmt = count_stmt.where(WorkspaceAsset.status == status_value)
        if history_only:
            stmt = stmt.where(WorkspaceAsset.source_asset_id.is_not(None))
            count_stmt = count_stmt.where(WorkspaceAsset.source_asset_id.is_not(None))
        elif not include_history:
            stmt = stmt.where(WorkspaceAsset.source_asset_id.is_(None))
            count_stmt = count_stmt.where(WorkspaceAsset.source_asset_id.is_(None))

        normalized_keyword = str(keyword or "").strip()
        if normalized_keyword:
            like_keyword = f"%{normalized_keyword}%"
            keyword_condition = or_(
                WorkspaceAsset.name.ilike(like_keyword),
                WorkspaceAsset.original_name.ilike(like_keyword),
                WorkspaceAsset.file_name.ilike(like_keyword),
                WorkspaceAsset.description.ilike(like_keyword),
                WorkspaceAsset.content_type.ilike(like_keyword),
                WorkspaceAsset.asset_type.ilike(like_keyword),
                self._build_tags_keyword_condition(normalized_keyword),
            )
            stmt = stmt.where(keyword_condition)
            count_stmt = count_stmt.where(keyword_condition)

        sort_column = getattr(WorkspaceAsset, sort_by, WorkspaceAsset.updated_at)
        sort_expression = sort_column.asc() if sort_order == "asc" else sort_column.desc()
        bounded_page = max(1, int(page))
        bounded_page_size = max(1, min(int(page_size), 100))
        normalized_tag = str(tag or "").strip()
        if normalized_tag:
            ordered_stmt = stmt.order_by(sort_expression, WorkspaceAsset.id.desc())
            candidate_assets = list((await self.session.execute(ordered_stmt)).scalars().all())
            filtered_assets = [asset for asset in candidate_assets if self._asset_has_tag(asset, normalized_tag)]
            total = len(filtered_assets)
            offset = (bounded_page - 1) * bounded_page_size
            return filtered_assets[offset:offset + bounded_page_size], total

        stmt = (
            stmt
            .order_by(sort_expression, WorkspaceAsset.id.desc())
            .offset((bounded_page - 1) * bounded_page_size)
            .limit(bounded_page_size)
        )
        total = int(await self.session.scalar(count_stmt) or 0)
        return list((await self.session.execute(stmt)).scalars().all()), total

    @staticmethod
    def _build_tags_keyword_condition(keyword: str) -> Any:
        """构建标签关键词匹配条件，兼容 SQLite JSON 字符串的 Unicode 转义存储。"""

        tag_text = WorkspaceAsset.tags.cast(String)
        conditions = [tag_text.ilike(f"%{keyword}%")]
        escaped_keyword = json.dumps(keyword, ensure_ascii=True).strip('"')
        if escaped_keyword != keyword:
            conditions.append(tag_text.ilike(f"%{escaped_keyword}%"))
        return or_(*conditions)

    @staticmethod
    def _asset_has_tag(asset: WorkspaceAsset, tag: str) -> bool:
        """按 JSON 数组实际内容判断资源是否包含指定标签，避免依赖数据库 JSON 文本格式。"""

        normalized_tag = str(tag or "").strip()
        if not normalized_tag:
            return False
        return any(str(item or "").strip() == normalized_tag for item in asset.tags or [])

    async def upload_asset(
        self,
        workspace_id: int,
        file: UploadFile,
        asset_type: AssetType = AssetType.ICON,
        tags: list[str] | None = None,
        name: str | None = None,
        description: str | None = None,
        overwrite: bool = False,
    ) -> WorkspaceAsset:
        """保存上传资源；覆盖写入时自动生成历史归档副本。"""

        resolved_tags = tags or []
        original_name = self._normalize_original_name(file.filename or "unknown")
        asset_name = self._normalize_asset_name(name or self._build_default_asset_name(original_name))
        normalized_description = self._normalize_description(description)
        content_type = self._normalize_content_type(file.content_type)
        self._validate_asset_file_type(asset_type, original_name, content_type)

        content = await file.read()
        if not content:
            raise AppException(status_code=400, code="ASSET_CONTENT_EMPTY", detail="资源内容不能为空。")
        self._validate_uploaded_asset_content(asset_type, original_name, content)
        file_hash = hashlib.sha256(content).hexdigest()
        file_size = len(content)

        existing_by_name = await self._get_asset_by_name(workspace_id, asset_name)
        existing_by_original_name = await self._get_active_asset_by_original_name(workspace_id, original_name)
        overwrite_target = existing_by_original_name or existing_by_name
        if overwrite_target is not None:
            self._ensure_can_write_current_asset(overwrite_target)
            if not overwrite:
                detail = (
                    f'文件 "{original_name}" 已存在，请确认是否覆盖。'
                    if existing_by_original_name is not None
                    else f'资源 name "{asset_name}" 已存在，请确认是否覆盖。'
                )
                raise AppException(status_code=409, code="ASSET_NAME_CONFLICT", detail=detail)

        ext = "".join(Path(original_name).suffixes)
        save_name = await self.driver.upload(workspace_id, file_hash, ext, content, content_type)
        if overwrite_target is not None:
            return await self._overwrite_asset(
                overwrite_target,
                original_name=original_name,
                asset_type=asset_type,
                content=content,
                content_type=content_type,
                file_hash=file_hash,
                file_name=save_name,
                file_size=file_size,
                description=normalized_description,
                create_history_snapshot=True,
            )

        analysis_metadata = self._build_analysis_metadata(asset_type, original_name, content_type, content)
        render_metadata = AssetRenderMetadataService.build_auto_metadata(asset_type, original_name, content_type, content)
        asset = WorkspaceAsset(
            workspace_id=workspace_id,
            name=asset_name,
            file_name=save_name,
            original_name=original_name,
            description=normalized_description,
            file_size=file_size,
            file_hash=file_hash,
            content_type=content_type,
            asset_type=asset_type.value,
            tags=resolved_tags,
            analysis_metadata=analysis_metadata,
            render_metadata=render_metadata,
            status=RecordStatus.ACTIVE.value,
        )
        self.session.add(asset)
        await self.session.commit()
        await self.session.refresh(asset)
        return asset

    async def create_content_asset(
        self,
        workspace_id: int,
        *,
        asset_type: AssetType,
        name: str,
        original_name: str,
        content: str,
        tags: list[str] | None = None,
        description: str | None = None,
        approx_aspect_ratio: str | None = None,
        aspect_ratio_source: AspectRatioSource = "manual",
    ) -> WorkspaceAsset:
        """通过文本内容创建 SVG 图标、SVG 图片、Draw.io、Mermaid、Chart 或 Formula 资源。"""

        asset_name = self._normalize_asset_name(name)
        original_name = self._normalize_original_name(original_name)
        normalized_description = self._normalize_description(description)
        self._validate_asset_file_type(asset_type, original_name, None)
        normalized_content, content_type = self._validate_editable_content(asset_type, original_name, content)
        content_bytes = normalized_content.encode("utf-8")
        file_hash = hashlib.sha256(content_bytes).hexdigest()
        ext = "".join(Path(original_name).suffixes)

        await self._ensure_asset_name_available(workspace_id, asset_name)
        save_name = await self.driver.upload(workspace_id, file_hash, ext, content_bytes, content_type)
        analysis_metadata = self._build_analysis_metadata(asset_type, original_name, content_type, content_bytes)
        render_metadata = AssetRenderMetadataService.build_manual_or_auto_metadata(
            value=approx_aspect_ratio,
            source=aspect_ratio_source,
            asset_type=asset_type,
            original_name=original_name,
            content_type=content_type,
            content=content_bytes,
        )
        asset = WorkspaceAsset(
            workspace_id=workspace_id,
            name=asset_name,
            file_name=save_name,
            original_name=original_name,
            description=normalized_description,
            file_size=len(content_bytes),
            file_hash=file_hash,
            content_type=content_type,
            asset_type=asset_type.value,
            tags=tags or [],
            analysis_metadata=analysis_metadata,
            render_metadata=render_metadata,
            status=RecordStatus.ACTIVE.value,
        )
        self.session.add(asset)
        await self.session.commit()
        await self.session.refresh(asset)
        return asset

    async def get_asset_content(self, workspace_id: int, asset_id: int) -> str:
        """读取可编辑资源的 UTF-8 文本内容。"""

        asset = await self._get_asset_or_raise(workspace_id, asset_id)
        self._ensure_content_readable(asset)
        raw_content = await self.driver.read_content(workspace_id, asset.file_name)
        try:
            return raw_content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise AppException(status_code=400, code="ASSET_CONTENT_NOT_UTF8", detail="资源内容不是合法 UTF-8 文本。") from error

    async def preview_content_update(self, workspace_id: int, asset_id: int, content: str) -> dict[str, object]:
        """预览资源内容写入 diff，不产生历史副本或实际写入。"""

        asset = await self._get_asset_or_raise(workspace_id, asset_id)
        self._ensure_asset_content_writable(asset)
        asset_type = AssetType(asset.asset_type)
        new_content, _ = self._validate_editable_content(asset_type, asset.original_name, content)
        old_content = await self.get_asset_content(workspace_id, asset_id)
        return {
            "asset_id": asset.id,
            "asset_name": asset.name,
            "changed": old_content != new_content,
            "unified_diff": self._build_unified_diff(old_content, new_content, fromfile=asset.original_name),
        }

    async def update_asset_content(
        self,
        workspace_id: int,
        asset_id: int,
        content: str,
        *,
        change_note: str | None = None,
    ) -> WorkspaceAsset:
        """替换可编辑资源内容，并在写入前自动创建 archived 历史副本。"""

        asset = await self._get_asset_or_raise(workspace_id, asset_id)
        self._ensure_asset_content_writable(asset)
        asset_type = AssetType(asset.asset_type)
        normalized_content, content_type = self._validate_editable_content(asset_type, asset.original_name, content)
        content_bytes = normalized_content.encode("utf-8")
        file_hash = hashlib.sha256(content_bytes).hexdigest()
        ext = "".join(Path(asset.original_name).suffixes)
        save_name = await self.driver.upload(workspace_id, file_hash, ext, content_bytes, content_type or asset.content_type)
        return await self._overwrite_asset(
            asset,
            original_name=asset.original_name,
            asset_type=asset_type,
            content=content_bytes,
            content_type=content_type or asset.content_type,
            file_hash=file_hash,
            file_name=save_name,
            file_size=len(content_bytes),
            description=None,
            create_history_snapshot=True,
            history_reason=change_note,
        )

    async def replace_asset_file(
        self,
        workspace_id: int,
        asset_id: int,
        file: UploadFile,
    ) -> WorkspaceAsset:
        """按资源 ID 替换文件内容，并在写入前自动生成历史副本。"""

        asset = await self._get_asset_or_raise(workspace_id, asset_id)
        self._ensure_can_write_current_asset(asset)
        asset_type = AssetType(asset.asset_type)
        original_name = self._normalize_original_name(file.filename or "unknown")
        content_type = self._normalize_content_type(file.content_type)
        self._validate_asset_file_type(asset_type, original_name, content_type)

        content = await file.read()
        if not content:
            raise AppException(status_code=400, code="ASSET_CONTENT_EMPTY", detail="资源内容不能为空。")
        self._validate_uploaded_asset_content(asset_type, original_name, content)
        file_hash = hashlib.sha256(content).hexdigest()
        file_size = len(content)
        ext = "".join(Path(original_name).suffixes)
        file_name = await self.driver.upload(workspace_id, file_hash, ext, content, content_type)

        return await self._overwrite_asset(
            asset,
            original_name=original_name,
            asset_type=asset_type,
            content=content,
            content_type=content_type,
            file_hash=file_hash,
            file_name=file_name,
            file_size=file_size,
            description=None,
            create_history_snapshot=True,
        )

    async def copy_asset(
        self,
        workspace_id: int,
        asset_id: int,
        *,
        name: str | None = None,
        original_name: str | None = None,
        tags: list[str] | None = None,
        description: str | None = None,
        status: RecordStatus = RecordStatus.ACTIVE,
        archive_reason: str | None = None,
    ) -> WorkspaceAsset:
        """复制资源记录并复用物理文件指针；不会复制为历史副本。"""

        source = await self._get_asset_or_raise(workspace_id, asset_id)
        normalized_name = self._normalize_asset_name(name) if name else await self._build_available_asset_name(workspace_id, f"{source.name}_copy")
        await self._ensure_asset_name_available(workspace_id, normalized_name)
        normalized_original_name = self._normalize_original_name(original_name) if original_name else source.original_name
        normalized_description = self._normalize_description(description) if description is not None else source.description
        resolved_status = status.value if isinstance(status, RecordStatus) else str(status)
        if resolved_status not in {RecordStatus.ACTIVE.value, RecordStatus.ARCHIVED.value}:
            raise AppException(status_code=400, code="ASSET_STATUS_INVALID", detail="资源状态非法。")

        asset = WorkspaceAsset(
            workspace_id=workspace_id,
            name=normalized_name,
            file_name=source.file_name,
            original_name=normalized_original_name,
            description=normalized_description,
            file_size=source.file_size,
            file_hash=source.file_hash,
            content_type=source.content_type,
            asset_type=source.asset_type,
            tags=tags if tags is not None else list(source.tags or []),
            analysis_metadata=source.analysis_metadata,
            render_metadata=source.render_metadata,
            status=resolved_status,
            archived_at=utc_now() if resolved_status == RecordStatus.ARCHIVED.value else None,
            archive_reason=self._normalize_description(archive_reason) if resolved_status == RecordStatus.ARCHIVED.value else None,
        )
        self.session.add(asset)
        await self.session.commit()
        await self.session.refresh(asset)
        return asset

    async def archive_asset(self, workspace_id: int, asset_id: int, *, archive_reason: str | None = None) -> WorkspaceAsset:
        """归档资源；归档后保留 name、hash 与公开访问能力。"""

        asset = await self._get_asset_or_raise(workspace_id, asset_id)
        if asset.source_asset_id is not None or asset.history_kind:
            raise AppException(status_code=409, code="ASSET_HISTORY_ARCHIVE_FORBIDDEN", detail="历史副本已是归档记录，不允许再次归档。")
        if asset.status == RecordStatus.ARCHIVED.value:
            return asset
        self._ensure_normal_asset_for_archive(asset)
        return await self._archive_asset_model(asset, archive_reason=archive_reason)

    async def batch_archive_assets(
        self,
        workspace_id: int,
        asset_ids: list[int],
        *,
        archive_reason: str | None = None,
    ) -> dict[str, object]:
        """批量归档 active 普通资源，逐项返回成功 ID 与失败原因。"""

        succeeded_ids: list[int] = []
        failures: list[dict[str, object]] = []
        for asset_id in self._normalize_batch_asset_ids(asset_ids):
            try:
                asset = await self._get_asset_or_raise(workspace_id, asset_id)
                self._ensure_normal_asset_for_archive(asset)
                await self._archive_asset_model(asset, archive_reason=archive_reason)
                succeeded_ids.append(asset_id)
            except AppException as error:
                await self.session.rollback()
                failures.append({"asset_id": asset_id, "code": error.code, "detail": error.detail})

        return self._build_batch_operation_payload(succeeded_ids, failures)

    async def restore_asset(self, workspace_id: int, asset_id: int, *, restore_reason: str | None = None) -> WorkspaceAsset:
        """恢复普通归档资源；写入历史副本保持 archived，不允许直接恢复为 active。"""

        asset = await self._get_asset_or_raise(workspace_id, asset_id)
        if asset.history_kind or asset.source_asset_id is not None:
            raise AppException(status_code=409, code="ASSET_HISTORY_RESTORE_FORBIDDEN", detail="历史副本不可直接恢复为 active，请复制为新资源或写回当前资源。")
        asset.status = RecordStatus.ACTIVE.value
        asset.archived_at = None
        asset.archive_reason = None
        await self.session.commit()
        await self.session.refresh(asset)
        return asset

    async def batch_restore_assets(
        self,
        workspace_id: int,
        asset_ids: list[int],
        *,
        restore_reason: str | None = None,
    ) -> dict[str, object]:
        """批量恢复普通归档资源，逐项返回成功 ID 与失败原因。"""

        succeeded_ids: list[int] = []
        failures: list[dict[str, object]] = []
        for asset_id in self._normalize_batch_asset_ids(asset_ids):
            try:
                await self.restore_asset(workspace_id, asset_id, restore_reason=restore_reason)
                succeeded_ids.append(asset_id)
            except AppException as error:
                await self.session.rollback()
                failures.append({"asset_id": asset_id, "code": error.code, "detail": error.detail})

        return self._build_batch_operation_payload(succeeded_ids, failures)

    async def batch_delete_assets(self, workspace_id: int, asset_ids: list[int]) -> dict[str, object]:
        """批量删除 archived 或历史资源，逐项返回成功 ID 与失败原因。"""

        succeeded_ids: list[int] = []
        failures: list[dict[str, object]] = []
        for asset_id in self._normalize_batch_asset_ids(asset_ids):
            try:
                await self._get_asset_or_raise(workspace_id, asset_id)
                await self.delete_asset(workspace_id, asset_id)
                succeeded_ids.append(asset_id)
            except AppException as error:
                await self.session.rollback()
                failures.append({"asset_id": asset_id, "code": error.code, "detail": error.detail})

        return self._build_batch_operation_payload(succeeded_ids, failures)

    async def update_asset_metadata(
        self,
        workspace_id: int,
        asset_id: int,
        name: str | None = None,
        original_name: str | None = None,
        tags: list[str] | None = None,
        description: str | None = None,
        approx_aspect_ratio: str | None = None,
        approx_aspect_ratio_provided: bool = False,
        aspect_ratio_source: AspectRatioSource = "manual",
    ) -> WorkspaceAsset:
        """更新资源元数据；不改变物理文件指针，也不生成历史副本。"""

        asset = await self._get_asset_or_raise(workspace_id, asset_id)
        normalized_name = self._normalize_asset_name(name) if name is not None else asset.name
        normalized_original_name = self._normalize_original_name(original_name) if original_name is not None else asset.original_name
        normalized_description = self._normalize_description(description) if description is not None else asset.description
        original_name_changed = normalized_original_name != asset.original_name

        if normalized_name != asset.name:
            await self._ensure_asset_name_available(workspace_id, normalized_name, exclude_asset_id=asset.id)
            asset.name = normalized_name

        if original_name_changed:
            self._validate_asset_file_type(AssetType(asset.asset_type), normalized_original_name, asset.content_type)
            asset.original_name = normalized_original_name

        if normalized_description != asset.description:
            asset.description = normalized_description

        if tags is not None:
            asset.tags = tags

        if approx_aspect_ratio_provided:
            content = await self.driver.read_content(workspace_id, asset.file_name)
            asset.render_metadata = AssetRenderMetadataService.build_manual_or_auto_metadata(
                value=approx_aspect_ratio,
                source=aspect_ratio_source,
                asset_type=AssetType(asset.asset_type),
                original_name=asset.original_name,
                content_type=asset.content_type,
                content=content,
            )
        elif original_name_changed and not AssetRenderMetadataService.is_manual_metadata(asset.render_metadata):
            content = await self.driver.read_content(workspace_id, asset.file_name)
            asset.render_metadata = AssetRenderMetadataService.build_auto_metadata(
                AssetType(asset.asset_type),
                asset.original_name,
                asset.content_type,
                content,
            )

        await WorkspaceFontService(self.session).sync_asset_reference_name(asset)
        await self.session.commit()
        await self.session.refresh(asset)
        return asset

    async def delete_asset(self, workspace_id: int, asset_id: int) -> None:
        """删除已归档且无引用的资源；物理文件仅在无其他记录复用时删除。"""

        asset = await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.id == asset_id)
        )
        if asset is None:
            return
        await WorkspaceFontService(self.session).ensure_asset_can_delete(asset)
        if asset.status != RecordStatus.ARCHIVED.value:
            raise AppException(status_code=409, code="ASSET_DELETE_REQUIRES_ARCHIVE", detail="仅允许删除已归档资源。")

        await self._purge_soft_deleted_theme_asset_references(workspace_id, asset)
        references = await self.preview_asset_references(workspace_id, asset_id)
        if references.has_references:
            raise AppException(status_code=409, code="ASSET_DELETE_FORBIDDEN", detail="资源仍存在引用，请先解除引用后再删除。")

        file_name = asset.file_name
        await self.session.delete(asset)
        try:
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise AppException(status_code=409, code="ASSET_DELETE_FORBIDDEN", detail="资源仍存在外键引用，请先解除引用后再删除。") from error
        if await self._count_file_name_references(workspace_id, file_name) == 0:
            try:
                await self.driver.delete(workspace_id, file_name)
            except Exception:
                pass

    async def delete_workspace_font_with_asset(self, workspace_id: int, font_id: int) -> None:
        """删除字体注册，并在安全时一并硬删除其字体资产和历史记录。"""

        font_service = WorkspaceFontService(self.session)
        font_config = await font_service._get_font_config_or_raise(workspace_id, font_id)
        conflict_error = font_service._build_font_config_in_use_error(font_config)
        if await font_service._is_font_config_referenced(workspace_id, font_config):
            raise conflict_error

        asset = await self._get_asset_or_raise(workspace_id, font_config.asset_id)
        if asset.asset_type != AssetType.FONT.value:
            raise AppException(status_code=409, code="FONT_ASSET_INVALID", detail="字体注册关联的资源不是字体文件，无法一并删除。")

        await font_service.workspace_theme_service.purge_soft_deleted_theme_font_references(workspace_id, font_config.id)
        await self._ensure_font_asset_has_no_external_references(workspace_id, asset)
        await self.session.delete(font_config)
        try:
            await self._delete_asset_records_and_unused_files(workspace_id, asset)
        except IntegrityError as error:
            await self.session.rollback()
            raise conflict_error from error

    async def delete_unregistered_font_asset(self, workspace_id: int, asset_id: int) -> None:
        """硬删除未注册字体资产；若存在字体注册或源码引用则拒绝。"""

        asset = await self._get_asset_or_raise(workspace_id, asset_id)
        if asset.asset_type != AssetType.FONT.value:
            raise AppException(status_code=400, code="FONT_ASSET_REQUIRED", detail="仅允许通过该接口删除字体文件。")

        font_service = WorkspaceFontService(self.session)
        if await font_service.get_font_config_by_asset_id(workspace_id, asset.id):
            raise AppException(status_code=409, code="FONT_ASSET_REGISTERED", detail="该字体文件已注册，请先删除字体注册。")

        await self._ensure_font_asset_has_no_external_references(workspace_id, asset)
        try:
            await self._delete_asset_records_and_unused_files(workspace_id, asset)
        except IntegrityError as error:
            await self.session.rollback()
            raise AppException(status_code=409, code="FONT_ASSET_DELETE_FORBIDDEN", detail="字体文件仍存在引用，请先解除引用后再删除。") from error

    async def preview_asset_references(self, workspace_id: int, asset_id: int) -> AssetReferenceSummary:
        """统计资源在主题、字体、页面与组件中的引用，供删除阻断和前端提示使用。"""

        asset = await self._get_asset_or_raise(workspace_id, asset_id)
        references: list[dict[str, object]] = []

        themes = await self._list_theme_references(workspace_id, asset)
        for item in themes:
            references.append({"kind": "theme", "id": item.id, "name": item.name})

        fonts = await self._list_font_references(workspace_id, asset)
        for item in fonts:
            references.append({"kind": "font", "id": item.id, "name": item.asset_name})

        pages = await self._list_page_references(workspace_id, asset)
        for item in pages:
            references.append({"kind": "page", "id": item.id, "name": item.title})

        components = await self._list_component_references(workspace_id, asset)
        for item in components:
            references.append({"kind": "component", "id": item.id, "name": item.name})

        component_versions = await self._list_component_version_references(workspace_id, asset)
        for item in component_versions:
            version, component = item
            references.append(
                {
                    "kind": "component_version",
                    "id": version.id,
                    "component_id": component.id,
                    "name": component.name,
                    "version_no": version.version_no,
                }
            )

        return AssetReferenceSummary(
            theme_count=len(themes),
            font_count=len(fonts),
            page_count=len(pages),
            component_count=len(components),
            component_version_count=len(component_versions),
            references=references,
        )

    async def get_asset_by_hash(self, workspace_id: int, file_hash: str) -> tuple[WorkspaceAsset, BaseStorageDriver]:
        """根据 Hash 获取资产模型与存储驱动；允许多个记录复用同一物理文件。"""

        asset = await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.file_hash == file_hash)
            .order_by(WorkspaceAsset.source_asset_id.asc(), WorkspaceAsset.id.asc())
        )
        if asset is None:
            raise AppException(status_code=404, code="ASSET_NOT_FOUND", detail="未找到目标静态资源。")
        return asset, self.driver

    async def list_tags(
        self,
        workspace_id: int,
        *,
        asset_type: AssetType | None = None,
        exclude_asset_type: AssetType | None = None,
        status: RecordStatus | str | None = RecordStatus.ACTIVE,
        include_history: bool = False,
        history_only: bool = False,
    ) -> list[str]:
        """按资源类型、状态和历史范围汇总工作空间资源标签。"""

        stmt = select(WorkspaceAsset).where(WorkspaceAsset.workspace_id == workspace_id)
        if asset_type is not None:
            stmt = stmt.where(WorkspaceAsset.asset_type == asset_type.value)
        elif exclude_asset_type is not None:
            stmt = stmt.where(WorkspaceAsset.asset_type != exclude_asset_type.value)
        if status is not None:
            status_value = status.value if isinstance(status, RecordStatus) else str(status)
            stmt = stmt.where(WorkspaceAsset.status == status_value)
        if history_only:
            stmt = stmt.where(WorkspaceAsset.source_asset_id.is_not(None))
        elif not include_history:
            stmt = stmt.where(WorkspaceAsset.source_asset_id.is_(None))
        assets = list((await self.session.execute(stmt)).scalars().all())
        tags: set[str] = set()
        for asset in assets:
            for tag in asset.tags or []:
                normalized = str(tag or "").strip()
                if normalized:
                    tags.add(normalized)
        return sorted(tags)

    async def _overwrite_asset(
        self,
        asset: WorkspaceAsset,
        *,
        original_name: str,
        asset_type: AssetType,
        content: bytes,
        content_type: str | None,
        file_hash: str,
        file_name: str,
        file_size: int,
        description: str | None,
        create_history_snapshot: bool,
        history_reason: str | None = None,
    ) -> WorkspaceAsset:
        """覆盖当前资源记录；写入前可复制旧文件指针为 archived 历史副本。"""

        old_file_name = asset.file_name
        if create_history_snapshot:
            await self._create_history_snapshot(asset, reason=history_reason)

        analysis_metadata = self._build_analysis_metadata(asset_type, original_name, content_type, content)
        render_metadata = AssetRenderMetadataService.preserve_manual_or_build_auto(
            asset_type=asset_type,
            original_name=original_name,
            content_type=content_type,
            content=content,
            existing_metadata=asset.render_metadata,
        )
        asset.file_name = file_name
        asset.original_name = original_name
        asset.file_size = file_size
        asset.file_hash = file_hash
        asset.content_type = content_type
        asset.asset_type = asset_type.value
        asset.analysis_metadata = analysis_metadata
        asset.render_metadata = render_metadata
        if description is not None:
            asset.description = description

        await self.session.commit()
        await self.session.refresh(asset)
        if old_file_name != file_name and await self._count_file_name_references(asset.workspace_id, old_file_name) == 0:
            try:
                await self.driver.delete(asset.workspace_id, old_file_name)
            except Exception:
                pass
        return asset

    async def _create_history_snapshot(self, asset: WorkspaceAsset, *, reason: str | None = None) -> WorkspaceAsset:
        """复制当前资源记录和文件指针为内部 archived 历史副本。"""

        if asset.source_asset_id is not None or asset.history_kind:
            raise AppException(status_code=409, code="ASSET_HISTORY_WRITE_FORBIDDEN", detail="历史副本不可直接写入。")
        if asset.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=409, code="ASSET_ARCHIVED_WRITE_FORBIDDEN", detail="归档资源不可直接写入内容。")

        timestamp = format_in_app_timezone(pattern="%Y%m%d%H%M%S")
        base_name = f"{self.HISTORY_NAME_PREFIX}{asset.id}_{timestamp}_{asset.file_hash[:8]}"
        history_name = await self._build_available_asset_name(asset.workspace_id, base_name)
        history = WorkspaceAsset(
            workspace_id=asset.workspace_id,
            name=history_name,
            file_name=asset.file_name,
            original_name=asset.original_name,
            description=asset.description,
            file_size=asset.file_size,
            file_hash=asset.file_hash,
            content_type=asset.content_type,
            asset_type=asset.asset_type,
            tags=list(asset.tags or []),
            analysis_metadata=asset.analysis_metadata,
            render_metadata=asset.render_metadata,
            status=RecordStatus.ARCHIVED.value,
            archived_at=utc_now(),
            archive_reason=self._normalize_description(reason) or "写入前自动归档副本。",
            source_asset_id=asset.id,
            history_kind=self.HISTORY_KIND_WRITE_SNAPSHOT,
        )
        self.session.add(history)
        await self.session.flush()
        return history

    async def _get_asset_or_raise(self, workspace_id: int, asset_id: int) -> WorkspaceAsset:
        """按工作空间和资源 ID 查询资源，不存在时抛出统一业务异常。"""

        asset = await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.id == asset_id)
        )
        if asset is None:
            raise AppException(status_code=404, code="ASSET_NOT_FOUND", detail="未找到目标静态资源。")
        return asset

    async def _ensure_asset_name_available(
        self,
        workspace_id: int,
        name: str,
        *,
        exclude_asset_id: int | None = None,
    ) -> None:
        """确保工作空间内资源逻辑名唯一；归档资源也不释放 name。"""

        stmt = (
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.name == name)
        )
        if exclude_asset_id is not None:
            stmt = stmt.where(WorkspaceAsset.id != exclude_asset_id)
        existing = await self.session.scalar(stmt)
        if existing is not None:
            raise AppException(status_code=409, code="ASSET_NAME_CONFLICT", detail=f'资源 name "{name}" 已存在，请更换后重试。')

    async def _build_available_asset_name(self, workspace_id: int, base_name: str) -> str:
        """在给定基础名后追加序号，生成可用资源 name。"""

        normalized_base = self._normalize_asset_name(base_name)[:220]
        candidate = normalized_base
        index = 1
        while True:
            existing = await self._get_asset_by_name(workspace_id, candidate)
            if existing is None:
                return candidate
            index += 1
            candidate = f"{normalized_base}_{index}"

    async def _get_active_asset_by_original_name(self, workspace_id: int, original_name: str) -> WorkspaceAsset | None:
        """按展示文件名查询 active 普通资源，作为上传同名覆盖目标。"""

        return await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.original_name == original_name)
            .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceAsset.source_asset_id.is_(None))
            .order_by(WorkspaceAsset.created_at.desc(), WorkspaceAsset.id.desc())
        )

    async def _get_asset_by_name(self, workspace_id: int, name: str) -> WorkspaceAsset | None:
        """按逻辑名查询工作空间资源，用于冲突检测。"""

        return await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.name == name)
        )

    async def _count_file_name_references(self, workspace_id: int, file_name: str) -> int:
        """统计同一物理文件名仍被多少资源记录复用。"""

        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(WorkspaceAsset)
                .where(WorkspaceAsset.workspace_id == workspace_id)
                .where(WorkspaceAsset.file_name == file_name)
            )
            or 0
        )

    async def _delete_asset_records_and_unused_files(self, workspace_id: int, asset: WorkspaceAsset) -> None:
        """硬删除当前资产及其历史记录，并清理不再被资产记录复用的物理文件。"""

        history_assets = list(
            (
                await self.session.execute(
                    select(WorkspaceAsset)
                    .where(WorkspaceAsset.workspace_id == workspace_id)
                    .where(WorkspaceAsset.source_asset_id == asset.id)
                )
            )
            .scalars()
            .all()
        )
        file_names = {item.file_name for item in [asset, *history_assets] if item.file_name}
        for history_asset in history_assets:
            await self.session.delete(history_asset)
        await self.session.delete(asset)
        await self.session.commit()

        for file_name in file_names:
            if await self._count_file_name_references(workspace_id, file_name) == 0:
                try:
                    await self.driver.delete(workspace_id, file_name)
                except Exception:
                    pass

    async def _ensure_font_asset_has_no_external_references(self, workspace_id: int, asset: WorkspaceAsset) -> None:
        """确认字体资产除自身注册外不再被主题、页面或组件引用。"""

        references = await self.preview_asset_references(workspace_id, asset.id)
        external_references = [item for item in references.references if item.get("kind") != "font"]
        if external_references:
            raise AppException(
                status_code=409,
                code="FONT_ASSET_DELETE_FORBIDDEN",
                detail="字体文件仍存在主题、页面或组件引用，请先解除引用后再删除。",
            )

    async def _list_theme_references(self, workspace_id: int, asset: WorkspaceAsset) -> list[WorkspaceTheme]:
        """列出主题中通过资源 ID 或历史字段引用该资源的记录。"""

        hard_reference_condition = or_(
            WorkspaceTheme.logo_asset_id == asset.id,
            WorkspaceTheme.invert_logo_asset_id == asset.id,
            WorkspaceTheme.project_icon_asset_id == asset.id,
        )
        active_path_reference_condition = (
            (WorkspaceTheme.workspace_id == workspace_id)
            & (WorkspaceTheme.deleted_at.is_(None))
            & or_(
                WorkspaceTheme.logo_path == asset.name,
                WorkspaceTheme.invert_logo_path == asset.name,
                WorkspaceTheme.project_icon_name == asset.name,
            )
        )
        stmt = (
            select(WorkspaceTheme)
            .where(or_(hard_reference_condition, active_path_reference_condition))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def _purge_soft_deleted_theme_asset_references(self, workspace_id: int, asset: WorkspaceAsset) -> None:
        """硬删除历史软删除主题，释放旧数据中残留的资源外键。"""

        stmt = (
            select(WorkspaceTheme)
            .where(WorkspaceTheme.workspace_id == workspace_id)
            .where(WorkspaceTheme.deleted_at.is_not(None))
            .where(
                or_(
                    WorkspaceTheme.logo_asset_id == asset.id,
                    WorkspaceTheme.invert_logo_asset_id == asset.id,
                    WorkspaceTheme.project_icon_asset_id == asset.id,
                )
            )
        )
        for theme in (await self.session.execute(stmt)).scalars().all():
            await self.session.delete(theme)
        await self.session.flush()

    async def _list_font_references(self, workspace_id: int, asset: WorkspaceAsset) -> list[WorkspaceFontConfig]:
        """列出字体配置中引用该资源的记录。"""

        stmt = (
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(or_(WorkspaceFontConfig.asset_id == asset.id, WorkspaceFontConfig.asset_name == asset.name))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def _list_page_references(self, workspace_id: int, asset: WorkspaceAsset) -> list[Page]:
        """列出当前页面版本资源索引中引用该资源 name 的页面。"""

        indexed_stmt = (
            select(Page)
            .join(PageVersion, PageVersion.page_id == Page.id)
            .join(PageVersionComponentResource, PageVersionComponentResource.page_version_id == PageVersion.id)
            .where(Page.workspace_id == workspace_id)
            .where(Page.deleted_at.is_(None))
            .where(PageVersion.version_no == Page.current_version_no)
            .where(PageVersionComponentResource.resource_name == asset.name)
        )
        pages: dict[int, Page] = {}
        for item in (await self.session.execute(indexed_stmt)).scalars().all():
            pages[item.id] = item
        if asset.asset_type == AssetType.FONT.value:
            source_stmt = (
                select(Page, PageVersion)
                .join(PageVersion, PageVersion.page_id == Page.id)
                .where(Page.workspace_id == workspace_id)
                .where(Page.deleted_at.is_(None))
                .where(PageVersion.version_no == Page.current_version_no)
            )
            for page, page_version in (await self.session.execute(source_stmt)).all():
                if page.id in pages:
                    continue
                if self._sources_reference_font_asset([page.page_content, page_version.content], asset.name):
                    pages[page.id] = page
        return list(pages.values())

    async def _list_component_references(self, workspace_id: int, asset: WorkspaceAsset) -> list[WorkspaceComponent]:
        """列出组件草稿结构化资源引用中命中该资源 name 的组件。"""

        stmt = (
            select(WorkspaceComponent)
            .where(WorkspaceComponent.workspace_id == workspace_id)
            .where(WorkspaceComponent.deleted_at.is_(None))
        )
        components = list((await self.session.execute(stmt)).scalars().all())
        return [
            component
            for component in components
            if self._component_sources_reference_asset(
                content=component.content,
                preview_schema=component.preview_schema,
                asset_name=asset.name,
                include_font_declarations=asset.asset_type == AssetType.FONT.value,
            )
        ]

    async def _list_component_version_references(
        self,
        workspace_id: int,
        asset: WorkspaceAsset,
    ) -> list[tuple[WorkspaceComponentVersion, WorkspaceComponent]]:
        """列出组件发布版本结构化资源引用中命中该资源 name 的版本。"""

        stmt = (
            select(WorkspaceComponentVersion, WorkspaceComponent)
            .join(WorkspaceComponent, WorkspaceComponent.id == WorkspaceComponentVersion.component_id)
            .where(WorkspaceComponent.workspace_id == workspace_id)
            .where(WorkspaceComponent.deleted_at.is_(None))
        )
        rows = list((await self.session.execute(stmt)).all())
        resource_repository = ComponentResourceIndexRepository(self.session)
        references: list[tuple[WorkspaceComponentVersion, WorkspaceComponent]] = []
        for version, component in rows:
            indexed_items = await resource_repository.list_component_resources_by_version(version.id)
            if indexed_items:
                if any(item.resource_name == asset.name for item in indexed_items):
                    references.append((version, component))
                continue
            if self._component_sources_reference_asset(
                content=version.content,
                preview_schema=version.preview_schema,
                asset_name=asset.name,
                include_font_declarations=asset.asset_type == AssetType.FONT.value,
            ):
                references.append((version, component))
        return references

    @staticmethod
    def _component_sources_reference_asset(
        *,
        content: str,
        preview_schema: str | None,
        asset_name: str,
        include_font_declarations: bool = False,
    ) -> bool:
        """使用统一解析器判断组件源码或 preview_schema 是否静态引用指定资源。"""

        resource_items = ComponentResourceIndexService.collect_version_resource_items(
            content=content,
            preview_schema=preview_schema,
        )
        if any(resource_name == asset_name for _, resource_name in resource_items):
            return True
        return include_font_declarations and AssetService._sources_reference_font_asset([content], asset_name)

    @staticmethod
    def _sources_reference_font_asset(sources: Iterable[str], asset_name: str) -> bool:
        """判断源码是否通过 Runtime Kit 字体 API 显式声明了字体资源。"""

        return asset_name in WorkspaceFontService.collect_declared_font_asset_names(sources)

    @classmethod
    def _validate_editable_content(cls, asset_type: AssetType, original_name: str, content: str) -> tuple[str, str]:
        """校验可写资源内容并返回规范化文本与 MIME 类型。"""

        if asset_type not in cls.CONTENT_EDITABLE_TYPES:
            raise AppException(status_code=400, code="ASSET_CONTENT_EDIT_UNSUPPORTED", detail="该资源类型不支持内容写入。")
        if asset_type == AssetType.ICON and not cls._is_svg_name(original_name):
            raise AppException(status_code=400, code="ICON_BITMAP_EDIT_UNSUPPORTED", detail="仅 SVG 图标支持生成或修改；位图图标只能复制、归档和维护元数据。")
        if asset_type == AssetType.IMAGE and not cls._is_svg_name(original_name):
            raise AppException(status_code=400, code="IMAGE_BITMAP_EDIT_UNSUPPORTED", detail="仅 SVG 图片支持生成或修改；位图图片只能上传、复制、归档和维护元数据。")

        normalized = cls._normalize_text_content(content)
        content_bytes = normalized.encode("utf-8")
        if len(content_bytes) > cls.TEXT_CONTENT_MAX_BYTES:
            raise AppException(status_code=400, code="ASSET_CONTENT_TOO_LARGE", detail="资源文本内容超过大小上限。")

        if asset_type in {AssetType.ICON, AssetType.IMAGE}:
            cls._validate_svg_content(normalized)
            return normalized, "image/svg+xml"
        if asset_type == AssetType.DRAWIO:
            cls._validate_xml_content(normalized, code="DRAWIO_XML_INVALID", detail="Draw.io 内容必须是可解析 XML。")
            return normalized, "application/xml"
        if asset_type == AssetType.CHART:
            cls._validate_chart_content(normalized, original_name)
            suffix = Path(original_name).suffix.lower()
            return normalized, "application/yaml" if suffix in {".yaml", ".yml"} else "application/json"
        if asset_type == AssetType.MERMAID:
            return normalized, "text/plain; charset=utf-8"
        if asset_type == AssetType.FORMULA:
            return normalized, "text/plain; charset=utf-8"
        raise AppException(status_code=400, code="ASSET_CONTENT_EDIT_UNSUPPORTED", detail="该资源类型不支持内容写入。")

    @classmethod
    def _validate_uploaded_asset_content(cls, asset_type: AssetType, original_name: str, content: bytes) -> None:
        """对上传文件补充内容级校验，避免绕过文本写入安全约束。"""

        if asset_type in {AssetType.ICON, AssetType.IMAGE} and not cls._is_svg_name(original_name):
            return
        if asset_type not in cls.CONTENT_EDITABLE_TYPES:
            return
        try:
            text_content = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise AppException(status_code=400, code="ASSET_CONTENT_NOT_UTF8", detail="资源内容不是合法 UTF-8 文本。") from error
        cls._validate_editable_content(asset_type, original_name, text_content)

    @classmethod
    def _ensure_content_readable(cls, asset: WorkspaceAsset) -> None:
        """校验资源是否允许读取为文本内容。"""

        if asset.source_asset_id is not None and asset.history_kind != cls.HISTORY_KIND_WRITE_SNAPSHOT:
            raise AppException(status_code=400, code="ASSET_CONTENT_READ_UNSUPPORTED", detail="该资源不支持内容读取。")
        if not resolve_asset_content_editable(asset.asset_type, asset.original_name, asset.content_type):
            raise AppException(status_code=400, code="ASSET_CONTENT_READ_UNSUPPORTED", detail="该资源不支持内容读取。")

    @classmethod
    def _ensure_asset_content_writable(cls, asset: WorkspaceAsset) -> None:
        """校验资源是否允许被内容写入。"""

        cls._ensure_can_write_current_asset(asset)
        if not resolve_asset_content_editable(asset.asset_type, asset.original_name, asset.content_type):
            raise AppException(status_code=400, code="ASSET_CONTENT_EDIT_UNSUPPORTED", detail="该资源不支持内容写入。")

    @staticmethod
    def _ensure_can_write_current_asset(asset: WorkspaceAsset) -> None:
        """禁止对归档资源和历史副本直接写入。"""

        if asset.source_asset_id is not None or asset.history_kind:
            raise AppException(status_code=409, code="ASSET_HISTORY_WRITE_FORBIDDEN", detail="历史副本不可直接写入。")
        if asset.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=409, code="ASSET_ARCHIVED_WRITE_FORBIDDEN", detail="归档资源不可直接写入。")

    @staticmethod
    def _ensure_normal_asset_for_archive(asset: WorkspaceAsset) -> None:
        """校验批量或单项归档只能作用于 active 普通资源。"""

        if asset.source_asset_id is not None or asset.history_kind:
            raise AppException(status_code=409, code="ASSET_HISTORY_ARCHIVE_FORBIDDEN", detail="历史副本已是归档记录，不允许再次归档。")
        if asset.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=409, code="ASSET_ARCHIVE_REQUIRES_ACTIVE", detail="仅允许归档启用中的普通资源。")

    async def _archive_asset_model(self, asset: WorkspaceAsset, *, archive_reason: str | None = None) -> WorkspaceAsset:
        """把已校验的资源模型标记为 archived 并提交。"""

        asset.status = RecordStatus.ARCHIVED.value
        asset.archived_at = utc_now()
        asset.archive_reason = self._normalize_description(archive_reason)
        await self.session.commit()
        await self.session.refresh(asset)
        return asset

    @staticmethod
    def _normalize_batch_asset_ids(asset_ids: list[int]) -> list[int]:
        """去重并保留资源 ID 原始顺序，避免批量操作重复执行。"""

        normalized_ids: list[int] = []
        seen_ids: set[int] = set()
        for asset_id in asset_ids:
            resolved_id = int(asset_id)
            if resolved_id in seen_ids:
                continue
            seen_ids.add(resolved_id)
            normalized_ids.append(resolved_id)
        return normalized_ids

    @classmethod
    def _build_batch_operation_payload(
        cls,
        succeeded_ids: list[int],
        failures: list[dict[str, object]],
    ) -> dict[str, object]:
        """组装批量操作接口响应，统一数量字段语义。"""

        return {
            "requested_count": len(succeeded_ids) + len(failures),
            "succeeded_count": len(succeeded_ids),
            "failed_count": len(failures),
            "asset_ids": succeeded_ids,
            "failures": failures,
        }

    @classmethod
    def _build_analysis_metadata(
        cls,
        asset_type: AssetType,
        original_name: str,
        content_type: str | None,
        content: bytes,
    ) -> dict | None:
        """生成图标分析元数据，非图标返回空。"""

        if asset_type != AssetType.ICON:
            return None
        return IconAnalysisService.analyze_icon_asset(file_name=original_name, content_type=content_type, content=content)

    @classmethod
    def _validate_svg_content(cls, content: str) -> None:
        """拒绝脚本、事件属性、foreignObject 和远程引用后再解析 SVG。"""

        if cls.SVG_FORBIDDEN_RE.search(content):
            raise AppException(status_code=400, code="SVG_CONTENT_UNSAFE", detail="SVG 不能包含 script、事件属性、foreignObject 或远程引用。")
        root = cls._validate_xml_content(content, code="SVG_XML_INVALID", detail="SVG 内容必须是可解析 XML。")
        tag = cls._local_xml_name(str(root.tag)).lower()
        if tag != "svg":
            raise AppException(status_code=400, code="SVG_ROOT_INVALID", detail="SVG 根节点必须是 svg。")

    @staticmethod
    def _validate_xml_content(content: str, *, code: str, detail: str) -> ET.Element:
        """解析 XML，失败时抛出统一业务异常。"""

        try:
            return ET.fromstring(content)
        except ET.ParseError as error:
            raise AppException(status_code=400, code=code, detail=detail) from error

    @staticmethod
    def _validate_chart_content(content: str, original_name: str) -> None:
        """校验图表 JSON/YAML 可解析且顶层为对象。"""

        suffix = Path(original_name).suffix.lower()
        try:
            parsed = yaml.safe_load(content) if suffix in {".yaml", ".yml"} else json.loads(content)
        except Exception as error:
            raise AppException(status_code=400, code="CHART_CONTENT_INVALID", detail="Chart 内容必须是可解析的 JSON 或 YAML。") from error
        if not isinstance(parsed, dict):
            raise AppException(status_code=400, code="CHART_CONTENT_INVALID", detail="Chart 内容顶层必须是对象。")

    @staticmethod
    def _normalize_text_content(content: str) -> str:
        """规范化文本换行并拒绝空内容。"""

        if not isinstance(content, str):
            raise AppException(status_code=400, code="ASSET_CONTENT_INVALID", detail="资源内容必须是字符串。")
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise AppException(status_code=400, code="ASSET_CONTENT_EMPTY", detail="资源内容不能为空。")
        return normalized

    @staticmethod
    def _build_unified_diff(old_content: str, new_content: str, *, fromfile: str) -> str:
        """生成统一 diff 文本，供 UI 和 AI 工具预览。"""

        diff = difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=fromfile,
            tofile=fromfile,
            lineterm="",
        )
        return "\n".join(diff)

    @staticmethod
    def _local_xml_name(tag: str) -> str:
        """去掉 XML 命名空间，仅返回局部标签名。"""

        if "}" in tag:
            return tag.rsplit("}", 1)[-1]
        return tag

    @staticmethod
    def _is_svg_name(original_name: str) -> bool:
        """判断文件名是否是 SVG。"""

        return Path(str(original_name or "")).suffix.lower() == ".svg"

    @staticmethod
    def _normalize_original_name(value: str) -> str:
        """规范化展示文件名，仅保留 basename 并去掉首尾空白。"""

        normalized_value = Path(str(value or "").strip()).name.strip()
        if not normalized_value:
            raise AppException(status_code=400, code="ASSET_ORIGINAL_NAME_INVALID", detail="资源文件名不能为空。")
        return normalized_value

    @classmethod
    def _build_default_asset_name(cls, original_name: str) -> str:
        """根据展示文件名生成默认逻辑名，规则为去掉全部后缀。"""

        normalized_name = cls._normalize_original_name(original_name)
        base_name = normalized_name
        while True:
            next_path = Path(base_name)
            if not next_path.suffix:
                break
            base_name = next_path.stem
        return base_name or Path(normalized_name).stem or normalized_name

    @staticmethod
    def _normalize_asset_name(value: str | None) -> str:
        """规范化资源逻辑名，并拒绝路径类输入。"""

        normalized_value = str(value or "").strip()
        if not normalized_value:
            raise AppException(status_code=400, code="ASSET_NAME_INVALID", detail="资源 name 不能为空。")
        if "/" in normalized_value or "\\" in normalized_value:
            raise AppException(status_code=400, code="ASSET_NAME_INVALID", detail='资源 name 不能包含 "/" 或 "\\"。')
        if normalized_value in {".", ".."}:
            raise AppException(status_code=400, code="ASSET_NAME_INVALID", detail="资源 name 非法。")
        return normalized_value

    @staticmethod
    def _normalize_description(value: str | None) -> str | None:
        """规范化描述或归档原因，空值统一转为 None。"""

        if value is None:
            return None
        normalized_value = str(value).strip()
        if not normalized_value:
            return None
        return normalized_value

    @staticmethod
    def _normalize_content_type(value: str | None) -> str | None:
        """规范化上传文件 MIME 类型，空值统一转为 None。"""

        normalized_value = str(value or "").strip().lower()
        return normalized_value or None

    @classmethod
    def _validate_asset_file_type(cls, asset_type: AssetType, original_name: str, content_type: str | None) -> None:
        """按资源类型校验文件扩展名和关键 MIME 类型约束。"""

        suffix = Path(original_name).suffix.lower()
        allowed_extensions = cls.ALLOWED_ASSET_EXTENSIONS.get(asset_type, set())
        if suffix not in allowed_extensions:
            allowed_text = "、".join(sorted(allowed_extensions))
            raise AppException(status_code=400, code="ASSET_FILE_TYPE_UNSUPPORTED", detail=f"{asset_type.value} 资源仅支持以下文件类型：{allowed_text}。")

        base_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
        if asset_type == AssetType.FONT and base_content_type and not (
            base_content_type.startswith("font/")
            or base_content_type in {"application/font-woff", "application/x-font-ttf", "application/octet-stream"}
        ):
            raise AppException(status_code=400, code="ASSET_CONTENT_TYPE_UNSUPPORTED", detail="字体资源的 MIME 类型不符合要求。")
        if asset_type == AssetType.VIDEO and base_content_type and not (
            base_content_type.startswith("video/")
            or base_content_type in {"application/mp4", "application/octet-stream"}
        ):
            raise AppException(status_code=400, code="ASSET_CONTENT_TYPE_UNSUPPORTED", detail="视频资源的 MIME 类型不符合要求。")
