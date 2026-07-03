"""文件功能：定义项目模板包 ZIP 格式、安全解析和稳定序列化辅助能力。"""

from __future__ import annotations

import io
import json
import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.exceptions import AppException
from app.services.component_share_package_models import PackageAsset, PackageComponent
from app.services.workspace_style_package_format import PackageTheme


@dataclass(slots=True)
class PackageTemplatePage:
    """模板包中的页面源码和元数据。"""

    source_page_code: str
    metadata: dict[str, Any]
    content: str


@dataclass(slots=True)
class ParsedProjectTemplatePackage:
    """已解析的项目模板包。"""

    manifest: dict[str, Any]
    template: dict[str, Any]
    screenshots: dict[str, Any]
    project: dict[str, Any]
    routes: dict[str, Any]
    pages: list[PackageTemplatePage]
    components: list[PackageComponent]
    themes: list[PackageTheme]
    assets: list[PackageAsset]
    font_configs: list[dict[str, Any]]
    screenshot_files: dict[str, bytes]


class ProjectTemplatePackageFormat:
    """模板包格式工具，负责 ZIP 路径安全、解析和 JSON 输出。"""

    @classmethod
    def parse_package(cls, archive_content: bytes) -> ParsedProjectTemplatePackage:
        """从 ZIP 二进制内容解析项目模板包。"""

        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_content))
        except zipfile.BadZipFile as error:
            raise AppException(status_code=400, code="PROJECT_TEMPLATE_PACKAGE_INVALID", detail="上传文件不是合法 Zip。") from error

        with archive:
            names = {cls.normalize_zip_name(item.filename) for item in archive.infolist() if not item.is_dir()}
            cls._ensure_required_files(names)
            manifest = cls.read_object_json(archive, "manifest.json")
            template = cls.read_object_json(archive, "metadata/template.json")
            screenshots = cls.read_object_json(archive, "metadata/screenshots.json")
            project = cls.read_object_json(archive, "project/project.json")
            routes = cls.read_object_json(archive, "project/routes.json")

            pages = [cls.read_package_page(archive, page_code) for page_code in cls.resolve_page_codes(manifest, names)]
            components = [
                cls.read_package_component(archive, component_code)
                for component_code in cls.resolve_component_codes(manifest, names)
            ]
            themes = [
                PackageTheme(cls.read_object_json(archive, f"themes/{theme_key}.json"))
                for theme_key in cls.resolve_keys(manifest, names, "themes", "key")
            ]
            assets = [
                cls.read_package_asset(archive, file_hash)
                for file_hash in cls.resolve_asset_hashes(manifest, names)
            ]
            font_payload = cls.read_json(archive, "fonts/font-configs.json") if "fonts/font-configs.json" in names else []
            if not isinstance(font_payload, list):
                raise AppException(status_code=400, code="PROJECT_TEMPLATE_PACKAGE_INVALID", detail="fonts/font-configs.json 必须是 JSON 数组。")
            screenshot_files = cls.read_screenshot_files(archive, screenshots, names)

        return ParsedProjectTemplatePackage(
            manifest=manifest,
            template=template,
            screenshots=screenshots,
            project=project,
            routes=routes,
            pages=pages,
            components=components,
            themes=themes,
            assets=assets,
            font_configs=[item for item in font_payload if isinstance(item, dict)],
            screenshot_files=screenshot_files,
        )

    @classmethod
    def read_package_page(cls, archive: zipfile.ZipFile, page_code: str) -> PackageTemplatePage:
        """读取模板包内单个页面。"""

        base_path = f"pages/{page_code}"
        metadata = cls.read_object_json(archive, f"{base_path}/page.json")
        content = cls.read_text(archive, f"{base_path}/index.vue")
        return PackageTemplatePage(
            source_page_code=str(metadata.get("source_page_code") or page_code).strip(),
            metadata=metadata,
            content=content,
        )

    @classmethod
    def read_package_component(cls, archive: zipfile.ZipFile, component_code: str) -> PackageComponent:
        """读取模板包内单个组件。"""

        base_path = f"components/{component_code}"
        metadata = cls.read_object_json(archive, f"{base_path}/component.json")
        content = cls.read_text(archive, f"{base_path}/index.vue")
        preview_schema = cls.read_text(archive, f"{base_path}/preview.schema.json")
        dependencies = [
            (str(item.get("component_code") or "").strip(), cls.coerce_int(item.get("version_no")) or 1)
            for item in metadata.get("dependencies", [])
            if isinstance(item, dict) and str(item.get("component_code") or "").strip()
        ]
        return PackageComponent(
            source_component_code=str(metadata.get("source_component_code") or component_code).strip(),
            source_version_no=cls.coerce_int(metadata.get("source_version_no")) or 1,
            metadata=metadata,
            content=content,
            preview_schema=preview_schema,
            dependencies=dependencies,
            asset_names=[str(item).strip() for item in metadata.get("asset_names", []) if str(item).strip()],
            font_asset_names=[str(item).strip() for item in metadata.get("font_asset_names", []) if str(item).strip()],
            content_hash=str(metadata.get("content_hash") or "").strip() or None,
            preview_schema_hash=str(metadata.get("preview_schema_hash") or "").strip() or None,
            component_fingerprint=str(metadata.get("component_fingerprint") or "").strip() or None,
            fingerprint_schema_version=cls.coerce_int(metadata.get("fingerprint_schema_version")),
        )

    @classmethod
    def read_package_asset(cls, archive: zipfile.ZipFile, file_hash: str) -> PackageAsset:
        """读取模板包内单个资源。"""

        base_path = f"assets/{file_hash}"
        metadata = cls.read_object_json(archive, f"{base_path}/asset.json")
        original_name = cls.safe_archive_filename(str(metadata.get("original_name") or "asset.bin"))
        content = cls.read_bytes(archive, f"{base_path}/{original_name}")
        return PackageAsset(metadata=metadata, content=content)

    @classmethod
    def read_screenshot_files(
        cls,
        archive: zipfile.ZipFile,
        screenshots: dict[str, Any],
        names: set[str],
    ) -> dict[str, bytes]:
        """按截图清单读取截图文件，缺失时在解析阶段阻断。"""

        paths: list[str] = []
        cover = screenshots.get("cover")
        if isinstance(cover, dict):
            paths.append(str(cover.get("path") or "").strip())
        pages = screenshots.get("pages")
        if isinstance(pages, list):
            for item in pages:
                if isinstance(item, dict):
                    paths.append(str(item.get("path") or "").strip())
        result: dict[str, bytes] = {}
        for path in [item for item in paths if item]:
            normalized = cls.normalize_zip_name(path)
            if normalized not in names:
                raise AppException(status_code=400, code="PROJECT_TEMPLATE_SCREENSHOT_MISSING", detail=f"模板截图文件缺失：{normalized}。")
            result[normalized] = cls.read_bytes(archive, normalized)
        return result

    @classmethod
    def read_object_json(cls, archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
        """读取并校验 ZIP 中的 JSON 对象。"""

        payload = cls.read_json(archive, name)
        if not isinstance(payload, dict):
            raise AppException(status_code=400, code="PROJECT_TEMPLATE_PACKAGE_INVALID", detail=f"{name} 必须是 JSON 对象。")
        return payload

    @classmethod
    def read_json(cls, archive: zipfile.ZipFile, name: str) -> dict[str, Any] | list[Any]:
        """读取 ZIP 中的 JSON 文件。"""

        try:
            return json.loads(cls.read_text(archive, name))
        except json.JSONDecodeError as error:
            raise AppException(status_code=400, code="PROJECT_TEMPLATE_PACKAGE_INVALID", detail=f"{name} 不是合法 JSON。") from error

    @classmethod
    def read_text(cls, archive: zipfile.ZipFile, name: str) -> str:
        """读取 ZIP 中的 UTF-8 文本。"""

        try:
            return cls.read_bytes(archive, name).decode("utf-8")
        except UnicodeDecodeError as error:
            raise AppException(status_code=400, code="PROJECT_TEMPLATE_PACKAGE_INVALID", detail=f"{name} 不是合法 UTF-8 文本。") from error

    @staticmethod
    def read_bytes(archive: zipfile.ZipFile, name: str) -> bytes:
        """读取 ZIP 中的二进制文件。"""

        normalized = ProjectTemplatePackageFormat.normalize_zip_name(name)
        try:
            return archive.read(normalized)
        except KeyError as error:
            raise AppException(status_code=400, code="PROJECT_TEMPLATE_PACKAGE_INVALID", detail=f"导入文件缺少文件：{normalized}。") from error

    @staticmethod
    def normalize_zip_name(name: str) -> str:
        """标准化 ZIP 内部路径，禁止绝对路径和上级目录。"""

        normalized = posixpath.normpath(str(name or "").replace("\\", "/")).lstrip("/")
        if normalized == "." or normalized.startswith("../") or "/../" in normalized:
            raise AppException(status_code=400, code="PROJECT_TEMPLATE_PACKAGE_PATH_INVALID", detail="导入文件包含非法路径。")
        return normalized

    @staticmethod
    def safe_archive_filename(name: str) -> str:
        """把展示文件名规整为 ZIP 内安全单文件名。"""

        filename = Path(str(name or "asset.bin").replace("\\", "/")).name
        return filename or "asset.bin"

    @staticmethod
    def dump_json(value: Any) -> str:
        """按项目约定输出 UTF-8 友好的格式化 JSON。"""

        return json.dumps(value, ensure_ascii=False, indent=2)

    @staticmethod
    def coerce_int(value: Any) -> int | None:
        """把输入值转为整数，失败时返回空。"""

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def resolve_page_codes(manifest: dict[str, Any], names: set[str]) -> list[str]:
        """从 manifest 或目录结构解析包内页面编码。"""

        codes = [
            str(item.get("source_page_code") or "").strip()
            for item in manifest.get("pages", [])
            if isinstance(item, dict)
        ]
        if not codes:
            codes = sorted({
                parts[1]
                for name in names
                if (parts := name.split("/")) and len(parts) >= 3 and parts[0] == "pages"
            })
        return [item for item in dict.fromkeys(codes) if item]

    @staticmethod
    def resolve_component_codes(manifest: dict[str, Any], names: set[str]) -> list[str]:
        """从 manifest 或目录结构解析包内组件编码。"""

        codes = [
            str(item.get("source_component_code") or item.get("component_code") or "").strip()
            for item in manifest.get("components", [])
            if isinstance(item, dict)
        ]
        if not codes:
            codes = sorted({
                parts[1]
                for name in names
                if (parts := name.split("/")) and len(parts) >= 3 and parts[0] == "components"
            })
        return [item for item in dict.fromkeys(codes) if item]

    @staticmethod
    def resolve_keys(manifest: dict[str, Any], names: set[str], section: str, key_field: str) -> list[str]:
        """从 manifest 或目录结构解析 key 类目录。"""

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
        return [item for item in dict.fromkeys(keys) if item]

    @staticmethod
    def resolve_asset_hashes(manifest: dict[str, Any], names: set[str]) -> list[str]:
        """从 manifest 或目录结构解析包内资源 hash。"""

        hashes = [
            str(item.get("file_hash") or "").strip()
            for item in manifest.get("assets", [])
            if isinstance(item, dict)
        ]
        if not hashes:
            hashes = sorted({
                parts[1]
                for name in names
                if (parts := name.split("/")) and len(parts) >= 3 and parts[0] == "assets"
            })
        return [item for item in dict.fromkeys(hashes) if item]

    @staticmethod
    def _ensure_required_files(names: set[str]) -> None:
        """校验模板包必须包含的根文件。"""

        required = {
            "manifest.json",
            "metadata/template.json",
            "metadata/screenshots.json",
            "project/project.json",
            "project/routes.json",
        }
        missing = sorted(required - names)
        if missing:
            raise AppException(status_code=400, code="PROJECT_TEMPLATE_PACKAGE_INVALID", detail=f"导入文件缺少文件：{', '.join(missing)}。")
