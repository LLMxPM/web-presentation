"""文件功能：对拍 Scene 导入规则，验证写入/CodeCheck 共用解析器拒绝 GSAP 核心和插件。"""

import json
from pathlib import Path

import pytest

from app.core.exceptions import AppException
from app.core.scene_authoring_policy import is_forbidden_scene_import
from app.services.component_dependency_service import ComponentDependencyService

_CASES = json.loads((Path(__file__).resolve().parents[3] / "tests/fixtures/scene-import-policy-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _CASES)
def test_shared_import_cases(case: dict) -> None:
    """Python 和 Runtime 对包名、查询后缀与边界前缀使用同一组正反例。"""
    assert is_forbidden_scene_import(case["source"]) is case["forbidden"]


@pytest.mark.parametrize("script", [
    "import { gsap } from 'gsap'",
    "import 'gsap/DrawSVGPlugin'",
    "import type { SplitText } from 'gsap-trial/SplitText'",
    "export { ScrollTrigger } from 'gsap/ScrollTrigger'",
    "export * from 'gsap/all'",
])
@pytest.mark.parametrize("vue", [True, False])
def test_parser_rejects_direct_gsap(script: str, vue: bool) -> None:
    """SFC 与独立脚本入口都在依赖解析时拒绝直接包导入和重导出。"""
    source = f"<script setup>\n{script}\n</script>" if vue else script
    with pytest.raises(AppException) as error:
        ComponentDependencyService(None).parse_dependencies(  # type: ignore[arg-type]
            source, source_label="候选页面", importer_module_path="src/views/Page.vue" if vue else "src/views/helper.ts",
        )
    assert error.value.code == "SCENE_GSAP_IMPORT_FORBIDDEN"


def test_policy_version_invalidates_compiler_identity(monkeypatch) -> None:
    """策略升级必须改变编译器指纹，不能复用旧策略下的通过结果。"""
    from app.services import code_check_fingerprint as fingerprint

    before = fingerprint._compiler_identity()
    assert before["scene_authoring_policy"] == "page-scene-authoring.v1"
    monkeypatch.setattr(fingerprint, "SCENE_AUTHORING_POLICY_VERSION", "test-next")
    assert fingerprint._compiler_identity() != before
