"""文件功能：分层导入门禁，冻结 services→ai 既有依赖并拒绝新增反向耦合。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SERVICES_ROOT = Path(__file__).resolve().parents[2] / "app" / "services"

# 既有 services→app.ai 依赖白名单（文件相对 app/services 的路径 → 允许的 app.ai 模块前缀）。
# 新增 import 必须先在架构上论证，再显式扩表；禁止静默扩散。
ALLOWED_SERVICES_TO_AI: dict[str, frozenset[str]] = {
    "agent_image_attachment_service.py": frozenset({"app.ai.image_refs"}),
    "ai_chat_config_service.py": frozenset(
        {
            "app.ai.model_protocols",
            "app.ai.provider_catalog",
            "app.ai.reasoning_controls",
            "app.ai.secret_cipher",
            "app.ai.testing.scenarios",
        }
    ),
    "ai_agent_config_service.py": frozenset(
        {
            "app.ai.agent_catalog",
            "app.ai.agent_runtime_config",
            "app.ai.code_standards",
            "app.ai.tool_specs",
            "app.ai.tools.disclosure",
            "app.ai.visual_analysis_tool_schema",
        }
    ),
    "ai_model_catalog_service.py": frozenset(
        {
            "app.ai.model_protocols",
            "app.ai.reasoning_controls",
        }
    ),
    "ai_image_config_service.py": frozenset({"app.ai.secret_cipher"}),
    "ai_llm_service.py": frozenset(
        {
            "app.ai.provider_catalog",
            "app.ai.model_capabilities",
            "app.ai.model_budget",
            "app.ai.secret_cipher",
            "app.ai.testing.scenarios",
        }
    ),
    "code_check_service.py": frozenset({"app.ai.tools.shared"}),
    "dashscope_image_generation_adapter.py": frozenset({"app.ai.secret_cipher"}),
    "image_generation_adapters.py": frozenset({"app.ai.secret_cipher"}),
    "image_understanding_service.py": frozenset({"app.ai.pydantic_model_resolver"}),
    "image_generation/registry.py": frozenset({"app.ai.testing.dispatch"}),
    "mutation_job_service.py": frozenset({"app.ai.validation_result_formatter"}),
    "mutation_planners/component_mutation_planner.py": frozenset(
        {
            "app.ai.tools.component.component_library",
            "app.ai.tools.shared",
        }
    ),
    "mutation_planners/page_mutation_planner.py": frozenset(
        {
            "app.ai.tools.page.apply_page_edits",
            "app.ai.tools.project.project_pages",
            "app.ai.tools.shared",
        }
    ),
    "openrouter_image_generation_adapter.py": frozenset({"app.ai.secret_cipher"}),
    "project_build_service.py": frozenset({"app.ai.job_invariants"}),
}


def _module_from_import(node: ast.ImportFrom | ast.Import) -> list[str]:
    """取出 import 的模块名列表。"""

    if isinstance(node, ast.ImportFrom):
        if node.level and not node.module:
            return []
        module = node.module or ""
        if node.level:
            # 相对导入不映射到 app.ai 顶层。
            return []
        return [module]
    return [alias.name for alias in node.names]


def _collect_ai_imports(path: Path) -> set[str]:
    """收集文件内对 app.ai 的绝对导入模块名。"""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app.ai"):
            found.add(node.module or "")
        elif isinstance(node, ast.Import):
            for name in _module_from_import(node):
                if name.startswith("app.ai"):
                    found.add(name)
    return found


def test_services_should_not_add_new_app_ai_imports() -> None:
    """services 层不得新增对 app.ai 的依赖；存量仅允许白名单内模块。"""

    offenders: list[str] = []
    for path in sorted(SERVICES_ROOT.rglob("*.py")):
        rel = path.relative_to(SERVICES_ROOT).as_posix()
        imports = _collect_ai_imports(path)
        if not imports:
            continue
        allowed = ALLOWED_SERVICES_TO_AI.get(rel, frozenset())
        unexpected = sorted(name for name in imports if name not in allowed)
        if unexpected:
            offenders.append(f"{rel}: {', '.join(unexpected)}")

    assert not offenders, (
        "services/ 新增了 app.ai 依赖（分层门禁）。"
        "请上移调用方、下沉共享能力，或在架构评审后显式扩表：\n" + "\n".join(offenders)
    )


def test_allowlist_should_not_drift_from_tree() -> None:
    """白名单不得保留已删除的依赖条目，避免表项腐化。"""

    stale: list[str] = []
    for rel, allowed in ALLOWED_SERVICES_TO_AI.items():
        path = SERVICES_ROOT / rel
        if not path.is_file():
            stale.append(f"{rel}: 文件不存在")
            continue
        actual = _collect_ai_imports(path)
        missing = sorted(name for name in allowed if name not in actual)
        if missing:
            stale.append(f"{rel}: 白名单多余 {', '.join(missing)}")

    assert not stale, "分层门禁白名单与代码漂移：\n" + "\n".join(stale)
