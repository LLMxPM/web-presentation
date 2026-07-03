"""文件功能：验证项目模板包服务的导出预检摘要构造逻辑。"""

from __future__ import annotations

from app.models.page import Page
from app.models.workspace import Project
from app.models.workspace_theme import WorkspaceTheme
from app.schemas.project_template import ProjectTemplateExportRequest
from app.services.component_share_package_models import ExportAssetCollection
from app.services.project_template_package_service import (
    ProjectTemplateExportPlan,
    ProjectTemplatePackageService,
)


async def test_project_template_export_validation_should_include_theme_summary() -> None:
    """导出预检包含主题时应正常构造主题摘要，不触发运行时 NameError。"""

    service = ProjectTemplatePackageService.__new__(ProjectTemplatePackageService)
    validation = await service._build_export_validation(
        _build_export_plan_with_theme(),
        ProjectTemplateExportRequest(),
    )

    assert validation.can_export is True
    assert validation.themes[0].key == "brand-theme"
    assert validation.themes[0].name == "品牌主题"
    assert validation.themes[0].action == "export"


def test_project_template_metadata_should_use_project_fields_and_current_user() -> None:
    """导出 metadata 只包含项目真实字段，并把 author 固定为当前用户显示名。"""

    service = ProjectTemplatePackageService.__new__(ProjectTemplatePackageService)
    metadata = service._build_template_metadata(
        _build_export_plan_with_theme(),
        ProjectTemplateExportRequest(),
        "runtime-test",
        "平台系统管理员",
    )

    assert metadata["slug"] == "project-template"
    assert metadata["name"] == "模板项目"
    assert metadata["author"] == "平台系统管理员"
    assert metadata["page_count"] == 1
    assert metadata["aspect_ratio"] == "16:9"
    assert metadata["runtime_kit_manifest_version"] == "runtime-test"
    assert not {
        "language",
        "license",
        "content_types",
        "style_keywords",
        "category",
        "tags",
    }.intersection(metadata)


def _build_export_plan_with_theme() -> ProjectTemplateExportPlan:
    """构造带主题的最小导出计划。"""

    project = Project(
        id=18,
        workspace_id=3,
        code="PRJ_TEMPLATE",
        name="模板项目",
        description=None,
        page_width=1920,
        page_height=1080,
        base_font_size="20px",
        icon_default_stroke_width=2,
        show_pdf_export_button=True,
        menu_mode="preview",
        theme_key="brand-theme",
        theme_config_yaml="themes: {}\n",
        style_spec_markdown="",
        build_extra_assets_json={"asset_names": []},
    )
    page = Page(
        id=30,
        workspace_id=3,
        project_id=18,
        code="PAGE_COVER",
        title="封面",
        summary=None,
        speaker_notes=None,
        file_type="vue",
        page_content="<template><main>封面</main></template>",
        current_version_no=1,
    )
    theme = WorkspaceTheme(
        workspace_id=3,
        key="brand-theme",
        name="品牌主题",
    )
    asset_collection = ExportAssetCollection(
        assets=[],
        automatic_asset_names=[],
        manual_asset_names=[],
        missing_static_asset_names=[],
        missing_manual_asset_names=[],
        dynamic_resource_components=[],
        warnings=[],
    )
    return ProjectTemplateExportPlan(
        project=project,
        pages=[page],
        routes=[],
        component_snapshots=[],
        component_asset_collection=asset_collection,
        assets=[],
        themes=[theme],
        font_configs=[],
        automatic_asset_names=[],
        manual_asset_names=[],
        missing_asset_names=[],
        dynamic_resource_modules=[],
        warnings=[],
    )
