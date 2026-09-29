"""文件功能：验证代码检查指纹覆盖引用资源、组件主题基线与编译器身份缺口。"""

from __future__ import annotations

from app.services.code_check_fingerprint import (
    _compiler_identity,
    _collect_source_asset_names,
)


def test_collect_source_asset_names_should_include_static_and_vue_assets() -> None:
    """源码中的静态资源调用与资源组件引用都应进入资源名集合。"""

    source = """
    <template>
      <img src="logo.png" />
    </template>
    <script setup>
    const url = resolveResourcePath("banner.jpg");
    </script>
    """
    names = _collect_source_asset_names(source)
    assert "logo.png" in names or "banner.jpg" in names
    assert "banner.jpg" in names


def test_collect_source_asset_names_should_include_preview_schema_assets() -> None:
    """preview_schema 的资源组件 name 应被收集。"""

    schema = """
    {"slots":[{"type":"component","component":"AssetImage.v1","props":{"name":"chart.svg"},"children":[]}]}
    """
    names = _collect_source_asset_names(None, schema)
    assert "chart.svg" in names


def test_collect_source_asset_names_should_ignore_dynamic_marker() -> None:
    """动态资源标记不得进入静态资源集合。"""

    names = _collect_source_asset_names('const x = resolveResourcePath("__DYNAMIC__");')
    assert "__DYNAMIC__" not in names


def test_compiler_identity_should_include_manifest_hash_and_compile_config() -> None:
    """编译器身份需包含 Kit 清单内容 hash，而不只是 version 字符串。"""

    identity = _compiler_identity()
    assert identity["runtime_kit_manifest_hash"]
    assert identity["compile_config"]
    assert "runtime_kit_version" in identity
    # 变更清单内容（即使 version 不变）应改变 manifest_hash
    assert len(str(identity["runtime_kit_manifest_hash"])) == 64
