"""文件功能：覆盖工作空间、项目与页面基础 CRUD 及通用配置校验测试。"""

from tests.api.catalog.catalog_cases import (
    test_auto_generated_codes_are_unique,
    test_page_content_accepts_long_text,
    test_project_archive_and_restore_should_maintain_archived_at,
    test_project_config_update_should_reject_invalid_structured_fields,
    test_project_menu_mode_should_support_bottom_preview,
    test_workspace_project_and_page_crud,
)
