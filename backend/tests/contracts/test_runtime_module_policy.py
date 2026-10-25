"""文件功能：验证 Backend 按 Runtime Kit manifest 执行远程模块导入边界校验。"""

import json
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.core.runtime_module_policy import (
    build_runtime_module_resolver_config,
    get_runtime_kit_capability_by_import_path,
    is_runtime_public_local_module,
    is_runtime_public_local_module_path,
    list_runtime_kit_capabilities,
    list_runtime_kit_component_capabilities,
    load_runtime_kit_manifest,
    normalize_runtime_module_path,
)
from app.schemas import audio as audio_schema


def test_runtime_kit_manifest_loader_should_expose_public_contract() -> None:
    """manifest loader 应读取 Runtime 提供的公开清单，且不包含 PDF 壳层能力。"""

    manifest = load_runtime_kit_manifest()
    export_paths = {item["import_path"] for item in manifest["exports"]}

    assert manifest["alias"] == "@runtime-kit"
    assert "@runtime-kit/public/components/assets/AssetImage.v1.vue" in export_paths
    assert "@runtime-kit/public/components/primitives/Icon.v1.vue" in export_paths
    assert "@runtime-kit/public/components/primitives/ThemeLogo.v1.vue" in export_paths
    assert not any("PDF" in path or "runtime-shell" in path for path in export_paths)
    assert not any("component-preview" in path for path in export_paths)


def test_runtime_kit_component_capabilities_should_be_enabled_previewable_components() -> None:
    """组件能力目录应只包含 kind=component 的 enabled 能力，并保留 previewable 标记。"""

    capabilities = list_runtime_kit_component_capabilities()
    names = {item["name"] for item in capabilities}

    assert "Icon.v1" in names
    assert "ThemeLogo.v1" in names
    assert "DefaultContainer.v1" in names
    assert "Connector.v1" in names
    assert any(item["name"] == "Connector.v1" and item["previewable"] is False for item in capabilities)
    assert all(item["manifest_version"] == "1.0.0" for item in capabilities)
    assert all(item["import_path"].startswith("@runtime-kit/") for item in capabilities)
    assert all(item["kind"] == "component" for item in capabilities)
    assert all(item["name"] == f"{item['base_name']}.v{item['version_no']}" for item in capabilities)


def test_runtime_kit_capability_directory_should_include_doc_only_items() -> None:
    """能力目录应包含 composable/util/type 的 doc-only 条目。"""

    capabilities = list_runtime_kit_capabilities()
    by_name = {item["name"]: item for item in capabilities}

    assert by_name["usePageSize.v1"]["kind"] == "composable"
    assert by_name["usePageSize.v1"]["previewable"] is False
    assert len(by_name["usePageSize.v1"]["usage"]) >= 1
    assert len(by_name["usePageSize.v1"]["return_example"]) >= 1
    assert len(by_name["usePageSize.v1"]["constraints"]) >= 1
    for name in ("usePageTimeline.v1", "AssetAudio.v2", "AssetVideo.v2", "AssetModel.v2"):
        assert by_name[name]["previewable"] is False
        assert by_name[name]["usage"]
    assert "ComponentPreviewSchema" not in by_name
    assert "useComponentPreviewMock" not in by_name


def test_audio_cue_capability_directory_follows_development_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """cue 目录项仅在音效能力开放时展示，避免生产环境推荐无法保存的用法。"""

    monkeypatch.setenv("AUDIO_DEV_CAPABILITIES_ENABLED", "false")
    get_settings.cache_clear()
    try:
        assert "useAudioCue.v1" not in {item["name"] for item in list_runtime_kit_capabilities()}
        monkeypatch.setenv("AUDIO_DEV_CAPABILITIES_ENABLED", "true")
        get_settings.cache_clear()
        assert "useAudioCue.v1" in {item["name"] for item in list_runtime_kit_capabilities()}
    finally:
        get_settings.cache_clear()


def test_audio_cue_disclosure_follows_audio_capability_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """未开放 cue 时能力目录不披露，联合验收开启后才允许内容助手发现。"""

    monkeypatch.setattr(
        audio_schema,
        "get_open_audio_capabilities",
        lambda: frozenset({audio_schema.AUDIO_CAPABILITY_AUDIO_ASSETS}),
    )
    assert "useAudioCue.v1" not in {item["name"] for item in list_runtime_kit_capabilities()}

    monkeypatch.setattr(
        audio_schema,
        "get_open_audio_capabilities",
        lambda: frozenset(audio_schema.AUDIO_MILESTONE_CAPABILITIES["m2"]),
    )
    assert "useAudioCue.v1" in {item["name"] for item in list_runtime_kit_capabilities()}


def test_runtime_kit_capability_directory_should_filter_latest_versions(tmp_path: Path) -> None:
    """能力目录默认只返回每个 base_name 的最新版本，并支持按版本号筛选。"""

    manifest_path = tmp_path / "runtime-kit.manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "alias": "@runtime-kit",
                "exports": [
                    _build_manifest_item("Icon", 1),
                    _build_manifest_item("Icon", 2),
                    _build_manifest_item("ThemeLogo", 1),
                ],
            }
        ),
        encoding="utf-8",
    )

    latest = list_runtime_kit_capabilities(manifest_path)
    assert [item["name"] for item in latest] == ["Icon.v2", "ThemeLogo.v1"]

    versioned = list_runtime_kit_capabilities(manifest_path, base_name="Icon", version_no=1, include_all_versions=True)
    assert [item["name"] for item in versioned] == ["Icon.v1"]


