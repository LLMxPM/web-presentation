"""文件功能：从 External API 操作注册表生成 OpenAPI 扩展元数据，供外部客户端核对权限和 Header。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import FastAPI

from app.core.external_operations import ExternalOperationSpec, OPERATION_REGISTRY


def _header_required(path_item: dict[str, Any], operation: dict[str, Any], name: str) -> bool:
    """按 OpenAPI 实际参数判断 Header 是否必填，避免复制路由声明。"""

    parameters = [*path_item.get("parameters", []), *operation.get("parameters", [])]
    return any(
        parameter.get("in") == "header"
        and str(parameter.get("name", "")).lower() == name.lower()
        and parameter.get("required") is True
        for parameter in parameters
    )


def _scope_metadata(spec: ExternalOperationSpec) -> dict[str, Any]:
    """从鉴权单一事实源导出静态操作或动态候选的权限语义。"""

    return {
        "key": spec.operation_key,
        "required_scopes": list(spec.scopes),
        "scope_mode": spec.scope_mode,
    }


def _route_operation_specs(route: Any) -> list[ExternalOperationSpec]:
    """从实际路由的鉴权依赖读取注册表 key，兼容一个操作对应多个 URL。"""

    keys: set[str] = set()
    pending = [route.dependant]
    while pending:
        dependant = pending.pop()
        keys.update(getattr(dependant.call, "__wp_operation_keys__", ()))
        pending.extend(dependant.dependencies)
    return [OPERATION_REGISTRY[key] for key in sorted(keys)]


def annotate_external_openapi(document: dict[str, Any], app: FastAPI) -> None:
    """沿实际 External API 路由写入 x-wp-operation v1，权限取自鉴权注册表。"""

    paths = document["paths"]
    registry_paths: dict[tuple[str, str], list[ExternalOperationSpec]] = defaultdict(list)
    for spec in OPERATION_REGISTRY.values():
        registry_paths[(spec.http_method.lower(), f"/api/v1{spec.path_template}")].append(spec)
    for included_router in app.routes:
        if not hasattr(included_router, "effective_route_contexts"):
            continue
        for route in included_router.effective_route_contexts():
            if not route.path.startswith("/api/v1/"):
                continue
            dependency_specs = _route_operation_specs(route)
            for method in route.methods or ():
                path_item = paths.get(route.path, {})
                operation = path_item.get(method.lower())
                if operation is None:
                    continue
                specs = dependency_specs or registry_paths.get((method.lower(), route.path), [])
                if not specs:
                    continue
                header_required = _header_required(path_item, operation, "X-Workspace-ID")
                metadata: dict[str, Any] = {
                    "version": 1,
                    "workspace_header_required": header_required,
                    "idempotency_key_required": any(spec.requires_idempotency_key for spec in specs),
                }
                if len(specs) == 1:
                    spec = specs[0]
                    metadata.update(_scope_metadata(spec))
                    metadata["public"] = spec.is_public
                else:
                    action = specs[0].operation_key.rsplit(".", 1)[-1]
                    expected = {f"jobs.mutation.{resource}.{action}" for resource in ("page", "component")}
                    if {spec.operation_key for spec in specs} != expected:
                        raise RuntimeError(f"External API 动态操作映射不受支持：{method} {route.path}")
                    metadata.update({
                        "resolution": "mutation_job_type",
                        "action": action,
                        "candidates": {
                            resource: _scope_metadata(OPERATION_REGISTRY[f"jobs.mutation.{resource}.{action}"])
                            for resource in ("page", "component")
                        },
                    })
                operation["x-wp-operation"] = metadata


def install_external_operation_openapi(app: FastAPI) -> None:
    """包裹 FastAPI OpenAPI 生成入口，让元数据随当前路由和注册表同步更新。"""

    original_openapi = app.openapi

    def openapi_with_external_operations() -> dict[str, Any]:
        """复用 FastAPI 缓存文档并补充 External API 权限扩展。"""

        document = original_openapi()
        annotate_external_openapi(document, app)
        return document

    app.openapi = openapi_with_external_operations
