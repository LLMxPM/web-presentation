"""文件功能：验证资源引用解析器对 Vue 源码与 preview_schema 的静态引用识别。"""

from app.services.resource_reference_parser import DYNAMIC_RESOURCE_NAME, ResourceReferenceParser


def test_collect_vue_asset_references_should_ignore_plain_text_asset_names() -> None:
    """普通文案或注释中出现资源名时，不应被识别为资源引用。"""

    result = ResourceReferenceParser.collect_vue_asset_references(
        """
<template>
  <section>
    <!-- hero_image 只是注释 -->
    <p>hero_image 只是文案</p>
    <AssetImage name="cover_image" />
    <asset-mermaid :name="'flow_graph'" />
    <AssetDrawio :name="dynamicName" />
  </section>
</template>
        """
    )

    assert result.asset_names == ["cover_image", "flow_graph"]
    assert result.has_dynamic is True


def test_collect_vue_asset_references_should_support_static_array_v_for_fields() -> None:
    """同文件顶层 const 数组对象字面量中的资源字段应可通过 v-for 静态枚举。"""

    result = ResourceReferenceParser.collect_vue_asset_references(
        """
<script setup lang="ts">
const painPoints = [
  { icon: '文档', cover: 'cover_a', title: '结构断点' },
  { icon: '图片', cover: 'cover_b', title: '资产断点' },
]
</script>

<template>
  <section>
    <div v-for="(item, idx) in painPoints" :key="idx">
      <Icon :name="item.icon" />
      <AssetImage :name="item.cover" />
    </div>
  </section>
</template>
        """
    )

    assert result.asset_names == ["cover_a", "cover_b", "图片", "文档"]
    assert result.has_dynamic is False


def test_collect_vue_asset_references_should_keep_unsupported_dynamic_marker() -> None:
    """computed、函数返回和表达式拼接等无法静态证明的资源名应继续标记为动态。"""

    result = ResourceReferenceParser.collect_vue_asset_references(
        """
<script setup lang="ts">
import { computed } from 'vue'

const iconItems = computed(() => [{ icon: '文档' }])
const imageItems = buildItems()
</script>

<template>
  <section>
    <Icon v-for="item in iconItems" :name="item.icon" />
    <AssetImage v-for="item in imageItems" :name="item.cover || 'fallback'" />
  </section>
</template>
        """
    )

    assert result.asset_names == []
    assert result.has_dynamic is True


def test_collect_static_asset_call_names_should_support_runtime_helpers() -> None:
    """资源辅助函数的静态字符串参数应被收集。"""

    assert ResourceReferenceParser.collect_static_asset_call_names(
        [
            """
const cover = useAssetSrc('cover_image')
const bg = useAssetBackground("hero_bg")
const url = resolveResourcePath('chart_data')
const icon = useIcon("brand_icon")
            """
        ]
    ) == ["cover_image", "hero_bg", "chart_data", "brand_icon"]


def test_collect_preview_schema_asset_references_should_read_component_node_props_name() -> None:
    """preview_schema 的 Runtime Kit 资源组件节点应按 props.name 收集。"""

    result = ResourceReferenceParser.collect_preview_schema_asset_references(
        """
{
  "slots": {
    "default": {
      "default": [
        {
          "type": "component",
          "component": "@runtime-kit/public/components/assets/AssetImage.vue",
          "props": { "name": "schema_cover" }
        }
      ]
    }
  },
  "presets": [
    {
      "key": "icon",
      "slots": {
        "default": [
          {
            "type": "component",
            "component": "@runtime-kit/public/components/primitives/Icon.vue",
            "props": { "name": "schema_icon" }
          }
        ]
      }
    }
  ]
}
        """
    )

    assert result.asset_names == ["schema_cover", "schema_icon"]
    assert result.has_dynamic is False


def test_build_result_should_split_dynamic_marker_from_static_names() -> None:
    """动态标记应从静态资源名中拆出，便于导出阶段阻断。"""

    result = ResourceReferenceParser.build_result(["hero", DYNAMIC_RESOURCE_NAME, "hero"])

    assert result.asset_names == ["hero"]
    assert result.has_dynamic is True
