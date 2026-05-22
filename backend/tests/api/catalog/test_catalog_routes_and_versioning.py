"""文件功能：覆盖项目路由、运行时配置与页面版本链路测试。"""

from tests.api.catalog.catalog_cases import (
    test_archiving_page_should_remove_project_route_bindings,
    test_get_page_current_component_index_should_return_latest_version_index,
    test_page_copy_to_project_should_append_routes_and_deduplicate,
    test_page_copy_to_project_should_create_current_version_only,
    test_page_copy_to_project_should_reject_page_module_dependency_and_invalid_group_atomically,
    test_page_copy_to_project_should_validate_scope_and_status,
    test_page_save_should_build_component_index_for_each_version,
    test_page_version_history_snapshot_and_restore,
    test_page_version_timestamp_label_should_follow_app_timezone,
    test_project_route_tree_should_accept_page_bindings,
    test_project_route_tree_should_accept_single_segment_routes,
    test_project_route_tree_should_reject_duplicate_child_route,
    test_project_route_tree_should_reject_duplicate_top_level_route,
    test_project_route_tree_should_reject_invalid_route_segments,
    test_project_route_tree_should_validate_icon_assets,
    test_runtime_project_config_endpoint_should_return_yaml_text,
    test_runtime_project_icon_should_follow_theme_config,
    test_snapshot_version_labels_support_major_and_sub_versions,
)
