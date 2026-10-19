"""文件功能：验证新增截图描述 DTO 的增量兼容、状态约束及敏感字段边界。"""

import pytest
from app.schemas.mutation_result import ExternalMutationResult
from pydantic import TypeAdapter, ValidationError


def test_mutation_result_preserves_legacy_fields():
    """结果仍是字典，旧页面/组件与未来业务字段继续保留。"""
    adapter = TypeAdapter(ExternalMutationResult)
    assert adapter.validate_python({"page_id": 21, "validation": "检查通过"}) == {"page_id": 21, "validation": "检查通过"}
    ready = {"status": "ready", "version_no": 2, "screenshot_id": "a" * 64, "width": 1920, "height": 1080}
    assert adapter.validate_python({"screenshot": ready})["screenshot"] == ready
    with pytest.raises(ValidationError):
        adapter.validate_python({"screenshot": {"status": "available", "version_no": 2}})
