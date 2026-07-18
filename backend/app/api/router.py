"""文件功能：聚合后台管理端所有 API 路由。"""

from fastapi import APIRouter

from app.api.routes import (
    agents,
    asset_render_hint_backfill_jobs,
    assets,
    auth,
    build_jobs,
    client_logs,
    components,
    fonts,
    llm,
    page_screenshot_jobs,
    page_visual_edit,
    pages,
    preview,
    projects,
    runtime_kit,
    styles,
    template_packages,
    themes,
    users,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(agents.router, tags=["agents"])
api_router.include_router(client_logs.router, prefix="/client-logs", tags=["client-logs"])
api_router.include_router(llm.router, tags=["llm"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(pages.router, prefix="/pages", tags=["pages"])
api_router.include_router(page_visual_edit.router, prefix="/pages", tags=["page-visual-edit"])
api_router.include_router(page_screenshot_jobs.router, tags=["page-screenshot-jobs"])
api_router.include_router(components.router, prefix="/components", tags=["components"])
api_router.include_router(runtime_kit.router, prefix="/runtime-kit", tags=["runtime-kit"])
api_router.include_router(assets.router, tags=["assets"])
api_router.include_router(asset_render_hint_backfill_jobs.router, tags=["asset-render-hint-backfill-jobs"])
api_router.include_router(fonts.router, tags=["fonts"])
api_router.include_router(themes.router, tags=["themes"])
api_router.include_router(styles.router, tags=["styles"])
api_router.include_router(template_packages.router, tags=["template-packages"])
api_router.include_router(preview.router_admin, prefix="/projects", tags=["preview"])
api_router.include_router(build_jobs.router, tags=["build-jobs"])
