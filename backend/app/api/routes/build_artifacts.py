"""文件功能：提供构建产物 ZIP 的公开静态站点代理入口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.session import get_db_session

router = APIRouter()


@router.api_route(
    "/build-artifacts/{project_id}/{job_id}",
    methods=["GET", "HEAD"],
)
@router.api_route(
    "/build-artifacts/{project_id}/{job_id}/{artifact_path:path}",
    methods=["GET", "HEAD"],
)
async def proxy_project_build_artifact(
    project_id: int,
    job_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    artifact_path: str = "",
) -> Response:
    """公开代理构建产物中的静态文件；匿名访问已关闭。"""

    raise AppException(
        status_code=404,
        code="BUILD_ARTIFACT_ANONYMOUS_DISABLED",
        detail="构建产物匿名访问已关闭，请使用受保护的私有构建授权接口浏览或下载。",
        headers={"Cache-Control": "no-store"},
    )
