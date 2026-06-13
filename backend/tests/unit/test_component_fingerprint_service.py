"""文件功能：验证组件指纹服务的稳定 hash 与差异敏感字段。"""

from app.services.component_fingerprint_service import ComponentFingerprintService


def test_component_fingerprint_should_ignore_line_ending_differences() -> None:
    """源码换行差异不应影响 content_hash 和组件指纹。"""

    first = ComponentFingerprintService._build_fingerprint_result(
        file_type="vue",
        content="<template>\r\n  <section>demo</section>\r\n</template>",
        preview_schema=None,
        dependency_fingerprints={},
        asset_hashes={},
        font_signatures=[],
    )
    second = ComponentFingerprintService._build_fingerprint_result(
        file_type="vue",
        content="<template>\n  <section>demo</section>\n</template>",
        preview_schema="{}",
        dependency_fingerprints={},
        asset_hashes={},
        font_signatures=[],
    )

    assert first.content_hash == second.content_hash
    assert first.component_fingerprint == second.component_fingerprint


def test_component_fingerprint_should_not_include_display_metadata() -> None:
    """组件名称、摘要和 import_name 不进入指纹载荷。"""

    base = ComponentFingerprintService._build_fingerprint_result(
        file_type="vue",
        content="<template><section>demo</section></template>",
        preview_schema=None,
        dependency_fingerprints={},
        asset_hashes={},
        font_signatures=[],
    )
    renamed = ComponentFingerprintService._build_fingerprint_result(
        file_type="vue",
        content="<template><section>demo</section></template>",
        preview_schema=None,
        dependency_fingerprints={},
        asset_hashes={},
        font_signatures=[],
    )

    assert base.component_fingerprint == renamed.component_fingerprint


def test_component_fingerprint_should_change_for_runtime_dependencies_assets_and_fonts() -> None:
    """预览 schema、依赖指纹、资源文件 hash 和字体配置变化都应改变组件指纹。"""

    base = ComponentFingerprintService._build_fingerprint_result(
        file_type="vue",
        content="<template><section>demo</section></template>",
        preview_schema='{"props":{}}',
        dependency_fingerprints={("CMPA", 1): "a" * 64},
        asset_hashes={"logo": "asset-a"},
        font_signatures=[
            {
                "asset_name": "font",
                "file_hash": "font-a",
                "font_family": "Demo",
                "font_format": "woff2",
                "font_weight": "400",
                "font_style": "normal",
                "font_display": "swap",
                "status": "active",
            }
        ],
    )

    changed_preview = ComponentFingerprintService._build_fingerprint_result(
        file_type="vue",
        content="<template><section>demo</section></template>",
        preview_schema='{"props":{"title":{"type":"string"}}}',
        dependency_fingerprints={("CMPA", 1): "a" * 64},
        asset_hashes={"logo": "asset-a"},
        font_signatures=[
            {
                "asset_name": "font",
                "file_hash": "font-a",
                "font_family": "Demo",
                "font_format": "woff2",
                "font_weight": "400",
                "font_style": "normal",
                "font_display": "swap",
                "status": "active",
            }
        ],
    )
    changed_dependency = ComponentFingerprintService._build_fingerprint_result(
        file_type="vue",
        content="<template><section>demo</section></template>",
        preview_schema='{"props":{}}',
        dependency_fingerprints={("CMPB", 1): "b" * 64},
        asset_hashes={"logo": "asset-a"},
        font_signatures=[
            {
                "asset_name": "font",
                "file_hash": "font-a",
                "font_family": "Demo",
                "font_format": "woff2",
                "font_weight": "400",
                "font_style": "normal",
                "font_display": "swap",
                "status": "active",
            }
        ],
    )
    changed_asset = ComponentFingerprintService._build_fingerprint_result(
        file_type="vue",
        content="<template><section>demo</section></template>",
        preview_schema='{"props":{}}',
        dependency_fingerprints={("CMPA", 1): "a" * 64},
        asset_hashes={"logo": "asset-b"},
        font_signatures=[
            {
                "asset_name": "font",
                "file_hash": "font-a",
                "font_family": "Demo",
                "font_format": "woff2",
                "font_weight": "400",
                "font_style": "normal",
                "font_display": "swap",
                "status": "active",
            }
        ],
    )
    changed_font = ComponentFingerprintService._build_fingerprint_result(
        file_type="vue",
        content="<template><section>demo</section></template>",
        preview_schema='{"props":{}}',
        dependency_fingerprints={("CMPA", 1): "a" * 64},
        asset_hashes={"logo": "asset-a"},
        font_signatures=[
            {
                "asset_name": "font",
                "file_hash": "font-b",
                "font_family": "Demo",
                "font_format": "woff2",
                "font_weight": "400",
                "font_style": "normal",
                "font_display": "swap",
                "status": "active",
            }
        ],
    )

    assert changed_preview.component_fingerprint != base.component_fingerprint
    assert changed_dependency.component_fingerprint != base.component_fingerprint
    assert changed_asset.component_fingerprint != base.component_fingerprint
    assert changed_font.component_fingerprint != base.component_fingerprint
