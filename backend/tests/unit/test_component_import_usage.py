"""文件功能：测试工作空间组件导入路径生成以及响应模型 import_usage 自动填充逻辑。"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from app.ai.code_standards import get_default_code_standard
from app.core.component_import import build_component_import_usage, to_valid_import_identifier
from app.models.enums import PageFileType, RecordStatus, WorkspaceComponentType
from app.schemas.component import SuggestedComponentItem, WorkspaceComponentItem


@pytest.mark.unit
def test_to_valid_import_identifier() -> None:
    """验证组件导入标识符生成与归一化。"""

    assert to_valid_import_identifier("sales-metric-card") == "SalesMetricCard"
    assert to_valid_import_identifier("123card") == "Component123card"
    assert to_valid_import_identifier("MetricCard") == "MetricCard"
    assert to_valid_import_identifier("") == ""
    assert to_valid_import_identifier(None) == ""


@pytest.mark.unit
def test_build_component_import_usage() -> None:
    """验证组件导入路径与 import 语句构造。"""

    usage = build_component_import_usage("CMP20260503001", 3, component_name="指标卡", import_name="SalesMetricCard")
    assert usage["import_path"] == "@workspace-components/CMP20260503001/v/3"
    assert usage["import_statement"] == "import SalesMetricCard from '@workspace-components/CMP20260503001/v/3'"


@pytest.mark.unit
def test_workspace_component_item_populates_import_usage() -> None:
    """验证已发布工作空间组件响应模型自动生成 import_path 与 import_statement。"""

    published_item = WorkspaceComponentItem(
        id=1,
        workspace_id=1,
        code="CMP20260503001",
        content="<template><div></div></template>",
        preview_schema=None,
        current_version_no=2,
        draft_base_version_no=2,
        has_unpublished_changes=False,
        published_at=datetime.now(timezone.utc),
        file_type=PageFileType.VUE,
        name="核心指标卡",
        import_name="MetricCard",
        component_type=WorkspaceComponentType.CONTENT_COMPONENT,
        summary="测试摘要",
        status=RecordStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        created_by=1,
        updated_by=1,
    )
    assert published_item.import_path == "@workspace-components/CMP20260503001/v/2"
    assert published_item.import_statement == "import MetricCard from '@workspace-components/CMP20260503001/v/2'"

    draft_item = WorkspaceComponentItem(
        id=2,
        workspace_id=1,
        code="CMP20260503002",
        content="<template><div></div></template>",
        preview_schema=None,
        current_version_no=0,
        draft_base_version_no=0,
        has_unpublished_changes=True,
        published_at=None,
        file_type=PageFileType.VUE,
        name="未发布卡片",
        import_name="DraftCard",
        component_type=WorkspaceComponentType.CONTENT_COMPONENT,
        summary="草稿摘要",
        status=RecordStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        created_by=1,
        updated_by=1,
    )
    assert draft_item.import_path is None
    assert draft_item.import_statement is None


@pytest.mark.unit
def test_suggested_component_item_populates_import_usage() -> None:
    """验证建议组件响应模型自动填充 import_path 与 import_statement。"""

    suggested = SuggestedComponentItem(
        id=10,
        code="CMP_SUGGESTED",
        name="建议卡片",
        import_name="SuggestedCard",
        component_type=WorkspaceComponentType.CONTENT_COMPONENT,
        summary="建议摘要",
        current_version_no=1,
    )
    assert suggested.import_path == "@workspace-components/CMP_SUGGESTED/v/1"
    assert suggested.import_statement == "import SuggestedCard from '@workspace-components/CMP_SUGGESTED/v/1'"


@pytest.mark.unit
def test_code_standards_include_component_import_rules() -> None:
    """验证代码规范中包含工作空间组件引用格式说明。"""

    page_standard = get_default_code_standard("page")
    assert "@workspace-components/<component_code>/v/<version_no>" in page_standard
    component_standard = get_default_code_standard("component")
    assert "@workspace-components/<component_code>/v/<version_no>" in component_standard
