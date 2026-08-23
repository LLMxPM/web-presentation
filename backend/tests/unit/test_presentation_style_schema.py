"""文件功能：验证项目与工作空间样式共享配置 Schema 的判别分支和补丁约束。"""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.presentation_style import (
    PresentationConfig,
    PresentationConfigPatch,
    ProjectCreateConfiguration,
    StyleConfigurationPatch,
    SuggestedComponentsSelection,
)
from app.schemas.external_api import ExternalProjectCreateRequest


def test_presentation_config_should_normalize_defaults_and_text() -> None:
    """完整展示配置应统一字号、换行和默认字段。"""

    config = PresentationConfig(base_font_size="18", style_spec_markdown="a\r\nb")

    assert config.base_font_size == "18px"
    assert config.style_spec_markdown == "a\nb"
    assert config.page_width == 1920


def test_configuration_patch_should_reject_empty_or_invalid_null_fields() -> None:
    """补丁必须产生真实修改，只有 theme_key 允许 null 回退默认主题。"""

    with pytest.raises(ValidationError):
        PresentationConfigPatch()
    with pytest.raises(ValidationError):
        PresentationConfigPatch(style_spec_markdown=None)
    with pytest.raises(ValidationError):
        StyleConfigurationPatch(presentation=None)

    assert PresentationConfigPatch(theme_key=None).model_fields_set == {"theme_key"}


def test_suggested_components_should_deduplicate_in_order() -> None:
    """建议组件应按输入顺序去重并拒绝非正 ID。"""

    assert SuggestedComponentsSelection(component_ids=[3, 1, 3]).component_ids == [3, 1]
    with pytest.raises(ValidationError):
        SuggestedComponentsSelection(component_ids=[0])


def test_project_create_configuration_should_be_discriminated() -> None:
    """项目初始化来源不得交叉提交 style 与 custom 字段。"""

    adapter = TypeAdapter(ProjectCreateConfiguration)
    assert adapter.validate_python({"mode": "default"}).mode == "default"
    assert adapter.validate_python({"mode": "style", "style_id": 9}).mode == "style"
    assert adapter.validate_python({"mode": "custom", "presentation": {"page_width": 1600}}).mode == "custom"
    with pytest.raises(ValidationError):
        adapter.validate_python({"mode": "style", "style_id": 9, "presentation": {}})


def test_external_project_create_should_default_configuration() -> None:
    """External API 创建项目未传配置时，应使用 default 分支并拒绝空对象。"""

    request = ExternalProjectCreateRequest(name="External Project")
    assert request.configuration.mode == "default"

    with pytest.raises(ValidationError):
        ExternalProjectCreateRequest(name="External Project", configuration={})
