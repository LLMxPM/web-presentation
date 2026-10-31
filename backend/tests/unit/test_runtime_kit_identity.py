"""文件功能：以双端共享正例验证 Kit 身份投影及检查缓存对文案、执行字段的敏感度。"""

import json
from copy import deepcopy
from pathlib import Path

from app.core.runtime_kit_identity import project_runtime_kit_execution_manifest
from app.core import runtime_module_policy
from app.services import code_check_fingerprint


def test_execution_projection_should_match_shared_fixture() -> None:
    """Backend 与发布身份脚本消费同一 fixture；未知输入不得被目录过滤误删。"""

    path = Path(__file__).resolve().parents[3] / "tests/fixtures/runtime-kit-identity-cases.json"
    case = json.loads(path.read_text(encoding="utf8"))
    original = deepcopy(case["manifest"])
    assert project_runtime_kit_execution_manifest(case["manifest"]) == case["execution"]
    assert case["manifest"] == original


def test_compiler_identity_should_ignore_catalog_prose_but_cover_execution(monkeypatch) -> None:
    """纯目录变更保留检查缓存，入口、预览 Schema、引擎和策略变更必须失效。"""

    manifest = deepcopy(runtime_module_policy.load_runtime_kit_manifest())
    monkeypatch.setattr(runtime_module_policy, "load_runtime_kit_manifest", lambda: manifest)
    monkeypatch.setattr(code_check_fingerprint, "load_runtime_kit_manifest", lambda: manifest)
    baseline = code_check_fingerprint._compiler_identity()
    manifest["exports"][0]["description"] = "更新后的目录说明"
    manifest["exports"][0]["capability"]["summary"] = "更新后的 Agent 摘要"
    manifest["exports"][0]["capability"]["enabled"] = False
    assert code_check_fingerprint._compiler_identity() == baseline

    catalog_only = deepcopy(manifest)
    for field in ("import_path", "preview_schema", "model3d_engine", "future_execution"):
        manifest.clear()
        manifest.update(deepcopy(catalog_only))
        if field == "import_path":
            manifest["exports"][0]["import_path"] += ".other"
        elif field == "preview_schema":
            manifest["exports"][0]["capability"]["preview_schema"] = {"changed": True}
        else:
            manifest[field] = {"changed": True}
        assert code_check_fingerprint._compiler_identity() != baseline

    manifest.clear()
    manifest.update(catalog_only)
    monkeypatch.setattr(code_check_fingerprint, "RUNTIME_KIT_IMPORT_POLICY_VERSION", "future-policy")
    assert code_check_fingerprint._compiler_identity() != baseline
