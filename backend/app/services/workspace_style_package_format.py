"""文件功能：定义样式离线包的数据结构、Zip 解析与格式化辅助能力。"""

from __future__ import annotations

import io
import json
import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.exceptions import AppException

STYLE_PACKAGE_SCHEMA_VERSION = 3


@dataclass(slots=True)
class PackageStyle:
    """离线包内的样式载荷。"""

    payload: dict[str, Any]


@dataclass(slots=True)
class PackageTheme:
    """离线包内的主题载荷。"""

    payload: dict[str, Any]


@dataclass(slots=True)
class PackageAsset:
    """离线包内的资源元数据和二进制内容。"""

    metadata: dict[str, Any]
    content: bytes


@dataclass(slots=True)
class ParsedStylePackage:
    """已解析的样式离线包。"""

    manifest: dict[str, Any]
    styles: list[PackageStyle]
    themes: list[PackageTheme]
    assets: list[PackageAsset]
    font_configs: list[dict[str, Any]]


class WorkspaceStylePackageFormat:
    """样式离线包格式工具，负责安全读取 Zip 与稳定序列化。"""

    @classmethod
    def parse_package(cls, archive_content: bytes) -> ParsedStylePackage:
        """从 Zip 二进制内容解析样式离线包结构。"""

        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_content))
        except zipfile.BadZipFile as error:
            raise AppException(status_code=400, code="WORKSPACE_STYLE_PACKAGE_INVALID", detail="上传文件不是合法 Zip。") from error

        with archive:
            names = {cls.normalize_zip_name(item.filename) for item in archive.infolist() if not item.is_dir()}
            if "manifest.json" not in names:
                raise AppException(status_code=400, code="WORKSPACE_STYLE_PACKAGE_INVALID", detail="样式离线包缺少 manifest.json。")
            manifest = cls.read_json(archive, "manifest.json")
            if not isinstance(manifest, dict):
                raise AppException(status_code=400, code="WORKSPACE_STYLE_PACKAGE_INVALID", detail="manifest.json 必须是 JSON 对象。")

            style_keys = cls.resolve_package_keys(manifest, names, "styles", "key")
            theme_keys = cls.resolve_package_keys(manifest, names, "themes", "key")
            asset_hashes = cls.resolve_package_asset_hashes(manifest, names)
            styles = [PackageStyle(cls.read_object_json(archive, f"styles/{key}.json")) for key in style_keys]
            themes = [PackageTheme(cls.read_object_json(archive, f"themes/{key}.json")) for key in theme_keys]
            assets = [cls.read_package_asset(archive, asset_hash) for asset_hash in asset_hashes]
            font_payload = cls.read_json(archive, "fonts/font-configs.json") if "fonts/font-configs.json" in names else []
            if not isinstance(font_payload, list):
                raise AppException(status_code=400, code="WORKSPACE_STYLE_PACKAGE_INVALID", detail="fonts/font-configs.json 必须是 JSON 数组。")
            font_configs = [item for item in font_payload if isinstance(item, dict)]

        return ParsedStylePackage(
            manifest=manifest,
            styles=styles,
            themes=themes,
            assets=assets,
            font_configs=font_configs,
        )

    @classmethod
    def read_package_asset(cls, archive: zipfile.ZipFile, asset_hash: str) -> PackageAsset:
        """读取包内单个资源。"""

        base_path = f"assets/{asset_hash}"
        metadata = cls.read_object_json(archive, f"{base_path}/asset.json")
        original_name = cls.safe_archive_filename(str(metadata.get("original_name") or "asset.bin"))
        content = cls.read_bytes(archive, f"{base_path}/{original_name}")
        return PackageAsset(metadata=metadata, content=content)

    @classmethod
    def read_object_json(cls, archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
        """读取并校验 Zip 中的 JSON 对象。"""

        payload = cls.read_json(archive, name)
        if not isinstance(payload, dict):
            raise AppException(status_code=400, code="WORKSPACE_STYLE_PACKAGE_INVALID", detail=f"{name} 必须是 JSON 对象。")
        return payload

    @classmethod
    def read_json(cls, archive: zipfile.ZipFile, name: str) -> dict[str, Any] | list[Any]:
        """从 Zip 中读取 JSON 文件。"""

        try:
            return json.loads(cls.read_text(archive, name))
        except json.JSONDecodeError as error:
            raise AppException(status_code=400, code="WORKSPACE_STYLE_PACKAGE_INVALID", detail=f"{name} 不是合法 JSON。") from error

    @classmethod
    def read_text(cls, archive: zipfile.ZipFile, name: str) -> str:
        """从 Zip 中读取 UTF-8 文本。"""

        try:
            return cls.read_bytes(archive, name).decode("utf-8")
        except UnicodeDecodeError as error:
            raise AppException(status_code=400, code="WORKSPACE_STYLE_PACKAGE_INVALID", detail=f"{name} 不是合法 UTF-8 文本。") from error

    @staticmethod
    def read_bytes(archive: zipfile.ZipFile, name: str) -> bytes:
        """从 Zip 中读取二进制文件并校验路径存在。"""

        normalized_name = WorkspaceStylePackageFormat.normalize_zip_name(name)
        try:
            return archive.read(normalized_name)
        except KeyError as error:
            raise AppException(status_code=400, code="WORKSPACE_STYLE_PACKAGE_INVALID", detail=f"样式离线包缺少文件：{normalized_name}。") from error

    @staticmethod
    def normalize_zip_name(name: str) -> str:
        """标准化 Zip 内部路径，禁止绝对路径和上级目录。"""

        normalized = posixpath.normpath(str(name or "").replace("\\", "/")).lstrip("/")
        if normalized == "." or normalized.startswith("../") or "/../" in normalized:
            raise AppException(status_code=400, code="WORKSPACE_STYLE_PACKAGE_PATH_INVALID", detail="样式离线包包含非法路径。")
        return normalized

    @staticmethod
    def resolve_package_keys(manifest: dict[str, Any], names: set[str], section: str, key_field: str) -> list[str]:
        """从 manifest 或目录结构解析样式、主题 key。"""

        keys = [
            str(item.get(key_field) or "").strip()
            for item in manifest.get(section, [])
            if isinstance(item, dict)
        ]
        if not keys:
            keys = sorted({
                Path(name).stem
                for name in names
                if name.startswith(f"{section}/") and name.endswith(".json")
            })
        return [key for key in dict.fromkeys(keys) if key]

    @staticmethod
    def resolve_package_asset_hashes(manifest: dict[str, Any], names: set[str]) -> list[str]:
        """从 manifest 或目录结构解析包内资源 hash。"""

        asset_hashes = [
            str(item.get("file_hash") or "").strip()
            for item in manifest.get("assets", [])
            if isinstance(item, dict)
        ]
        if not asset_hashes:
            asset_hashes = sorted({
                parts[1]
                for name in names
                if (parts := name.split("/")) and len(parts) >= 3 and parts[0] == "assets"
            })
        return [file_hash for file_hash in dict.fromkeys(asset_hashes) if file_hash]

    @staticmethod
    def safe_archive_filename(name: str) -> str:
        """把资源展示文件名规整为 Zip 内单文件名。"""

        filename = Path(str(name or "asset.bin").replace("\\", "/")).name
        return filename or "asset.bin"

    @staticmethod
    def dump_json(value: Any) -> str:
        """按项目约定输出 UTF-8 友好的格式化 JSON。"""

        return json.dumps(value, ensure_ascii=False, indent=2)

    @staticmethod
    def canonical_payload(value: dict[str, Any]) -> str:
        """将业务载荷转成稳定 JSON，供内容一致性比较。"""

        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def normalize_optional_name(value: object) -> str | None:
        """归一化可空资源名、字体资源名或 legacy 路径。"""

        normalized = str(value or "").strip()
        return normalized or None

    @staticmethod
    def coerce_int(value: Any) -> int | None:
        """把输入值转为整数，失败时返回空。"""

        try:
            return int(value)
        except (TypeError, ValueError):
            return None
