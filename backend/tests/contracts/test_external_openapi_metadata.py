"""文件功能：核对 External API OpenAPI 操作元数据与鉴权注册表及真实路由同步。"""

from __future__ import annotations

import pytest

from app.core.external_operations import OPERATION_REGISTRY
from app.main import create_app

pytestmark = pytest.mark.unit


def test_external_routes_disclose_operation_metadata() -> None:
    """外部路由均披露鉴权语义，管理端内部路由不被误标记。"""

    paths = create_app().openapi()["paths"]
    operations = {
        (path, method): operation
        for path, path_item in paths.items()
        if path.startswith("/api/v1/")
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }
    missing = {
        (path, method)
        for (path, method), operation in operations.items()
        if "x-wp-operation" not in operation and not path.startswith("/api/v1/admin/")
    }
    assert not missing
    assert "x-wp-operation" not in operations[("/api/v1/admin/settings", "get")]


def test_registered_routes_disclose_scopes_and_dynamic_candidates() -> None:
    """已登记的 HTTP 路径和复用操作的别名保留真实 Scope、幂等与动态选择。"""

    paths = create_app().openapi()["paths"]
    for spec in OPERATION_REGISTRY.values():
        if not spec.path_template:
            continue
        operation = paths[f"/api/v1{spec.path_template}"][spec.http_method.lower()]
        metadata = operation["x-wp-operation"]
        candidates = metadata.get("candidates")
        resolved = candidates[spec.operation_key.split(".")[2]] if candidates else metadata
        assert resolved["key"] == spec.operation_key
        assert resolved["required_scopes"] == list(spec.scopes)
        assert resolved["scope_mode"] == spec.scope_mode
        assert metadata["idempotency_key_required"] == spec.requires_idempotency_key

    alias = paths["/api/v1/pages/{page_id}/source"]["get"]["x-wp-operation"]
    assert alias["key"] == "page.get"
    assert alias["required_scopes"] == ["page:read"]
    dynamic = paths["/api/v1/jobs/mutations/{job_id}"]["get"]["x-wp-operation"]
    assert dynamic["resolution"] == "mutation_job_type"
    assert dynamic["candidates"]["page"]["required_scopes"] == ["page:read"]
    assert dynamic["candidates"]["component"]["required_scopes"] == ["component:read"]
