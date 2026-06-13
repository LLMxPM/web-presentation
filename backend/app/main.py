"""文件功能：定义 FastAPI 应用入口、生命周期和全局异常处理。"""

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager, suppress
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.ai.agent_factory import AIAgentFactory
from app.ai.db import build_agno_db
from app.ai.registry import AgentRegistry
from app.api.router import api_router
from app.api.routes import build_artifacts, public_assets, internal_runtime, runtime_configs, well_known, preview
from app.core.config import AppSettings, get_settings
from app.core.exceptions import AppException
from app.core.logging_config import bind_request_id, configure_app_logging, reset_request_id, sanitize_log_text
from app.db.errors import (
    DatabaseConnectivityError,
    format_database_connectivity_error,
    is_database_connectivity_error,
)
from app.db.session import get_session_factory
from app.services.ai_session_retention_service import (
    build_ai_session_retention_service,
    run_ai_session_retention_loop,
    should_start_ai_session_retention_task,
)
from app.services.bootstrap_service import BootstrapService
from app.services.object_storage_service import ObjectStorageService
from app.services.page_screenshot_job_service import (
    recover_interrupted_screenshot_jobs_on_startup,
    run_page_screenshot_queue_loop,
)
from app.services.project_build_service import recover_interrupted_build_jobs_on_startup
from app.services.redis_runtime_client import ensure_redis_runtime_available


logger = logging.getLogger(__name__)
access_logger = logging.getLogger("app.access")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时校验数据库、Redis 运行态并初始化默认管理员。"""

    ai_session_cleanup_task: asyncio.Task[None] | None = None
    page_screenshot_queue_task: asyncio.Task[None] | None = None
    try:
        session_factory = get_session_factory()
        await BootstrapService(session_factory).ensure_default_admin()
        ensure_redis_runtime_available()
        await recover_interrupted_build_jobs_on_startup(session_factory)
        await recover_interrupted_screenshot_jobs_on_startup(session_factory)
        page_screenshot_queue_task = _start_page_screenshot_queue_task()
        ai_session_cleanup_task = _start_ai_session_retention_task(app, get_settings())
    except SQLAlchemyError as exc:
        if is_database_connectivity_error(exc):
            _raise_database_connectivity_error(exc, phase="Backend 启动时")
        raise
    try:
        yield
    finally:
        if page_screenshot_queue_task is not None:
            await _stop_background_task(page_screenshot_queue_task)
        if ai_session_cleanup_task is not None:
            await _stop_background_task(ai_session_cleanup_task)


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

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_exception(_: Request, exc: RequestValidationError) -> JSONResponse:
        validation_errors = _sanitize_validation_errors(exc.errors())
        first_error = validation_errors[0] if validation_errors else {}
        message = _format_request_validation_message(first_error)
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": message,
                "detail": validation_errors,
            },
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


def _format_request_validation_message(error: dict) -> str:
    """将 FastAPI 参数校验错误转换为面向前端用户的中文提示。"""

    loc = error.get("loc")
    field_path = ".".join(str(item) for item in loc if item not in {"body", "query", "path"}) if isinstance(loc, (list, tuple)) else ""
    raw_message = str(error.get("msg") or "").strip()
    if field_path and raw_message:
        return f"请求参数 {field_path} 不符合要求：{raw_message}"
    if field_path:
        return f"请求参数 {field_path} 不符合要求。"
    return "请求参数不符合要求，请检查后再提交。"


def _sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """清洗 FastAPI 校验错误，确保 detail 可被 JSONResponse 序列化。"""

    return [_sanitize_jsonable(error) for error in errors]


def _sanitize_jsonable(value: Any) -> Any:
    """递归转换异常等非 JSON 友好对象，保留校验错误的结构化字段。"""

    if isinstance(value, dict):
        return {str(key): _sanitize_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_jsonable(item) for item in value]
    if isinstance(value, Exception):
        return str(value)
    return value


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


def _start_ai_session_retention_task(app: FastAPI, settings: AppSettings) -> asyncio.Task[None] | None:
    """按配置启动 AI session 历史清理后台任务。"""

    agno_db = getattr(app.state, "ai_db", None)
    if not should_start_ai_session_retention_task(settings, agno_db):
        return None

    service = build_ai_session_retention_service(settings, agno_db)
    logger.info(
        "AI 会话历史清理后台任务已启动。",
        extra={
            "event": "ai.session_retention.started",
            "retention_days": settings.ai_session_retention_days,
            "interval_seconds": settings.ai_session_cleanup_interval_seconds,
            "batch_size": settings.ai_session_cleanup_batch_size,
        },
    )
    return asyncio.create_task(
        run_ai_session_retention_loop(
            service,
            interval_seconds=settings.ai_session_cleanup_interval_seconds,
        ),
        name="ai-session-retention-cleanup",
    )


def _start_page_screenshot_queue_task() -> asyncio.Task[None]:
    """启动页面截图队列后台任务。"""

    return asyncio.create_task(
        run_page_screenshot_queue_loop(get_session_factory()),
        name="page-screenshot-queue",
    )


async def _stop_background_task(task: asyncio.Task[None]) -> None:
    """取消后台任务并等待退出，避免应用关闭时遗留清理协程。"""

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


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
