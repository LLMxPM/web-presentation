"""文件功能：定义 External API v1 的 Bearer 认证、Scope 权限校验与动态 Mutation 鉴权依赖。"""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated, Literal

from fastapi import Depends, Header, Path, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.external_headers import IdempotencyKeyHeader, require_idempotency_key
from app.api.external_request_logging import (
    bind_external_identity,
    bind_external_operation,
)
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.external_operations import get_operation_spec
from app.core.oauth_config import resolve_oauth_policy
from app.db.session import get_db_session
from app.models.api_mutation_job import ApiMutationJob
from app.services.api_access_token_service import ApiAccessTokenService
from app.services.external_pat_identity import principal_from_pat
from app.services.external_principal import ExternalPrincipal as ExternalAuthContext
from app.services.oauth.delegated_identity import authenticate_delegated


async def get_external_auth_context(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> ExternalAuthContext:
    """按凭证命名空间单次分派 PAT/委托验证；任何失败都不能回退其它来源。"""

    if not authorization or len(request.headers.getlist("Authorization")) != 1:
        raise AppException(
            status_code=401,
            code="UNAUTHENTICATED",
            detail="请提供唯一的 Authorization: Bearer 认证头。",
        )

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AppException(
            status_code=401,
            code="UNAUTHENTICATED",
            detail="Authorization 头格式错误，必须为 Bearer <访问凭证>。",
        )

    raw_token = parts[1]
    if raw_token.startswith("wp_dlg_"):
        policy = resolve_oauth_policy(get_settings())
        if policy is None:
            raise AppException(401, "UNAUTHENTICATED", "委托访问凭证不可用。")
        principal = await authenticate_delegated(session, raw_token, policy)
        bind_external_identity(request, principal)
        return principal
    if not raw_token.startswith("wp_pat_"):
        raise AppException(401, "UNAUTHENTICATED", "业务 API 不接受此类访问凭证。")
    client_ip = request.client.host if request.client else None
    token = await ApiAccessTokenService(session).authenticate_pat(raw_token, ip=client_ip)

    # PAT 仍走原哈希、用户状态、到期及撤销校验，不伪造 PAT 行或借用服务身份。
    principal = principal_from_pat(token)
    bind_external_identity(request, principal)
    return principal


def require_external_operation(operation_key: str):
    """基于单一事实源注册表 OPERATION_REGISTRY 生成静态操作鉴权依赖。"""

    spec = get_operation_spec(operation_key)
    if spec is None:
        raise RuntimeError(f"未注册的外部 API 操作: {operation_key}")

    async def _dependency(
        request: Request,
        auth: Annotated[ExternalAuthContext, Depends(get_external_auth_context)],
        session: Annotated[AsyncSession, Depends(get_db_session)],
        x_workspace_id: Annotated[int | None, Header(alias="X-Workspace-ID")] = None,
        idempotency_key: IdempotencyKeyHeader = None,
    ) -> ExternalAuthContext:
        bind_external_operation(request, operation_key)
        # 1. 校验 Scope
        if not auth.has_required_scopes(spec.scopes, mode=spec.scope_mode):
            missing = [s for s in spec.scopes if not auth.has_scope(s)]
            raise AppException(
                status_code=403,
                code="INSUFFICIENT_SCOPE",
                detail=f"当前访问令牌缺少执行该操作所需的权限 Scope: {', '.join(missing)}",
                data={"required_scopes": list(spec.scopes), "missing_scopes": missing},
            )

        # 2. 校验必需的 Idempotency-Key
        if spec.requires_idempotency_key:
            require_idempotency_key(idempotency_key, operation_key)

        # 3. 若要求工作空间，校验 X-Workspace-ID 归属与数据库实时成员状态
        if not spec.is_public and not spec.exempt_workspace_header and x_workspace_id is not None:
            await auth.ensure_workspace_access(x_workspace_id, session)
            bind_external_operation(request, operation_key, workspace_context_id=x_workspace_id)
            auth = replace(auth, workspace_context_id=x_workspace_id)

        return auth

    # OpenAPI 从真实鉴权依赖派生，不另建 route→scope 映射。
    _dependency.external_operation_spec = spec
    return _dependency


def require_dynamic_mutation_operation(action: Literal["status", "cancel", "retry"]):
    """对通用 /jobs/mutations/{job_id} 动态按实体类型执行 page 或 component 权限鉴权。"""

    async def _dependency(
        request: Request,
        job_id: Annotated[str, Path(description="任务公开 UUID")],
        auth: Annotated[ExternalAuthContext, Depends(get_external_auth_context)],
        session: Annotated[AsyncSession, Depends(get_db_session)],
        x_workspace_id: Annotated[int | None, Header(alias="X-Workspace-ID")] = None,
        idempotency_key: IdempotencyKeyHeader = None,
    ) -> tuple[ExternalAuthContext, ApiMutationJob]:
        # 先复核 Header 空间，再将对象/任务访问限制到本次请求上下文。
        if x_workspace_id is not None:
            await auth.ensure_workspace_access(x_workspace_id, session)
            auth = replace(auth, workspace_context_id=x_workspace_id)
        stmt = select(ApiMutationJob).where(ApiMutationJob.job_id == job_id)
        job = await session.scalar(stmt)
        if job is None:
            raise AppException(status_code=404, code="MUTATION_JOB_NOT_FOUND", detail="未找到指定的变更任务。")

        # 校验工作空间权限与成员活跃状态
        await auth.ensure_workspace_access(job.workspace_id, session)

        # 根据 job_type 动态派发必须满足的 Scope
        is_page = "page" in job.job_type
        resource = "page" if is_page else "component"
        bind_external_operation(
            request,
            f"jobs.mutation.{resource}.{action}",
            workspace_id=job.workspace_id,
            workspace_context_id=x_workspace_id,
            job_id=job.job_id,
        )
        if action == "status":
            required_scope = "page:read" if is_page else "component:read"
        else:
            required_scope = "page:write" if is_page else "component:write"

        if not auth.has_scope(required_scope):
            raise AppException(
                status_code=403,
                code="INSUFFICIENT_SCOPE",
                detail=f"执行该变更任务的 {action} 操作需要 {required_scope} 权限 Scope。",
                data={"required_scopes": [required_scope]},
            )

        if action in {"cancel", "retry"}:
            require_idempotency_key(idempotency_key, f"Mutation {action}")

        return auth, job

    _dependency.external_mutation_action = action
    return _dependency
