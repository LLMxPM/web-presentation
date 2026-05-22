"""文件功能：提供构建产物 ZIP 的公开静态站点代理入口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.services.project_build_artifact_proxy_service import ProjectBuildArtifactProxyService

router = APIRouter()


@router.get("/build-artifacts/{project_id}/{job_id}")
@router.get("/build-artifacts/{project_id}/{job_id}/{artifact_path:path}")
async def proxy_project_build_artifact(
    project_id: int,
    job_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    artifact_path: str = "",
) -> Response:
    """公开代理构建产物中的静态文件，支持 SPA 页面路由回退。"""

    result = await ProjectBuildArtifactProxyService(session).get_artifact_file(
        project_id=project_id,
        job_id=job_id,
        request_path=artifact_path,
    )
    return Response(content=result.content, media_type=result.media_type, headers=result.headers)
