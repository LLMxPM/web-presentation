"""文件功能：约束图标契约说明和跨仓 Skill 的资源发现、分页及字段读取流程。"""

import json
from pathlib import Path

import pytest


def test_icon_contract_distinguishes_renderer_and_assets():
    """Icon 说明必须解释名称来源、示例边界及独立 Runtime 配置。"""
    root = Path(__file__).resolve().parents[3]
    manifest = json.loads((root / "runtime/src/runtime-kit/manifest/runtime-kit.manifest.json").read_text(encoding="utf-8"))
    items = manifest["exports"]
    icon = next(item for item in items if item["name"] == "Icon.v1")
    text = " ".join(icon["capability"]["constraints"])
    assert all(word in text for word in ("active", "真实 name", "示例", "不保证", "独立", "SVG"))


def test_cli_skill_icon_discovery_contract():
    """跨仓实例存在时验证实际分发文档，缺仓明确跳过。"""
    references = Path(__file__).resolve().parents[4] / "web-presentation-cli/skills/web-presentation/references"
    if not references.is_dir():
        pytest.skip("需要相邻 CLI 仓库")
    text = (references / "design-system-and-assets.md").read_text(encoding="utf-8")
    for field in ("wp --json asset list --type icon", "--keyword", "--page-size", "total", "import_path", "usage", "constraints", "preview_schema.props", "省略标记"):
        assert field in text
