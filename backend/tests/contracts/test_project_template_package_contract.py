"""文件功能：验证项目模板包 v1 的 ZIP 结构、元数据和截图清单契约。"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime

import pytest

from app.core.exceptions import AppException
from app.schemas.project_template import (
    PROJECT_TEMPLATE_PACKAGE_SCHEMA_VERSION,
    PROJECT_TEMPLATE_PACKAGE_TYPE,
)
from app.services.project_template_package_format import ProjectTemplatePackageFormat


def test_project_template_package_v1_should_expose_library_metadata_contract() -> None:
    """模板包 v1 应稳定暴露外部模板库可读取的 manifest、元数据和截图清单。"""

    archive_content = _build_minimal_template_package()

    parsed = ProjectTemplatePackageFormat.parse_package(archive_content)

    assert parsed.manifest["package_type"] == PROJECT_TEMPLATE_PACKAGE_TYPE
    assert parsed.manifest["schema_version"] == PROJECT_TEMPLATE_PACKAGE_SCHEMA_VERSION
    assert parsed.manifest["template_path"] == "metadata/template.json"
    assert parsed.manifest["screenshots_path"] == "metadata/screenshots.json"
    assert parsed.template["slug"] == "modern-business-report"
    assert parsed.template["name"] == "现代商业报告"
    assert parsed.template["author"] == "平台系统管理员"
    assert parsed.template["page_count"] == 1
    assert parsed.template["aspect_ratio"] == "16:9"
    assert not {
        "language",
        "license",
        "content_types",
        "style_keywords",
        "category",
        "tags",
    }.intersection(parsed.template)
    assert parsed.screenshots["cover"]["path"] == "screenshots/cover.png"
    assert parsed.screenshots["pages"][0]["source_page_code"] == "page_cover"
    assert set(parsed.screenshot_files) == {
        "screenshots/cover.png",
        "screenshots/pages/page_cover.png",
    }
    assert parsed.pages[0].source_page_code == "page_cover"
    assert parsed.pages[0].content == "<template><main>cover</main></template>"


def test_project_template_package_should_reject_zip_path_traversal() -> None:
    """模板包解析器应拒绝 ZIP 内部上级目录路径。"""

    archive_content = _build_zip({"../manifest.json": "{}"})

    with pytest.raises(AppException) as error:
        ProjectTemplatePackageFormat.parse_package(archive_content)

    assert error.value.code == "PROJECT_TEMPLATE_PACKAGE_PATH_INVALID"


def _build_minimal_template_package() -> bytes:
    """构造最小可解析的项目模板包。"""

    exported_at = datetime(2026, 7, 3, tzinfo=UTC).isoformat()
    manifest = {
        "package_type": PROJECT_TEMPLATE_PACKAGE_TYPE,
        "schema_version": PROJECT_TEMPLATE_PACKAGE_SCHEMA_VERSION,
        "exported_at": exported_at,
        "runtime_kit_manifest_version": "1.0.0",
        "template_path": "metadata/template.json",
        "screenshots_path": "metadata/screenshots.json",
        "project_path": "project/project.json",
        "routes_path": "project/routes.json",
        "page_count": 1,
        "component_count": 0,
        "asset_count": 0,
        "theme_count": 0,
        "font_count": 0,
        "pages": [{"source_page_code": "page_cover", "path": "pages/page_cover"}],
        "components": [],
        "assets": [],
        "themes": [],
        "fonts": [],
    }
    template = {
        "slug": "modern-business-report",
        "name": "现代商业报告",
        "summary": "适合季度复盘的多页演示模板。",
        "description": "更长的模板说明。",
        "author": "平台系统管理员",
        "page_count": 1,
        "page_width": 1920,
        "page_height": 1080,
        "aspect_ratio": "16:9",
        "runtime_kit_manifest_version": "1.0.0",
        "created_at": exported_at,
        "updated_at": exported_at,
    }
    screenshots = {
        "cover": {"path": "screenshots/cover.png", "width": 1920, "height": 1080},
        "pages": [
            {
                "source_page_code": "page_cover",
                "title": "封面",
                "path": "screenshots/pages/page_cover.png",
                "order": 1,
                "width": 1920,
                "height": 1080,
            }
        ],
    }
    project = {
        "source_project_code": "PRJ_TEMPLATE",
        "name": "现代商业报告",
        "description": "项目描述",
        "page_width": 1920,
        "page_height": 1080,
        "base_font_size": "16px",
        "icon_default_stroke_width": 2,
        "show_pdf_export_button": True,
        "menu_mode": "preview",
        "theme_key": None,
        "theme_config_yaml": "themes: {}\n",
        "style_spec_markdown": "",
        "build_extra_assets_json": {"asset_names": []},
        "suggested_reference_asset_names": [],
        "suggested_components": [],
    }
    page = {
        "source_page_code": "page_cover",
        "title": "封面",
        "summary": None,
        "speaker_notes": None,
        "file_type": "vue",
    }
    routes = {
        "routes": [
            {
                "route_type": "page",
                "route": "/",
                "order": 1,
                "hidden": False,
                "group_title": None,
                "source_page_code": "page_cover",
                "children": [],
            }
        ]
    }
    return _build_zip(
        {
            "manifest.json": json.dumps(manifest),
            "metadata/template.json": json.dumps(template, ensure_ascii=False),
            "metadata/screenshots.json": json.dumps(screenshots, ensure_ascii=False),
            "project/project.json": json.dumps(project, ensure_ascii=False),
            "project/routes.json": json.dumps(routes, ensure_ascii=False),
            "pages/page_cover/page.json": json.dumps(page, ensure_ascii=False),
            "pages/page_cover/index.vue": "<template><main>cover</main></template>",
            "screenshots/cover.png": b"png-cover",
            "screenshots/pages/page_cover.png": b"png-page",
        }
    )


def _build_zip(files: dict[str, str | bytes]) -> bytes:
    """按给定文件映射构造内存 ZIP。"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()
