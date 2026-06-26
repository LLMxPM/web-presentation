"""文件功能：保存智能体工具规格使用的响应示例和工具 key 分组常量。"""

from __future__ import annotations


_COMPONENT_LIST_RESPONSE_EXAMPLE = {
    "total": 1,
    "items": [
        {
            "component_id": 12,
            "component_code": "cmp_hero_card",
            "name": "HeroCard",
            "import_name": "HeroCard",
            "component_type": "内容组件",
            "summary": "首页英雄区卡片。",
            "current_version_no": 3,
            "status": "active",
        }
    ],
}

_WORKSPACE_COMPONENT_LIST_RESPONSE_EXAMPLE = {
    "source": "project_suggested",
    "fallback_reason": None,
    "total": 1,
    "items": [
        {
            "name": "HeroCard",
            "import_name": "HeroCard",
            "component_type": "内容组件",
            "description": "首页英雄区卡片。",
            "component_code": "cmp_hero_card",
            "current_version_no": 3,
        }
    ],
}

_WORKSPACE_COMPONENT_USAGE_RESPONSE_EXAMPLE = {
    "component_code": "cmp_hero_card",
    "name": "HeroCard",
    "import_name": "HeroCard",
    "component_type": "内容组件",
    "description": "首页英雄区卡片。",
    "current_version_no": 3,
    "preview_schema": '{"props":{"height":{"type":"number","label":"高度","default":320}}}',
    "import_path": "@workspace-components/cmp_hero_card/v/3",
    "import_statement": "import HeroCard from '@workspace-components/cmp_hero_card/v/3'",
}

_RUNTIME_KIT_LIST_RESPONSE_EXAMPLE = {
    "total": 1,
    "items": [
        {
            "name": "DefaultContainer.v1",
            "base_name": "DefaultContainer",
            "version_no": 1,
            "kind": "component",
            "category": "page",
            "import_path": "@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue",
        }
    ],
    "message": "Runtime Kit 能力仅用于生成页面或组件源码中的公开 import；生成代码时必须按工具返回的版本化 import_path 原样使用。",
}

_PROJECT_ROUTE_PAGE_WRITE_EXAMPLE = {
    "route_type": "page",
    "route": "cover",
    "order": 10,
    "hidden": False,
    "page_id": 3,
    "children": [],
}

_PROJECT_ROUTE_GROUP_WRITE_EXAMPLE = {
    "route_type": "group",
    "route": "chapter-1",
    "order": 20,
    "hidden": False,
    "group_title": "第一章",
    "page_id": None,
    "children": [
        {
            "route": "overview",
            "order": 10,
            "hidden": False,
            "page_id": 4,
        }
    ],
}

_PROJECT_ROUTE_TREE_RESPONSE_EXAMPLE = {
    "routes": [
        {
            "id": 11,
            "route_type": "page",
            "route": "cover",
            "order": 10,
            "hidden": False,
            "page_id": 3,
            "page_code": "page_cover",
            "page_title": "封面",
            "display_title": "封面",
            "children": [],
        },
        {
            "id": 12,
            "route_type": "group",
            "route": "chapter-1",
            "order": 20,
            "hidden": False,
            "group_title": "第一章",
            "page_id": None,
            "page_code": None,
            "page_title": None,
            "display_title": "第一章",
            "children": [
                {
                    "id": 13,
                    "route_type": "page",
                    "route": "overview",
                    "order": 10,
                    "hidden": False,
                    "page_id": 4,
                    "page_code": "page_overview",
                    "page_title": "概览",
                    "display_title": "概览",
                }
            ],
        },
    ],
}

_PROJECT_ROUTE_PREVIEW_RESPONSE_EXAMPLE = {
    "valid": True,
    "message": "路由树预览校验通过，尚未写入数据库。",
    "current_route_count": 2,
    "next_route_count": 3,
    "next_routes": [_PROJECT_ROUTE_PAGE_WRITE_EXAMPLE, _PROJECT_ROUTE_GROUP_WRITE_EXAMPLE],
}

_PROJECT_ROUTE_APPLY_RESPONSE_EXAMPLE = {
    "success": True,
    "message": "项目路由树已整树覆盖。",
    "route_count": 3,
    "routes": _PROJECT_ROUTE_TREE_RESPONSE_EXAMPLE["routes"],
}


_COORDINATOR_CONTENT_PROJECT_TOOL_KEYS = (
    'get_page_content',
    'get_project_style_config',
    'list_project_pages',
    'get_project_route_tree',
    'preview_project_route_tree',
    'check_page_code',
    'apply_page_edits',
    'get_page_screenshot',
    'create_project_page',
    'update_page_metadata',
    'update_project_style_config',
    'apply_project_route_tree',
    'remove_project_route_node',
)


_TEAM_DELEGATION_TOOL_KEYS = (
    'delegate_task_to_member',
    'delegate_task_to_members',
)


_RUNTIME_KIT_TOOL_KEYS = (
    'list_runtime_kit_capabilities',
    'get_runtime_kit_capability',
)


_COMPONENT_LIBRARY_TOOL_KEYS = (
    'list_components',
    'get_component_detail',
    'list_component_versions',
    'get_component_dependencies',
    *_RUNTIME_KIT_TOOL_KEYS,
    'list_resource_assets',
    'get_resource_asset_content',
    'list_resource_tags',
    'check_component_code',
    'create_component',
    'apply_component_edits',
    'update_component_metadata',
    'publish_component',
    'delete_component',
)


_RESOURCE_LIBRARY_TOOL_KEYS = (
    'list_resource_assets',
    'list_project_suggested_reference_assets',
    'get_resource_asset_content',
    'list_resource_tags',
    'create_resource_asset',
    'preview_resource_content_diff',
    'apply_resource_content_diff',
    'update_resource_asset_metadata',
    'copy_resource_asset',
    'archive_resource_asset',
)


