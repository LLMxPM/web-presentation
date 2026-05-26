"""文件功能：定义 FastAPI 应用入口、生命周期和全局异常处理。"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.ai.agent_factory import AIAgentFactory
from app.ai.db import build_agno_db
from app.ai.registry import AgentRegistry
from app.ai.run_background import AgentBackgroundRunManager
from app.api.router import api_router
from app.api.routes import build_artifacts, public_assets, internal_runtime, runtime_configs, well_known, preview
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging_config import bind_request_id, configure_app_logging, reset_request_id, sanitize_log_text
from app.db.errors import (
    DatabaseConnectivityError,
    format_database_connectivity_error,
    is_database_connectivity_error,
)
from app.db.session import get_session_factory
from app.services.bootstrap_service import BootstrapService
from app.services.ai_agent_run_service import recover_ai_agent_runs_on_startup
from app.services.object_storage_service import ObjectStorageService
from app.services.project_build_service import recover_interrupted_build_jobs_on_startup
from app.services.redis_runtime_client import ensure_redis_runtime_available


logger = logging.getLogger(__name__)
access_logger = logging.getLogger("app.access")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时校验数据库、Redis 运行态并初始化默认管理员。"""

    try:
        session_factory = get_session_factory()
        await BootstrapService(session_factory).ensure_default_admin()
        ensure_redis_runtime_available()
        await recover_interrupted_build_jobs_on_startup(session_factory)
        ai_db = getattr(app.state, "ai_db", None)
        if getattr(app.state, "ai_run_manager", None) is not None:
            await recover_ai_agent_runs_on_startup(session_factory, ai_db=ai_db)
    except SQLAlchemyError as exc:
        if is_database_connectivity_error(exc):
            _raise_database_connectivity_error(exc, phase="Backend 启动时")
        raise
    yield


def create_app() -> FastAPI:
    """创建应用实例并注册路由与异常处理。"""

    settings = get_settings()
    configure_app_logging(settings)
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")
    app.include_router(runtime_configs.router, tags=["runtime-configs"])
    app.include_router(public_assets.router, prefix="/public", tags=["public-assets"])
    app.include_router(build_artifacts.router, tags=["build-artifacts"])
    app.include_router(preview.router_public, tags=["preview"])
    app.include_router(internal_runtime.router, tags=["internal-runtime"])
    app.include_router(well_known.router, tags=["well-known"])

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> JSONResponse:
        """返回容器存活状态；不触发数据库和外部服务探测。"""

        return JSONResponse({"status": "ok"})

    _mount_ai_runtime(app)
    app.mount("/media", StaticFiles(directory=ObjectStorageService().ensure_local_root()), name="media")

    @app.middleware("http")
    async def bind_request_context(request: Request, call_next):  # noqa: ANN001
        """为每个请求绑定 request_id，并输出安全访问日志。"""

        request_id = _resolve_request_id(request)
        token = bind_request_id(request_id)
        start_time = time.perf_counter()
        path = request.url.path
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.exception(
                "Backend 请求出现未处理异常。",
                extra={
                    "event": "http.request.failed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                },
            )
            reset_request_id(token)
            raise

        response.headers["X-Request-ID"] = request_id
        if settings.access_log_enabled and path != "/healthz":
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            access_logger.info(
                "Backend 请求完成。",
                extra={
                    "event": "http.request.completed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": request.client.host if request.client else "",
                },
            )
        reset_request_id(token)
        return response

    @app.exception_handler(AppException)
    async def handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
        content = {"code": exc.code, "message": exc.detail}
        if exc.data is not None:
            content["data"] = exc.data
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_sqlalchemy_exception(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        if is_database_connectivity_error(exc):
            message = format_database_connectivity_error(exc, settings.database_url, phase="Backend 请求时")
            logger.error("%s", message)
            return JSONResponse(
                status_code=503,
                content={"code": "DATABASE_UNAVAILABLE", "message": "数据库连接不可用，请稍后重试。"},
            )
        raise exc

    return app


def _mount_ai_runtime(app: FastAPI) -> None:
    """把 Agno 会话库与动态 Agent 注册表挂载到当前 FastAPI 应用。"""

    settings = get_settings()
    if not settings.ai_enabled:
        return

    agno_db = build_agno_db()
    registry = AgentRegistry(
        AIAgentFactory(
            agno_db=agno_db,
            session_factory=get_session_factory(),
        )
    )
    app.state.ai_registry = registry
    app.state.ai_db = agno_db
    app.state.ai_run_manager = AgentBackgroundRunManager(session_factory=get_session_factory())


def _raise_database_connectivity_error(exc: SQLAlchemyError, *, phase: str) -> None:
    """将底层连库异常压缩为一条安全日志，并阻止原始调用栈继续向外展示。"""

    message = format_database_connectivity_error(exc, get_settings().database_url, phase=phase)
    logger.error("%s", message)
    raise DatabaseConnectivityError(message) from None


def _resolve_request_id(request: Request) -> str:
    """优先使用上游请求 ID；缺失或非法时生成短 ID。"""

    raw_request_id = request.headers.get("x-request-id") or ""
    normalized = "".join(ch for ch in sanitize_log_text(raw_request_id, max_length=128) if ch.isalnum() or ch in "-_.")
    if normalized:
        return normalized[:128]
    return f"req-{uuid.uuid4().hex[:16]}"


app = create_app()


def main() -> None:
    """使用当前配置启动开发服务器。"""

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_reload,
        access_log=False,
        log_config=None,
    )
