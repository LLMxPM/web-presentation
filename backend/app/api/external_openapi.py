"""文件功能：从 External 真实鉴权依赖派生 OpenAPI 元数据，并收口缓存边界与公共请求结果日志。"""

from __future__ import annotations

import time
from collections.abc import Callable, Coroutine, Iterator
from typing import Any

from fastapi import Request, Response
from fastapi.dependencies.models import Dependant
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.api.external_request_logging import bind_mutation_response, log_external_result
from app.core.exceptions import AppException
from app.core.external_operations import (
    OPERATION_REGISTRY,
    ExternalOperationSpec,
    get_operation_spec,
)
from app.schemas.external_api import ExternalMutationJobResponse


def _walk_dependencies(dependant: Dependant) -> Iterator[Dependant]:
    """遍历真实路由的依赖树，包含嵌套 Scope 和 Header 声明。"""

    yield dependant
    for child in dependant.dependencies:
        yield from _walk_dependencies(child)


def _scope_metadata(spec: ExternalOperationSpec) -> dict[str, Any]:
    """使用鉴权依赖捕获的同一规格生成 Scope 元数据，不复制权限表。"""

    return {"key": spec.operation_key, "required_scopes": list(spec.scopes), "scope_mode": spec.scope_mode}


class ExternalAPIRoute(APIRoute):
    """外部专用路由，在装配时校验并公开真实操作契约。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """装配鉴权元数据；缺少注册依赖或存在歧义时拒绝启动。"""

        super().__init__(*args, **kwargs)
        dependencies = list(_walk_dependencies(self.dependant))
        specs = {
            spec.operation_key: spec
            for dependency in dependencies
            if (spec := getattr(dependency.call, "external_operation_spec", None)) is not None
        }
        actions = {
            action for dependency in dependencies
            if (action := getattr(dependency.call, "external_mutation_action", None)) is not None
        }
        if len(specs) > 1 or len(actions) > 1 or (specs and actions):
            raise RuntimeError(f"External 路由鉴权规格不明确：{self.path}")

        workspace_required = any(
            parameter.alias.lower() == "x-workspace-id" and parameter.field_info.is_required()
            for dependency in dependencies for parameter in dependency.header_params
        )
        if actions:
            action = next(iter(actions))
            candidates = {}
            for resource in ("page", "component"):
                spec = get_operation_spec(f"jobs.mutation.{resource}.{action}")
                if spec is None:
                    raise RuntimeError(f"Mutation 操作未登记：{resource}.{action}")
                candidates[resource] = _scope_metadata(spec)
            metadata = {
                "version": 1,
                "resolution": "mutation_job_type",
                "action": action,
                "candidates": candidates,
                "workspace_header_required": workspace_required,
                "idempotency_key_required": any(
                    get_operation_spec(item["key"]).requires_idempotency_key for item in candidates.values()
                ),
            }
        else:
            # 公开入口没有 Bearer 依赖，按注册表中的真实公开路径匹配。
            public_specs = [
                spec for spec in OPERATION_REGISTRY.values()
                if spec.is_public and spec.path_template == self.path and spec.http_method in self.methods
            ]
            if not specs and len(public_specs) == 1:
                specs = {public_specs[0].operation_key: public_specs[0]}
            if len(specs) != 1:
                raise RuntimeError(f"External 路由缺少操作鉴权规格：{self.path}")
            spec = next(iter(specs.values()))
            metadata = {
                "version": 1,
                **_scope_metadata(spec),
                "public": spec.is_public,
                "workspace_header_required": workspace_required,
                "idempotency_key_required": spec.requires_idempotency_key,
            }
        extra = dict(self.openapi_extra or {})
        if "x-wp-operation" in extra and extra["x-wp-operation"] != metadata:
            raise RuntimeError(f"External 操作元数据不能覆盖实际鉴权：{self.path}")
        self.openapi_extra = {**extra, "x-wp-operation": metadata}

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """为原路由添加公共结果日志与用户数据缓存边界，保持原鉴权、响应和异常语义。"""

        original_handler = super().get_route_handler()

        async def _handler(request: Request) -> Response:
            """执行原鉴权/序列化并记录公共标识；原业务异常继续抛出，日志不展开领域正文。"""
            metadata = (self.openapi_extra or {}).get("x-wp-operation", {})
            started = time.perf_counter()
            try:
                response = await original_handler(request)
            except Exception as error:
                status = (
                    422 if isinstance(error, RequestValidationError)
                    else getattr(error, "status_code", 500)
                )
                log_external_result(
                    request,
                    route=self.path,
                    operation=metadata.get("key"),
                    status_code=status,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    error_code=error.code if isinstance(error, AppException) else None,
                )
                raise
            if not metadata.get("public", False):
                response.headers["Cache-Control"] = "private, no-store"
            if self.response_model is ExternalMutationJobResponse:
                bind_mutation_response(request, response)
            log_external_result(
                request,
                route=self.path,
                operation=metadata.get("key"),
                status_code=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            return response

        return _handler
