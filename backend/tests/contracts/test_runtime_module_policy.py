"""文件功能：验证 Backend 按 Runtime Kit manifest 执行远程模块导入边界校验。"""

from app.core.runtime_module_policy import (
    build_runtime_module_resolver_config,
    is_runtime_public_local_module,
    is_runtime_public_local_module_path,
    list_runtime_kit_capabilities,
    list_runtime_kit_component_capabilities,
    load_runtime_kit_manifest,
    normalize_runtime_module_path,
)


def test_runtime_kit_manifest_loader_should_expose_public_contract() -> None:
    """manifest loader 应读取 Runtime 提供的公开清单，且不包含 PDF 壳层能力。"""

    manifest = load_runtime_kit_manifest()
    export_paths = {item["import_path"] for item in manifest["exports"]}

    assert manifest["alias"] == "@runtime-kit"
    assert "@runtime-kit/public/components/assets/AssetImage.vue" in export_paths
    assert "@runtime-kit/public/components/primitives/Icon.vue" in export_paths
    assert not any("PDF" in path or "runtime-shell" in path for path in export_paths)
    assert not any("component-preview" in path for path in export_paths)


def test_runtime_kit_component_capabilities_should_be_enabled_previewable_components() -> None:
    """组件能力目录应只包含 kind=component 的 enabled 能力，并保留 previewable 标记。"""

    capabilities = list_runtime_kit_component_capabilities()
    names = {item["name"] for item in capabilities}

    assert "Icon" in names
    assert "DefaultContainer" in names
    assert "Connector" in names
    assert any(item["name"] == "Connector" and item["previewable"] is False for item in capabilities)
    assert all(item["manifest_version"] == "1.0.0" for item in capabilities)
    assert all(item["import_path"].startswith("@runtime-kit/") for item in capabilities)
    assert all(item["kind"] == "component" for item in capabilities)


def test_runtime_kit_capability_directory_should_include_doc_only_items() -> None:
    """能力目录应包含 composable/util/type 的 doc-only 条目。"""

    capabilities = list_runtime_kit_capabilities()
    by_name = {item["name"]: item for item in capabilities}

    assert by_name["usePageSize"]["kind"] == "composable"
    assert by_name["usePageSize"]["previewable"] is False
    assert len(by_name["usePageSize"]["usage"]) >= 1
    assert len(by_name["usePageSize"]["return_example"]) >= 1
    assert len(by_name["usePageSize"]["constraints"]) >= 1
    assert "ComponentPreviewSchema" not in by_name
    assert "useComponentPreviewMock" not in by_name


def test_runtime_public_local_module_should_be_manifest_based() -> None:
    """Runtime 本地公共模块校验应只接受 manifest 中的 @runtime-kit 路径。"""

    assert is_runtime_public_local_module("@runtime-kit/public/components/assets/AssetImage.vue") is True
    assert is_runtime_public_local_module("@runtime-kit/public/components/primitives/Icon.vue") is True
    assert is_runtime_public_local_module("@runtime-kit/public/components/primitives/Unknown.vue") is False
    assert is_runtime_public_local_module("@runtime-kit/public/types/component-preview") is False
    assert is_runtime_public_local_module("@runtime-kit/public/composables/component-preview/useComponentPreviewMock") is False
    assert is_runtime_public_local_module("@/components/common/AppIcon.vue") is False
    assert is_runtime_public_local_module("@/core/utils/path") is False


def test_runtime_module_path_normalization_should_support_runtime_kit_alias() -> None:
    """路径规范化应支持 @runtime-kit，但公共模块判断仍由 manifest 控制。"""

    assert normalize_runtime_module_path("@runtime-kit/public/components/assets/AssetImage.vue") == (
        "src/runtime-kit/public/components/assets/AssetImage.vue"
    )
    assert is_runtime_public_local_module_path("src/runtime-kit/public/components/assets/AssetImage.vue") is True
    assert is_runtime_public_local_module_path("src/runtime-kit/public/components/assets/Missing.vue") is False


def test_runtime_module_resolver_config_should_publish_manifest_snapshot() -> None:
    """下发给 Runtime 的 resolver 配置应包含 Runtime Kit manifest 快照。"""

    resolver_config = build_runtime_module_resolver_config()
    export_paths = {item["import_path"] for item in resolver_config["runtime_kit_exports"]}

    assert resolver_config["remote_component_prefix"] == "@workspace-components/"
    assert resolver_config["runtime_kit_alias"] == "@runtime-kit"
    assert resolver_config["runtime_kit_manifest_version"] == "1.0.0"
    assert "@runtime-kit/public/utils/assets" in export_paths
    assert "@runtime-kit/internal/renderers/ImageViewer.vue" not in export_paths
    assert "@runtime-kit/public/types/component-preview" not in export_paths