def test_runtime_public_local_module_should_be_manifest_based() -> None:
    """Runtime 本地公共模块校验应只接受 manifest 中的 @runtime-kit 路径。"""

    assert is_runtime_public_local_module("@runtime-kit/public/components/assets/AssetImage.v1.vue") is True
    assert is_runtime_public_local_module("@runtime-kit/public/components/primitives/Icon.v1.vue") is True
    assert is_runtime_public_local_module("@runtime-kit/public/components/primitives/ThemeLogo.v1.vue") is True
    assert is_runtime_public_local_module("@runtime-kit/public/components/primitives/Icon.vue") is False
    assert is_runtime_public_local_module("@runtime-kit/public/components/primitives/Unknown.vue") is False
    assert is_runtime_public_local_module("@runtime-kit/public/types/component-preview") is False
    assert is_runtime_public_local_module("@runtime-kit/public/composables/component-preview/useComponentPreviewMock") is False
    assert is_runtime_public_local_module("@/components/common/AppIcon.vue") is False
    assert is_runtime_public_local_module("@/core/utils/path") is False


def test_runtime_module_path_normalization_should_support_runtime_kit_alias() -> None:
    """路径规范化应支持 @runtime-kit，但公共模块判断仍由 manifest 控制。"""

    assert normalize_runtime_module_path("@runtime-kit/public/components/assets/AssetImage.v1.vue") == (
        "src/runtime-kit/public/components/assets/AssetImage.v1.vue"
    )
    assert is_runtime_public_local_module_path("src/runtime-kit/public/components/assets/AssetImage.v1.vue") is True
    assert is_runtime_public_local_module_path("src/runtime-kit/public/components/assets/Missing.vue") is False


def test_runtime_kit_import_path_should_resolve_versioned_capability_metadata() -> None:
    """版本化 Runtime Kit import_path 应能解析出依赖索引需要的能力元数据。"""

    dependency = get_runtime_kit_capability_by_import_path("@runtime-kit/public/components/primitives/Icon.v1.vue")

    assert dependency is not None
    assert dependency.name == "Icon.v1"
    assert dependency.base_name == "Icon"
    assert dependency.version_no == 1
    assert dependency.import_path == "@runtime-kit/public/components/primitives/Icon.v1.vue"
    assert get_runtime_kit_capability_by_import_path("@runtime-kit/public/components/primitives/Icon.vue") is None


def test_runtime_module_resolver_config_should_publish_manifest_snapshot() -> None:
    """下发给 Runtime 的 resolver 配置应包含 Runtime Kit manifest 快照。"""

    resolver_config = build_runtime_module_resolver_config()
    export_paths = {item["import_path"] for item in resolver_config["runtime_kit_exports"]}

    assert resolver_config["remote_component_prefix"] == "@workspace-components/"
    assert resolver_config["runtime_kit_alias"] == "@runtime-kit"
    assert resolver_config["runtime_kit_manifest_version"] == "1.0.0"
    assert "@runtime-kit/public/utils/assets.v1" in export_paths
    assert "@runtime-kit/internal/renderers/ImageViewer.vue" not in export_paths
    assert "@runtime-kit/public/types/component-preview" not in export_paths


def _build_manifest_item(base_name: str, version_no: int) -> dict[str, object]:
    """构造测试用 Runtime Kit manifest 能力项。"""

    return {
        "kind": "component",
        "base_name": base_name,
        "version_no": version_no,
        "name": f"{base_name}.v{version_no}",
        "import_path": f"@runtime-kit/public/components/primitives/{base_name}.v{version_no}.vue",
        "category": "runtime",
        "description": base_name,
        "capability": {
            "enabled": True,
            "previewable": True,
            "recommendation_level": "default",
            "display_name": base_name,
            "summary": base_name,
            "tags": [],
            "usage": [],
            "returns": "",
            "return_example": [],
            "constraints": ["测试约束"],
            "audiences": ["backend", "agent"],
        },
    }


def test_runtime_kit_manifest_model3d_engine_identity_should_match_runtime_package() -> None:
    """清单三维引擎身份必须与后端接受策略版本和 Runtime three 依赖版本一致。"""

    import json
    from pathlib import Path

    from app.services.model3d_acceptance_policy import MODEL3D_ACCEPTANCE_POLICY

    manifest = load_runtime_kit_manifest()
    engine_identity = manifest["model3d_engine"]
    assert engine_identity["validationProfile"] == MODEL3D_ACCEPTANCE_POLICY.validation_profile

    repo_root = Path(__file__).resolve().parents[3]
    runtime_package = json.loads((repo_root / "runtime" / "package.json").read_text(encoding="utf-8"))
    assert engine_identity["engineVersion"] == runtime_package["dependencies"]["three"]
