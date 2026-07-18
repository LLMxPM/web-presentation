"""文件功能：验证页面可视化组件 schema 使用本地标签和真实钉住版本且不读取组件草稿。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.exceptions import AppException
from app.repositories.module_dependency_repository import ResolvedComponentDependency
from app.services.component_dependency_service import (
    ComponentDependencyService,
    ParsedDefaultImportBinding,
    ParsedModuleDependencies,
)
from app.services.page_visual_edit_component_schema_service import (
    PageVisualEditComponentSchemaService,
)


PAGE_SOURCE = """<script setup lang="ts">
import LocalCard from '@workspace-components/CMP001/v/1'
</script>
<template><LocalCard /></template>"""


def _build_service(*, preview_schema: str | None):
    """构造依赖解析、精确版本仓储和页面替身。"""

    dependency_service = SimpleNamespace(
        parse_dependencies=Mock(
            return_value=ParsedModuleDependencies(
                component_imports=(("CMP001", 1),),
                runtime_local_imports=tuple(),
                page_module_imports=tuple(),
            )
        ),
        resolve_component_dependencies=AsyncMock(
            return_value=[
                ResolvedComponentDependency(
                    component_id=21,
                    component_version_id=101,
                    component_code="CMP001",
                    component_version_no=1,
                )
            ]
        ),
        parse_default_import_bindings=Mock(
            return_value=(
                ParsedDefaultImportBinding(
                    local_name="LocalCard",
                    import_path="@workspace-components/CMP001/v/1",
                ),
            )
        ),
    )
    version_repository = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value=SimpleNamespace(
                id=101,
                component_id=21,
                version_no=1,
                preview_schema=preview_schema,
            )
        )
    )
    service = PageVisualEditComponentSchemaService(
        SimpleNamespace(),
        dependency_service=dependency_service,
        component_version_repository=version_repository,
    )
    page = SimpleNamespace(
        code="PG001",
        file_type="vue",
        page_content=PAGE_SOURCE,
        workspace_id=7,
    )
    return service, page, dependency_service, version_repository


@pytest.mark.asyncio
async def test_component_schema_should_use_exact_pinned_version_and_local_name() -> (
    None
):
    """映射 key 应为 import 本地名，props 来自解析得到的 v1 版本而非当前组件草稿。"""

    preview_schema = """
    {
      "props": {
        "variant": {
          "type": "select",
          "label": "样式",
          "options": [{"label": "强调", "value": "strong"}],
          "default": "strong",
          "agent_visible": false
        },
        "count": {"type": "number", "default": 2},
        "enabled": {"type": "boolean", "default": true}
      },
      "slots": {"default": {"default": []}},
      "presets": []
    }
    """
    service, page, dependency_service, version_repository = _build_service(
        preview_schema=preview_schema
    )

    result = await service.build_for_page(page=page)

    assert set(result) == {"LocalCard"}
    component_schema = result["LocalCard"]
    assert component_schema.source == "workspace_component"
    assert component_schema.component_code == "CMP001"
    assert component_schema.version_no == 1
    assert component_schema.props is not None
    assert set(component_schema.props) == {"variant", "count", "enabled"}
    assert component_schema.props["variant"].options[0].value == "strong"
    assert "agent_visible" not in component_schema.props["variant"].model_dump()
    dependency_service.resolve_component_dependencies.assert_awaited_once_with(
        workspace_id=7,
        component_refs=(("CMP001", 1),),
        source_label="页面 PG001",
    )
    version_repository.get_by_id.assert_awaited_once_with(101)


@pytest.mark.asyncio
async def test_component_schema_should_expose_null_props_when_pinned_version_has_no_schema() -> (
    None
):
    """钉住版本没有 previewSchema 时仍下发来源身份，并明确 props 为 null。"""

    service, page, _, _ = _build_service(preview_schema=None)

    result = await service.build_for_page(page=page)

    assert result["LocalCard"].props is None


@pytest.mark.asyncio
async def test_component_schema_should_read_runtime_kit_manifest_by_import_path() -> (
    None
):
    """Runtime Kit 默认导入应直接消费 manifest 的组件 preview_schema，不维护第二份清单。"""

    page = SimpleNamespace(
        code="PG002",
        file_type="vue",
        workspace_id=7,
        page_content="""<script setup>
import LocalAssetImage from '@runtime-kit/public/components/assets/AssetImage.v1.vue'
</script><template><LocalAssetImage /></template>""",
    )
    service = PageVisualEditComponentSchemaService(SimpleNamespace())

    result = await service.build_for_page(page=page)

    runtime_schema = result["LocalAssetImage"]
    assert runtime_schema.source == "runtime_kit"
    assert runtime_schema.component_code == "AssetImage"
    assert runtime_schema.version_no == 1
    assert runtime_schema.props is not None
    assert runtime_schema.props["fit"].type == "select"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "detail"),
    [
        ("REMOTE_COMPONENT_NOT_FOUND", "组件不属于页面工作空间。"),
        ("REMOTE_COMPONENT_VERSION_NOT_FOUND", "组件钉住版本不存在。"),
    ],
)
async def test_component_schema_should_preserve_existing_dependency_boundary_errors(
    error_code: str,
    detail: str,
) -> None:
    """跨工作空间或错版本必须沿用页面依赖边界失败，不得回退当前组件版本。"""

    service, page, dependency_service, version_repository = _build_service(
        preview_schema=None
    )
    dependency_service.resolve_component_dependencies.side_effect = AppException(
        status_code=400,
        code=error_code,
        detail=detail,
    )

    with pytest.raises(AppException) as exc_info:
        await service.build_for_page(page=page)

    assert exc_info.value.code == error_code
    version_repository.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_component_schema_should_not_fallback_when_resolved_version_row_is_missing() -> (
    None
):
    """依赖解析得到的钉住版本记录缺失时必须失败，不得读取组件最新版本替代。"""

    service, page, _, version_repository = _build_service(preview_schema=None)
    version_repository.get_by_id.return_value = None

    with pytest.raises(AppException) as exc_info:
        await service.build_for_page(page=page)

    assert exc_info.value.code == "REMOTE_COMPONENT_VERSION_NOT_FOUND"
    version_repository.get_by_id.assert_awaited_once_with(101)


def test_default_import_parser_should_omit_named_and_ambiguous_local_bindings() -> None:
    """命名别名和重复本地名不能可靠定位默认组件，应保持不下发。"""

    source = """<script setup>
import { default as NamedAlias } from '@workspace-components/CMP001/v/1'
import Duplicate from '@workspace-components/CMP001/v/1'
import Duplicate from '@workspace-components/CMP002/v/1'
import Reliable from '@workspace-components/CMP003/v/1'
</script>"""

    bindings = ComponentDependencyService(
        SimpleNamespace()
    ).parse_default_import_bindings(source)

    assert bindings == (
        ParsedDefaultImportBinding(
            local_name="Reliable",
            import_path="@workspace-components/CMP003/v/1",
        ),
    )
