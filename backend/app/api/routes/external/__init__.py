"""文件功能：聚合 External API v1 所有资源子路由并导出统一 v1_router。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.external.assets import router as assets_router
from app.api.routes.external.builds import router as builds_router
from app.api.routes.external.components import router as components_router
from app.api.routes.external.mutations import router as mutations_router
from app.api.routes.external.pages import router as pages_router
from app.api.routes.external.projects import router as projects_router
from app.api.routes.external.styles import router as styles_router
from app.api.routes.external.system import router as system_router
from app.api.routes.external.themes import router as themes_router
from app.api.routes.external.validate import router as validate_router
from app.api.routes.external.workspaces import router as workspaces_router

v1_router = APIRouter(prefix="/v1")

v1_router.include_router(system_router, tags=["External System"])
v1_router.include_router(workspaces_router, prefix="/workspaces", tags=["External Workspaces"])
v1_router.include_router(projects_router, prefix="/projects", tags=["External Projects"])
v1_router.include_router(pages_router, tags=["External Pages"])
v1_router.include_router(components_router, prefix="/components", tags=["External Components"])
v1_router.include_router(assets_router, prefix="/assets", tags=["External Assets"])
v1_router.include_router(themes_router, prefix="/themes", tags=["External Themes"])
v1_router.include_router(styles_router, prefix="/styles", tags=["External Styles"])
v1_router.include_router(builds_router, tags=["External Builds"])
v1_router.include_router(mutations_router, prefix="/jobs/mutations", tags=["External Mutations"])
v1_router.include_router(validate_router, prefix="/validate", tags=["External Validation"])
