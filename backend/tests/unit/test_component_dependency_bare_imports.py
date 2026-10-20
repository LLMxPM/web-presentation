"""文件功能：验证源码依赖解析会显式记录裸模块说明符，供截图身份做路由可达性门控。"""

from __future__ import annotations

from app.services.component_dependency_service import ComponentDependencyService


def _parse(source: str):
    """按页面入口路径解析源码依赖；解析只做纯文本处理，不访问数据库会话。"""

    return ComponentDependencyService(None).parse_dependencies(  # type: ignore[arg-type]
        source,
        source_label="测试页面",
        importer_module_path="src/views/demo.vue",
        allow_page_module_imports=True,
    )


def test_bare_imports_should_capture_vue_router() -> None:
    """引用 vue-router 的页面必须被识别为可读取路由上下文。"""

    source = """
    <template><div>{{ route.path }}</div></template>
    <script setup>
    import { useRoute } from 'vue-router'
    const route = useRoute()
    </script>
    """
    assert _parse(source).bare_imports == ("vue-router",)


def test_bare_imports_should_not_capture_scoped_or_path_specifiers() -> None:
    """作用域包、别名路径、页面模块与组件引用都不得进入裸导入集合。"""

    source = """
    <template><div /></template>
    <script setup>
    import { ref } from 'vue'
    import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
    import Card from '@workspace-components/CMP001/v/1'
    import Helper from '@/views/helper.vue'
    import Local from './local'
    </script>
    """
    parsed = _parse(source)
    assert parsed.bare_imports == ("vue",)
    # 相对路径会按 importer 位置归一为页面模块路径，同样不得进入裸导入集合。
    assert parsed.page_module_imports == ("src/views/helper.vue", "src/views/local")
    assert parsed.component_imports == (("CMP001", 1),)


def test_bare_imports_should_deduplicate() -> None:
    """重复导入同一裸说明符只记录一次。"""

    source = """
    <script setup>
    import { useRoute } from 'vue-router'
    import type { RouteLocationNormalized } from 'vue-router'
    </script>
    """
    assert _parse(source).bare_imports == ("vue-router",)


def test_runtime_kit_imports_should_stay_out_of_bare_imports() -> None:
    """Runtime Kit 版本化能力走 runtime_local_imports，不得混入裸导入。"""

    source = """
    <script setup>
    import { useCurrentPage } from '@runtime-kit/public/composables/page/useCurrentPage.v1'
    </script>
    """
    parsed = _parse(source)
    assert parsed.bare_imports == tuple()
    assert [item.name for item in parsed.runtime_local_imports] == ["useCurrentPage.v1"]
