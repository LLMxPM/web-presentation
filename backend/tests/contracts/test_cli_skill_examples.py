"""文件功能：验证相邻 agent-kit Skill 示例与 Backend 模型、路由业务规则及 Runtime 主题映射一致。"""

import json
from pathlib import Path
import re

import pytest

from app.schemas.project_route import ProjectRouteTreeWriteRequest
from app.schemas.theme import ThemePalette
from app.services.project_route_service import ProjectRouteService


def test_skill_route_and_theme_examples():
    """真实文档中的 JSON 必须通过模型及稳定业务规则；缺少相邻仓库时明确跳过。"""
    root = Path(__file__).resolve().parents[3]
    references = root.parent / 'web-presentation-agent-kit/skills/web-presentation/references'
    if not references.is_dir():
        pytest.skip('需要相邻 web-presentation-agent-kit 仓库以执行跨仓 Skill 示例验证')
    route_text = (references / 'route-and-navigation.md').read_text(encoding='utf-8')
    route = ProjectRouteTreeWriteRequest.model_validate(json.loads(re.search(r'```json\s*(.*?)\s*```', route_text, re.S)[1]))
    for item in route.routes:
        ProjectRouteService._ensure_valid_route_segment(item.route, source_label='Skill 示例')
        for child in item.children:
            ProjectRouteService._ensure_valid_route_segment(child.route, source_label='Skill 示例')
    theme_text = (references / 'design-system-and-assets.md').read_text(encoding='utf-8')
    ThemePalette.model_validate(json.loads(re.search(r'```json\s*(.*?)\s*```', theme_text, re.S)[1]))
    runtime = (root / 'runtime/src/core/tailwind/runtime-tailwind-theme.js').read_text(encoding='utf-8')
    for variable in re.findall(r'--tw-color-[a-z0-9-]+', theme_text):
        assert variable in runtime, variable
    for key, variable in [('primary', '--tw-color-text-primary'), ('accent1', '--tw-color-accent1')]:
        assert f"{key}: createColorScale('{variable}')" in runtime
