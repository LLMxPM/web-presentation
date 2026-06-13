"""文件功能：构建和导入工作空间资源离线包，保留资源文件、标签、描述和渲染元数据。"""

from __future__ import annotations

import hashlib
import io
import json
import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, RecordStatus
from app.schemas.asset import AssetPackageImportItem, AssetPackageImportResult
from app.services.asset_service import AssetService

ASSET_PACKAGE_SCHEMA_VERSION = 1
ASSET_PACKAGE_KIND = "workspace-assets"


@dataclass(slots=True)
class PackageAsset:
    """资源离线包内的单个资源载荷。"""

    metadata: dict[str, Any]
    content: bytes


@dataclass(slots=True)
class ParsedAssetPackage:
    """已解析的资源离线包结构。"""

    manifest: dict[str, Any]
    assets: list[PackageAsset]


class AssetPackageService:
    """资源离线包服务，负责导出、解析和导入资源包。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.asset_service = AssetService(session)

    async def export_package(self, *, workspace_id: int, asset_ids: list[int]) -> tuple[bytes, str]:
        """按资源 ID 导出资源离线包，返回 Zip 二进制内容与文件名。"""

        assets = await self._load_assets(workspace_id, asset_ids)
        buffer = io.BytesIO()
        manifest_assets = [
            self._build_asset_payload(asset, entry_key=self._build_entry_key(asset, index))
            for index, asset in enumerate(assets, start=1)
        ]
        manifest = {
            "schema_version": ASSET_PACKAGE_SCHEMA_VERSION,
            "package_kind": ASSET_PACKAGE_KIND,
            "exported_at": utc_now().isoformat(),
            "assets": manifest_assets,
        }

        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", self._dump_json(manifest))
            for asset, entry in zip(assets, manifest_assets, strict=True):
                base_path = f"assets/{entry['entry_key']}"
                archive.writestr(f"{base_path}/asset.json", self._dump_json(entry))
                archive.writestr(
                    f"{base_path}/{self.safe_archive_filename(asset.original_name)}",
                    await self.asset_service.driver.read_content(workspace_id, asset.file_name),
                )

        return buffer.getvalue(), self._build_export_filename(assets)

    async def import_package(self, *, workspace_id: int, archive_content: bytes) -> AssetPackageImportResult:
        """导入资源离线包，已存在同名同内容资源时更新元数据并复用。"""

        parsed = self.parse_package(archive_content)
        self._validate_manifest(parsed.manifest)
        assets: list[AssetPackageImportItem] = []
        failures: list[dict[str, str]] = []

        for package_asset in parsed.assets:
            asset_name = str(package_asset.metadata.get("name") or "").strip() or "unknown"
            try:
                assets.append(await self._import_package_asset(workspace_id, package_asset))
            except AppException as error:
                await self.session.rollback()
                failures.append({"name": asset_name, "code": error.code, "detail": error.detail})

        await self.session.commit()
        return AssetPackageImportResult(
            imported_count=sum(1 for item in assets if item.action == "create"),
            updated_count=sum(1 for item in assets if item.action == "update_metadata"),
            reused_count=sum(1 for item in assets if item.action == "reuse"),
            failed_count=len(failures),
            assets=assets,
            failures=failures,
        )

    @classmethod
    def parse_package(cls, archive_content: bytes) -> ParsedAssetPackage:
        """从 Zip 二进制内容解析资源离线包。"""

        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_content))
        except zipfile.BadZipFile as error:
            raise AppException(status_code=400, code="ASSET_PACKAGE_INVALID", detail="上传文件不是合法 Zip。") from error

        with archive:
            names = {cls.normalize_zip_name(item.filename) for item in archive.infolist() if not item.is_dir()}
            if "manifest.json" not in names:
                raise AppException(status_code=400, code="ASSET_PACKAGE_INVALID", detail="资源包缺少 manifest.json。")
            manifest = cls.read_json(archive, "manifest.json")
            if not isinstance(manifest, dict):
                raise AppException(status_code=400, code="ASSET_PACKAGE_INVALID", detail="manifest.json 必须是 JSON 对象。")
            asset_entries = cls.resolve_asset_entries(manifest, names)
            return ParsedAssetPackage(
                manifest=manifest,
                assets=[cls.read_package_asset(archive, entry_key) for entry_key in asset_entries],
            )

    @classmethod
    def read_package_asset(cls, archive: zipfile.ZipFile, entry_key: str) -> PackageAsset:
        """读取包内单个资源的元数据和文件内容。"""

        base_path = f"assets/{entry_key}"
        metadata = cls.read_object_json(archive, f"{base_path}/asset.json")
        original_name = cls.safe_archive_filename(str(metadata.get("original_name") or "asset.bin"))
        content = cls.read_bytes(archive, f"{base_path}/{original_name}")
        return PackageAsset(metadata=metadata, content=content)

    async def _load_assets(self, workspace_id: int, asset_ids: list[int]) -> list[WorkspaceAsset]:
        """按请求顺序读取资源并去重。"""

        assets: list[WorkspaceAsset] = []
        for asset_id in AssetService._normalize_batch_asset_ids(asset_ids):
            assets.append(await self.asset_service._get_asset_or_raise(workspace_id, asset_id))
        return assets

    async def _import_package_asset(self, workspace_id: int, package_asset: PackageAsset) -> AssetPackageImportItem:
        """导入单个资源；同名同内容时只同步元数据。"""

        metadata = package_asset.metadata
        name = AssetService._normalize_asset_name(str(metadata.get("name") or ""))
        original_name = AssetService._normalize_original_name(self.safe_archive_filename(str(metadata.get("original_name") or "asset.bin")))
        try:
            asset_type = AssetType(str(metadata.get("asset_type") or ""))
        except ValueError as error:
            raise AppException(status_code=400, code="ASSET_PACKAGE_ASSET_TYPE_INVALID", detail=f"资源 {name} 类型不受支持。") from error
        content_type = AssetService._normalize_content_type(str(metadata.get("content_type") or "") or None)
        content = package_asset.content
        if not content:
            raise AppException(status_code=400, code="ASSET_CONTENT_EMPTY", detail=f"资源 {name} 内容不能为空。")
        file_hash = hashlib.sha256(content).hexdigest()
        expected_hash = str(metadata.get("file_hash") or "").strip()
        if expected_hash and expected_hash != file_hash:
            raise AppException(status_code=400, code="ASSET_PACKAGE_HASH_MISMATCH", detail=f"资源 {name} 文件 hash 与元数据不一致。")

        AssetService._validate_asset_file_type(asset_type, original_name, content_type)
        AssetService._validate_uploaded_asset_content(asset_type, original_name, content)

        existing = await self.asset_service._get_asset_by_name(workspace_id, name)
        if existing is not None:
            return await self._sync_existing_asset_metadata(existing, metadata, original_name, asset_type, file_hash, content_type)

        ext = "".join(Path(original_name).suffixes)
        save_name = await self.asset_service.driver.upload(workspace_id, file_hash, ext, content, content_type)
        asset = WorkspaceAsset(
            workspace_id=workspace_id,
            name=name,
            file_name=save_name,
            original_name=original_name,
            description=AssetService._normalize_description(metadata.get("description")),
            file_size=len(content),
            file_hash=file_hash,
            content_type=content_type,
            asset_type=asset_type.value,
            tags=self._normalize_tags(metadata.get("tags")),
            analysis_metadata=self._resolve_metadata_dict(metadata.get("analysis_metadata"))
            or AssetService._build_analysis_metadata(asset_type, original_name, content_type, content),
            render_metadata=self._resolve_metadata_dict(metadata.get("render_metadata"))
            or AssetService._build_analysis_metadata(asset_type, original_name, content_type, content),
            status=self._resolve_import_status(metadata),
            archived_at=utc_now() if self._resolve_import_status(metadata) == RecordStatus.ARCHIVED.value else None,
            archive_reason=AssetService._normalize_description(metadata.get("archive_reason")),
        )
        self.session.add(asset)
        await self.session.flush()
        return AssetPackageImportItem(
            name=asset.name,
            original_name=asset.original_name,
            asset_type=AssetType(asset.asset_type),
            file_hash=asset.file_hash,
            action="create",
            asset_id=asset.id,
        )

    async def _sync_existing_asset_metadata(
        self,
        existing: WorkspaceAsset,
        metadata: dict[str, Any],
        original_name: str,
        asset_type: AssetType,
        file_hash: str,
        content_type: str | None,
    ) -> AssetPackageImportItem:
        """同名资源已存在时，在文件一致的前提下同步描述、标签等元数据。"""

        if existing.source_asset_id is not None or existing.history_kind:
            raise AppException(status_code=409, code="ASSET_PACKAGE_NAME_CONFLICT", detail=f"资源 {existing.name} 已被历史副本占用。")
        if existing.file_hash != file_hash:
            raise AppException(status_code=409, code="ASSET_PACKAGE_NAME_CONFLICT", detail=f"资源 {existing.name} 已存在且文件内容不同。")
        if existing.asset_type != asset_type.value:
            raise AppException(status_code=409, code="ASSET_PACKAGE_TYPE_CONFLICT", detail=f"资源 {existing.name} 已存在但类型不同。")

        changed = False
        next_description = AssetService._normalize_description(metadata.get("description"))
        next_tags = self._normalize_tags(metadata.get("tags"))
        next_analysis_metadata = self._resolve_metadata_dict(metadata.get("analysis_metadata"))
        next_render_metadata = self._resolve_metadata_dict(metadata.get("render_metadata"))
        if existing.original_name != original_name:
            AssetService._validate_asset_file_type(asset_type, original_name, content_type)
            existing.original_name = original_name
            changed = True
        if existing.description != next_description:
            existing.description = next_description
            changed = True
        if list(existing.tags or []) != next_tags:
            existing.tags = next_tags
            changed = True
        if existing.content_type != content_type:
            existing.content_type = content_type
            changed = True
        if next_analysis_metadata is not None and existing.analysis_metadata != next_analysis_metadata:
            existing.analysis_metadata = next_analysis_metadata
            changed = True
        if next_render_metadata is not None and existing.render_metadata != next_render_metadata:
            existing.render_metadata = next_render_metadata
            changed = True
        await self.session.flush()
        return AssetPackageImportItem(
            name=existing.name,
            original_name=existing.original_name,
            asset_type=AssetType(existing.asset_type),
            file_hash=existing.file_hash,
            action="update_metadata" if changed else "reuse",
            asset_id=existing.id,
        )

    @staticmethod
    def _validate_manifest(manifest: dict[str, Any]) -> None:
        """校验资源包 manifest 的版本与类型。"""

        if manifest.get("package_kind") != ASSET_PACKAGE_KIND:
            raise AppException(status_code=400, code="ASSET_PACKAGE_INVALID", detail="资源包类型不匹配。")
        try:
            schema_version = int(manifest.get("schema_version") or 0)
        except (TypeError, ValueError) as error:
            raise AppException(status_code=400, code="ASSET_PACKAGE_SCHEMA_UNSUPPORTED", detail="资源包 schema_version 不受支持。") from error
        if schema_version != ASSET_PACKAGE_SCHEMA_VERSION:
            raise AppException(status_code=400, code="ASSET_PACKAGE_SCHEMA_UNSUPPORTED", detail="资源包 schema_version 不受支持。")

    @staticmethod
    def _build_asset_payload(asset: WorkspaceAsset, *, entry_key: str) -> dict[str, Any]:
        """构建资源包内单个资源的元数据载荷。"""

        return {
            "entry_key": entry_key,
            "name": asset.name,
            "original_name": asset.original_name,
            "asset_type": asset.asset_type,
            "content_type": asset.content_type,
            "file_size": asset.file_size,
            "file_hash": asset.file_hash,
            "description": asset.description,
            "tags": asset.tags or [],
            "analysis_metadata": asset.analysis_metadata,
            "render_metadata": asset.render_metadata,
            "status": asset.status,
            "archive_reason": asset.archive_reason,
            "history_kind": asset.history_kind,
        }

    @staticmethod
    def _build_entry_key(asset: WorkspaceAsset, index: int) -> str:
        """生成 Zip 内资源目录名，避免同 hash 多资源互相覆盖。"""

        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", asset.name).strip("-") or "asset"
        return f"{index:03d}-{asset.id}-{safe_name}"

    @staticmethod
    def _resolve_import_status(metadata: dict[str, Any]) -> str:
        """导入时仅保留 active/archived 状态，历史副本按 archived 普通资源导入。"""

        status = str(metadata.get("status") or RecordStatus.ACTIVE.value)
        if status == RecordStatus.ARCHIVED.value or metadata.get("history_kind"):
            return RecordStatus.ARCHIVED.value
        return RecordStatus.ACTIVE.value

    @staticmethod
    def _normalize_tags(value: Any) -> list[str]:
        """归一化资源包内标签数组。"""

        if not isinstance(value, list):
            return []
        tags: list[str] = []
        seen: set[str] = set()
        for item in value:
            tag = str(item or "").strip()
            if tag and tag not in seen:
                seen.add(tag)
                tags.append(tag)
        return tags

    @staticmethod
    def _resolve_metadata_dict(value: Any) -> dict[str, Any] | None:
        """仅接受 JSON 对象形式的分析或渲染元数据。"""

        return value if isinstance(value, dict) else None

    @staticmethod
    def _build_export_filename(assets: list[WorkspaceAsset]) -> str:
        """根据首个资源名生成资源包下载文件名。"""

        first_name = assets[0].name if assets else "assets"
        safe_name = re.sub(r'[\\/:*?"<>|\s]+', "-", first_name).strip("-") or "assets"
        suffix = f"-and-{len(assets) - 1}" if len(assets) > 1 else ""
        return f"workspace-assets-{safe_name}{suffix}.zip"

    @staticmethod
    def _dump_json(payload: Any) -> str:
        """稳定序列化资源包 JSON 文件。"""

        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def read_object_json(cls, archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
        """读取 Zip 内 JSON 对象。"""

        payload = cls.read_json(archive, name)
        if not isinstance(payload, dict):
            raise AppException(status_code=400, code="ASSET_PACKAGE_INVALID", detail=f"{name} 必须是 JSON 对象。")
        return payload

    @classmethod
    def read_json(cls, archive: zipfile.ZipFile, name: str) -> dict[str, Any] | list[Any]:
        """读取 Zip 内 JSON 文件。"""

        try:
            return json.loads(cls.read_text(archive, name))
        except json.JSONDecodeError as error:
            raise AppException(status_code=400, code="ASSET_PACKAGE_INVALID", detail=f"{name} 不是合法 JSON。") from error

    @classmethod
    def read_text(cls, archive: zipfile.ZipFile, name: str) -> str:
        """读取 Zip 内 UTF-8 文本文件。"""

        try:
            return cls.read_bytes(archive, name).decode("utf-8")
        except UnicodeDecodeError as error:
            raise AppException(status_code=400, code="ASSET_PACKAGE_INVALID", detail=f"{name} 不是合法 UTF-8 文本。") from error

    @staticmethod
    def read_bytes(archive: zipfile.ZipFile, name: str) -> bytes:
        """读取 Zip 内二进制文件并校验路径存在。"""

        normalized_name = AssetPackageService.normalize_zip_name(name)
        try:
            return archive.read(normalized_name)
        except KeyError as error:
            raise AppException(status_code=400, code="ASSET_PACKAGE_INVALID", detail=f"资源包缺少文件：{normalized_name}。") from error

    @staticmethod
    def normalize_zip_name(name: str) -> str:
        """标准化 Zip 内路径，禁止绝对路径和上级目录。"""

        normalized = posixpath.normpath(str(name or "").replace("\\", "/")).lstrip("/")
        if normalized == "." or normalized.startswith("../") or "/../" in normalized:
            raise AppException(status_code=400, code="ASSET_PACKAGE_PATH_INVALID", detail="资源包包含非法路径。")
        return normalized

    @staticmethod
    def resolve_asset_entries(manifest: dict[str, Any], names: set[str]) -> list[str]:
        """从 manifest 或目录结构解析资源条目目录名。"""

        entries = [
            str(item.get("entry_key") or "").strip()
            for item in manifest.get("assets", [])
            if isinstance(item, dict)
        ]
        if not entries:
            entries = sorted({
                parts[1]
                for name in names
                if (parts := name.split("/")) and len(parts) >= 3 and parts[0] == "assets"
            })
        return [entry for entry in dict.fromkeys(entries) if entry]

    @staticmethod
    def safe_archive_filename(value: str) -> str:
        """清理包内文件名，禁止路径穿越并回退到 asset.bin。"""

        filename = Path(str(value or "").replace("\\", "/")).name.strip()
        return filename or "asset.bin"
