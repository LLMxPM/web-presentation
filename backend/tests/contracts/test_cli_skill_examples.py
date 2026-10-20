"""文件功能：验证相邻 CLI Skill 的路由、音频及主题示例与 Backend 契约一致。"""

import json
from pathlib import Path
import re

import pytest

from app.schemas.project_route import ProjectRouteTreeWriteRequest
from app.schemas.audio import ProjectAudioSettings
from app.schemas.theme import ThemePalette
from app.schemas.external_api import ExternalFontRegisterRequest, ExternalThemeUpdateRequest
from app.services.project_route_service import ProjectRouteService


@pytest.fixture
def skill_paths() -> tuple[Path, Path]:
    """定位主仓与相邻 Skill；缺少外部源码时明确跳过跨仓验证。"""
    root = Path(__file__).resolve().parents[3]
    references = root.parent / 'web-presentation-cli/skills/web-presentation/references'
    if not references.is_dir():
        references = root.parent / 'web-presentation-agent-kit/skills/web-presentation/references'
    if not references.is_dir():
        pytest.skip('需要相邻 web-presentation-cli 仓库以执行跨仓 Skill 示例验证')
    return root, references


def _json_example(text: str, required_fields: set[str]) -> dict:
    """按业务字段定位唯一示例，不依赖文档中 JSON 代码块的出现顺序。"""

    examples = [json.loads(block) for block in re.findall(r'```json\s*(.*?)\s*```', text, re.S)]
    matches = [item for item in examples if isinstance(item, dict) and required_fields <= item.keys()]
    assert len(matches) == 1, f"预期唯一包含 {sorted(required_fields)} 的示例，实际找到 {len(matches)} 个"
    return matches[0]


def test_skill_route_example(skill_paths):
    """路由示例必须通过真实写模型及单段路径业务规则。"""

    _, references = skill_paths
    route_text = (references / 'route-and-navigation.md').read_text(encoding='utf-8')
    route = ProjectRouteTreeWriteRequest.model_validate(_json_example(route_text, {'routes'}))
    for item in route.routes:
        ProjectRouteService._ensure_valid_route_segment(item.route, source_label='Skill 示例')
        for child in item.children:
            ProjectRouteService._ensure_valid_route_segment(child.route, source_label='Skill 示例')

def test_skill_audio_example(skill_paths):
    """能力关闭仍可验证文档中的音频字段、cue 命名和音量范围。"""

    _, references = skill_paths
    text = (references / 'design-system-and-assets.md').read_text(encoding='utf-8')
    ProjectAudioSettings.model_validate(_json_example(text, {'master_volume_percent', 'cue_bindings'}))


def test_skill_theme_example_and_runtime_mapping(skill_paths):
    """主题示例与实际 Runtime Token 映射保持一致，不误选前面的音频示例。"""

    root, references = skill_paths
    theme_text = (references / 'design-system-and-assets.md').read_text(encoding='utf-8')
    ThemePalette.model_validate(_json_example(theme_text, {'text', 'background', 'border', 'link', 'accent'}))
    runtime = (root / 'runtime/src/core/tailwind/runtime-tailwind-theme.js').read_text(encoding='utf-8')
    for variable in re.findall(r'--tw-color-[a-z0-9-]+', theme_text):
        assert variable in runtime, variable
    for key, variable in [('primary', '--tw-color-text-primary'), ('accent1', '--tw-color-accent1')]:
        assert f"{key}: createColorScale('{variable}')" in runtime


def test_skill_font_registration_and_theme_design_examples(skill_paths):
    """字体注册与主题设计 JSON 必须通过真实 External DTO，而非只校验 Markdown 格式。"""

    _, references = skill_paths
    text = (references / 'cli-usage.md').read_text(encoding='utf-8')
    ExternalFontRegisterRequest.model_validate(_json_example(text, {'asset_id', 'family_name', 'font_weight'}))
    ExternalThemeUpdateRequest.model_validate(_json_example(text, {'logo_asset_id', 'heading_font_family_id', 'body_font_preset'}))
