"""文件功能：提供 Runtime 读取项目级 app/icon/theme 配置的只读 YAML 接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.services.auth_service import AuthContext
from app.services.project_config_service import ProjectConfigName, ProjectConfigService
from app.services.project_service import ProjectService

router = APIRouter()


@router.get("/api/runtime/projects/{project_id}/configs/{config_file_name}")
async def get_runtime_project_config(
    project_id: int,
    config_file_name: str,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """按文件名返回项目级 YAML 配置，严格校验登录用户项目访问权限 (W11)。"""

    await ProjectService(session).get(project_id, user_id=current.user.id)
    config_name = _parse_config_name(config_file_name)
    config_text = await ProjectConfigService(session).get_config_text(project_id, config_name)
    return Response(
        content=config_text,
        media_type="text/yaml; charset=utf-8",
        headers={"Cache-Control": "private, no-cache"},
    )



def _parse_config_name(config_file_name: str) -> ProjectConfigName:
    """将请求中的配置文件名映射为内部配置分类。"""

    file_name_map: dict[str, ProjectConfigName] = {
        "app.config.yaml": "app",
        "icons.config.yaml": "icons",
        "themes.config.yaml": "themes",
    }
    config_name = file_name_map.get(str(config_file_name or "").strip())
    if config_name is None:
        from app.core.exceptions import AppException

        raise AppException(status_code=404, code="PROJECT_CONFIG_FILE_NOT_FOUND", detail="请求的配置文件不存在。")
    return config_name
