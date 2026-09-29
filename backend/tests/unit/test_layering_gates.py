"""文件功能：分层导入门禁，冻结 services→ai 与路由层 ORM 直查既有依赖并拒绝新增耦合。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SERVICES_ROOT = Path(__file__).resolve().parents[2] / "app" / "services"
API_ROUTES_ROOT = Path(__file__).resolve().parents[2] / "app" / "api" / "routes"

# 路由层仅允许引用的 app.models 子模块（枚举/常量，不含 ORM 实体）。
ALLOWED_ROUTE_MODEL_IMPORTS = frozenset({"app.models.enums"})

# 既有路由层 ORM 实体依赖白名单（文件相对 app/api/routes → 允许的 app.models 模块）。
# 新增直查必须下沉到 services；确需保留时须架构评审后显式扩表，禁止静默扩散。
ALLOWED_ROUTES_TO_MODELS: dict[str, frozenset[str]] = {
    "assets.py": frozenset({"app.models.asset"}),
    "internal_runtime.py": frozenset({"app.models.project_build_job", "app.models.release"}),
    "public_assets.py": frozenset({"app.models.asset", "app.models.page"}),
    "testing_readiness.py": frozenset(
        {
            "app.models.ai_image_model",
            "app.models.ai_llm",
            "app.models.user",
            "app.models.workspace",
        }
    ),
    "external/mutations.py": frozenset({"app.models.api_mutation_job"}),
    "external/system.py": frozenset({"app.models.workspace"}),
    "external/workspaces.py": frozenset({"app.models.workspace"}),
}

# 既有路由层 SQLAlchemy 查询构造白名单（同一文件相对路径）。
# 仅覆盖当前已存在的直查点；新路由必须走 services，不得继续扩表堆查询。
ALLOWED_ROUTE_ORM_QUERIES: dict[str, frozenset[str]] = {
    "internal_runtime.py": frozenset(
        {
            "select",
            "session.execute",
            "session.get",
            "session.scalars",
        }
    ),
    "public_assets.py": frozenset({"select", "session.scalar"}),
    "testing_readiness.py": frozenset({"select", "session.execute", "session.scalar"}),
    "external/system.py": frozenset({"select", "session.execute"}),
    "external/workspaces.py": frozenset({"select", "session.scalars"}),
}

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


def _collect_model_imports(path: Path) -> set[str]:
    """收集文件内对 app.models 的绝对导入模块名。"""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app.models"):
            found.add(node.module or "")
        elif isinstance(node, ast.Import):
            for name in _module_from_import(node):
                if name.startswith("app.models"):
                    found.add(name)
    return found


def _receiver_name(node: ast.AST) -> str | None:
    """取出属性访问的接收者简单名；嵌套属性只保留最外层名。"""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _receiver_name(node.value)
    return None


# 会话对象常见命名；只在这些接收者上识别 ORM 调用，避免误伤 router.get / dict.get。
_SESSION_RECEIVER_HINTS = ("session", "db", "async_session", "db_session")
_ORM_SESSION_METHODS = frozenset({"execute", "scalars", "scalar", "get", "add"})


def _collect_orm_query_hits(path: Path) -> set[str]:
    """收集路由文件内的 SQLAlchemy 查询/写入构造点短名。"""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "select":
            found.add("select")
            continue
        if isinstance(func, ast.Attribute) and func.attr in _ORM_SESSION_METHODS:
            receiver = _receiver_name(func.value)
            if receiver and any(hint in receiver for hint in _SESSION_RECEIVER_HINTS):
                found.add(f"session.{func.attr}")
    return found


def test_routes_should_not_add_new_orm_entity_imports() -> None:
    """路由层不得新增 app.models 实体依赖；枚举导入允许，存量实体仅白名单内可用。"""

    offenders: list[str] = []
    for path in sorted(API_ROUTES_ROOT.rglob("*.py")):
        rel = path.relative_to(API_ROUTES_ROOT).as_posix()
        imports = _collect_model_imports(path)
        unexpected = sorted(
            name
            for name in imports
            if name not in ALLOWED_ROUTE_MODEL_IMPORTS
            and name not in ALLOWED_ROUTES_TO_MODELS.get(rel, frozenset())
        )
        if unexpected:
            offenders.append(f"{rel}: {', '.join(unexpected)}")

    assert not offenders, (
        "api/routes 新增了 app.models 实体依赖（分层门禁）。"
        "请下沉到 services/repositories，或在架构评审后显式扩表：\n" + "\n".join(offenders)
    )


def test_routes_should_not_add_new_orm_queries() -> None:
    """路由层不得新增 SQLAlchemy 查询/写入构造；存量直查仅白名单内模块可保留。"""

    offenders: list[str] = []
    for path in sorted(API_ROUTES_ROOT.rglob("*.py")):
        rel = path.relative_to(API_ROUTES_ROOT).as_posix()
        hits = _collect_orm_query_hits(path)
        allowed = ALLOWED_ROUTE_ORM_QUERIES.get(rel, frozenset())
        unexpected = sorted(hit for hit in hits if hit not in allowed)
        if unexpected:
            offenders.append(f"{rel}: {', '.join(unexpected)}")

    assert not offenders, (
        "api/routes 新增了 ORM 直查（分层门禁）。"
        "路由只应编排 services，不得自建查询：\n" + "\n".join(offenders)
    )


def test_route_orm_allowlists_should_not_drift_from_tree() -> None:
    """路由 ORM 白名单不得保留已删除条目，也不得漏记仍存在的直查。"""

    stale: list[str] = []
    for rel, allowed in ALLOWED_ROUTES_TO_MODELS.items():
        path = API_ROUTES_ROOT / rel
        if not path.is_file():
            stale.append(f"{rel}: 文件不存在（模型导入白名单）")
            continue
        actual = _collect_model_imports(path) - ALLOWED_ROUTE_MODEL_IMPORTS
        missing = sorted(name for name in allowed if name not in actual)
        if missing:
            stale.append(f"{rel}: 模型导入白名单多余 {', '.join(missing)}")

    for rel, allowed in ALLOWED_ROUTE_ORM_QUERIES.items():
        path = API_ROUTES_ROOT / rel
        if not path.is_file():
            stale.append(f"{rel}: 文件不存在（查询白名单）")
            continue
        actual = _collect_orm_query_hits(path)
        missing = sorted(name for name in allowed if name not in actual)
        if missing:
            stale.append(f"{rel}: 查询白名单多余 {', '.join(missing)}")

    assert not stale, "路由 ORM 白名单与代码漂移：\n" + "\n".join(stale)
