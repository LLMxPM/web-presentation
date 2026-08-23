"""文件功能：覆盖组件草稿保存、发布和恢复相关测试。"""

# 通过导入测试函数交给 pytest 收集。
# ruff: noqa: F401

from tests.integration.component_preview.component_preview_publish_cases import (
    test_component_draft_save_publish_restore_and_version_preview,
    test_component_publish_should_build_versions_and_current_dependencies,
)  # noqa: F401
