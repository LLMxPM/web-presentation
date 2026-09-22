"""文件功能：独立 Renderer 执行服务入口，单槽接管远程渲染 attempt。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router, set_slot
from app.config import get_renderer_settings
from app.control.slot import SlotController

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时创建单槽控制器，退出时限时回收执行。"""

    settings = get_renderer_settings()
    slot = SlotController(worker_id=settings.render_worker_id, worker_epoch=settings.render_worker_epoch)
    set_slot(slot)
    logger.info(
        "Renderer 执行服务已启动。",
        extra={
            "event": "renderer.started",
            "worker_id": settings.render_worker_id,
            "worker_epoch": settings.render_worker_epoch,
        },
    )
    try:
        yield
    finally:
        await slot.shutdown()
        logger.info("Renderer 执行服务已停止。", extra={"event": "renderer.stopped"})


def create_app() -> FastAPI:
    """创建 Renderer FastAPI 应用。"""

    settings = get_renderer_settings()
    app = FastAPI(title="web-presentation-renderer", lifespan=lifespan)
    app.include_router(router)
    logger.info("Renderer 协议版本：%s profile=%s", settings.protocol_version, settings.render_profile_digest)
    return app


app = create_app()
