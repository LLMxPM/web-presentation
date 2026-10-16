"""文件功能：提供隔离预览主机名下按构建票据鉴权的静态产物代理入口。"""

from __future__ import annotations

import hashlib
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.services.file_auth_service import FileAuthService
from app.services.project_build_artifact_proxy_service import ProjectBuildArtifactProxyService
from app.services.token_service import TokenService

router = APIRouter()


@router.get("/build-artifacts/{project_id}/{job_id}")
@router.get("/build-artifacts/{project_id}/{job_id}/{artifact_path:path}")
@router.head("/build-artifacts/{project_id}/{job_id}", include_in_schema=False)
@router.head("/build-artifacts/{project_id}/{job_id}/{artifact_path:path}", include_in_schema=False)
async def proxy_project_build_artifact(
    project_id: int,
    job_id: int,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    artifact_path: str = "",
) -> Response:
    """受保护的项目构建产物静态站点代理入口。

    必须携带有效的构建访问令牌（支持 query token 或 project/job 专用 Cookie）；
    无凭证或凭证无效的匿名访问一律返回 404 及 no-store。
    """

    cookie_name = f"wp_build_token_{project_id}_{job_id}"
    token = request.query_params.get("token") or request.cookies.get(cookie_name)
    if not token and request.headers.get("authorization"):
        parts = request.headers["authorization"].strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]

    if not token:
        raise AppException(
            status_code=404,
            code="BUILD_ARTIFACT_ANONYMOUS_DISABLED",
            detail="构建产物匿名访问已关闭，请使用受保护的私有构建授权接口浏览或下载。",
            headers={"Cache-Control": "no-store"},
        )

    try:
        claims = TokenService.verify_build_access_token(token)
    except Exception as exc:
        raise AppException(
            status_code=404,
            code="BUILD_ARTIFACT_ANONYMOUS_DISABLED",
            detail="构建产物访问凭证无效或已过期。",
            headers={"Cache-Control": "no-store"},
        ) from exc

    if int(claims.get("project_id") or 0) != int(project_id) or int(claims.get("job_id") or 0) != int(job_id):
        raise AppException(
            status_code=404,
            code="BUILD_ARTIFACT_ANONYMOUS_DISABLED",
            detail="构建产物访问凭证作用域不匹配。",
            headers={"Cache-Control": "no-store"},
        )

    from app.services.preview_origin_service import isolated_preview_origin
    from urllib.parse import urlsplit
    preview_origin = isolated_preview_origin()
    if request.url.hostname != urlsplit(preview_origin).hostname:
        # 业务源站不能执行用户构建 HTML；有效票据只能跳转至隔离源站。
        return RedirectResponse(
            f"{preview_origin}{request.url.path}?token={token}", status_code=307,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    result = await ProjectBuildArtifactProxyService(session).get_artifact_file(
        project_id=project_id,
        job_id=job_id,
        request_path=artifact_path,
    )

    etag = hashlib.sha256(result.content).hexdigest()
    if FileAuthService.evaluate_preconditions(request, etag):
        resp = Response(status_code=304, headers={**result.headers, "ETag": f'"{etag}"'})
    elif request.method == "HEAD":
        resp = Response(
            status_code=200,
            media_type=result.media_type,
            headers={**result.headers, "ETag": f'"{etag}"', "Content-Length": str(len(result.content))},
        )
    else:
        resp = Response(
            content=result.content,
            status_code=200,
            media_type=result.media_type,
            headers={**result.headers, "ETag": f'"{etag}"'},
        )

    if request.query_params.get("token"):
        resp.set_cookie(
            key=cookie_name,
            value=token,
            max_age=max(0, min(300, int(claims["exp"]) - int(time.time()))),
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
            path=f"/build-artifacts/{project_id}/{job_id}/",
        )
    return resp

