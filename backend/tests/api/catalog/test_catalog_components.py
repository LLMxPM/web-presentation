"""文件功能：覆盖工作空间组件目录与导入元数据校验测试。"""

from tests.api.catalog.catalog_cases import (
    test_workspace_component_import_name_should_be_required_valid_and_unique,
    test_workspace_component_should_persist_component_type_and_support_filter,
    test_workspace_component_should_reject_unknown_component_type,
)
