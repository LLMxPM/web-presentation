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
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.ai.registry import AgentRegistry
from app.ai.background_run_manager import AgentBackgroundRunManager
from app.ai.run_recovery import recover_interrupted_agent_runs_on_startup
from app.ai.external_task_queue import run_ai_external_task_coordinator
from app.ai.component_mutation_queue import (
    recover_interrupted_component_mutation_tasks,
    run_ai_component_mutation_queue_loop,
)
from app.ai.page_mutation_queue import (
    recover_interrupted_ai_page_mutation_jobs_on_startup,
    run_ai_page_mutation_queue_loop,
)
from app.ai.image_generation_queue import (
    recover_interrupted_image_generation_jobs_on_startup,
    run_ai_image_generation_queue_loop,
)
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
from app.db import metrics as write_path_metrics
from app.db.session import get_session_factory
from app.db.sqlite_single_process import SqliteSingleProcessGuard, ensure_sqlite_single_process
from app.services.bootstrap_service import BootstrapService
from app.services.ai_model_catalog_service import AiModelCatalogService, run_model_catalog_sync_loop
from app.services.object_storage_service import ObjectStorageService
from app.services.asset_render_hint_backfill_job_service import (
    recover_interrupted_asset_render_hint_backfill_jobs_on_startup,
    run_asset_render_hint_backfill_queue_loop,
)
from app.services.mutation_job_service import (
    run_api_mutation_sweeper_loop,
    run_api_mutation_worker_loop,
)
from app.services.page_screenshot_job_service import (
    recover_interrupted_screenshot_jobs_on_startup,
    run_page_screenshot_queue_loop,
)
from app.services.page_screenshot_queue_worker import drain_page_screenshot_jobs
from app.services.project_build_service import recover_interrupted_build_jobs_on_startup
from app.services.rendering.coordinator import get_render_coordinator
from app.services.redis_runtime_client import (
    ensure_redis_runtime_available,
    resolve_runtime_state_profile,
    validate_runtime_state_deployment,
)
from app.services.runtime_artifact_store import RuntimeArtifactStore, run_runtime_artifact_sweeper


logger = logging.getLogger(__name__)
access_logger = logging.getLogger("app.access")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时校验数据库、Redis 运行态并初始化默认管理员。"""

    page_screenshot_queue_task: asyncio.Task[None] | None = None
    asset_render_hint_backfill_queue_task: asyncio.Task[None] | None = None
    runtime_artifact_sweeper_task: asyncio.Task[None] | None = None
    ai_page_mutation_queue_task: asyncio.Task[None] | None = None
    ai_image_generation_queue_task: asyncio.Task[None] | None = None
    ai_external_task_coordinator_task: asyncio.Task[None] | None = None
    ai_component_mutation_queue_task: asyncio.Task[None] | None = None
    model_catalog_sync_task: asyncio.Task[None] | None = None
    api_mutation_worker_task: asyncio.Task[None] | None = None
    api_mutation_sweeper_task: asyncio.Task[None] | None = None
    render_coordinator_task: asyncio.Task[None] | None = None
    render_coordinator = get_render_coordinator()
    agent_background_run_manager: AgentBackgroundRunManager = app.state.agent_background_run_manager
    sqlite_single_process_guard: SqliteSingleProcessGuard | None = None
    try:
        # SQLite 文件库必须单进程写入；多 worker / 共享数据卷直接拒绝启动。
        # 必须在任何数据库访问之前取得，否则并发写入会绕过单写者边界。
        sqlite_single_process_guard = ensure_sqlite_single_process(get_settings().database_url)
        app.state.sqlite_single_process_guard = sqlite_single_process_guard
        session_factory = get_session_factory()
        await BootstrapService(session_factory).ensure_default_admin()
        async with session_factory() as catalog_session:
            await AiModelCatalogService(catalog_session).ensure_minimal_catalog()
        validate_runtime_state_deployment(get_settings())
        ensure_redis_runtime_available()
        _log_runtime_state_startup(app)
        if get_settings().ai_enabled:
            await recover_interrupted_agent_runs_on_startup(session_factory)
        await recover_interrupted_build_jobs_on_startup(session_factory)
        await recover_interrupted_screenshot_jobs_on_startup(session_factory)
        await recover_interrupted_asset_render_hint_backfill_jobs_on_startup(session_factory)
        if get_settings().ai_enabled:
            await recover_interrupted_ai_page_mutation_jobs_on_startup(session_factory)
            await recover_interrupted_image_generation_jobs_on_startup(session_factory)
            await recover_interrupted_component_mutation_tasks(session_factory)
        # 远程渲染控制面：Backend 不再启动本地 Chromium，由 RenderCoordinator
        # 通过受信 Renderer Worker API 完成调度、重试与结果落库。
        page_screenshot_queue_task = _start_page_screenshot_queue_task()
        render_coordinator_task = asyncio.create_task(
            render_coordinator.run_forever(),
            name="render-coordinator",
        )
        asset_render_hint_backfill_queue_task = _start_asset_render_hint_backfill_queue_task()
        runtime_artifact_sweeper_task = asyncio.create_task(
            run_runtime_artifact_sweeper(),
            name="runtime-artifact-sweeper",
        )
        api_mutation_worker_task = asyncio.create_task(
            run_api_mutation_worker_loop(session_factory),
            name="api-mutation-worker",
        )
        api_mutation_sweeper_task = asyncio.create_task(
            run_api_mutation_sweeper_loop(session_factory),
            name="api-mutation-sweeper",
        )
        if get_settings().ai_enabled:
            ai_page_mutation_queue_task = asyncio.create_task(
                run_ai_page_mutation_queue_loop(session_factory, app=app),
                name="ai-page-mutation-queue",
            )
            ai_image_generation_queue_task = asyncio.create_task(
                run_ai_image_generation_queue_loop(session_factory, app=app),
                name="ai-image-generation-queue",
            )
            ai_external_task_coordinator_task = asyncio.create_task(
                run_ai_external_task_coordinator(session_factory, app=app),
                name="ai-external-task-coordinator",
            )
            ai_component_mutation_queue_task = asyncio.create_task(
                run_ai_component_mutation_queue_loop(session_factory),
                name="ai-component-mutation-queue",
            )
        if get_settings().ai_model_catalog_sync_enabled:
            model_catalog_sync_task = asyncio.create_task(
                run_model_catalog_sync_loop(session_factory),
                name="ai-model-catalog-sync",
            )
    except SQLAlchemyError as exc:
        if is_database_connectivity_error(exc):
            _raise_database_connectivity_error(exc, phase="Backend 启动时")
        raise
    try:
        yield
    finally:
        await agent_background_run_manager.shutdown()
        if page_screenshot_queue_task is not None:
            await _stop_background_task(page_screenshot_queue_task)
        if render_coordinator_task is not None:
            await _stop_background_task(render_coordinator_task)
        # 请求内“提交并等待”的兼容路径也会登记真实执行任务；渲染链路由
        # 协调器与 Renderer 负责回收，这里只等待领域任务安全收敛。
        await drain_page_screenshot_jobs()
        if asset_render_hint_backfill_queue_task is not None:
            await _stop_background_task(asset_render_hint_backfill_queue_task)
        if runtime_artifact_sweeper_task is not None:
            await _stop_background_task(runtime_artifact_sweeper_task)
        if api_mutation_worker_task is not None:
            await _stop_background_task(api_mutation_worker_task)
        if api_mutation_sweeper_task is not None:
            await _stop_background_task(api_mutation_sweeper_task)
        if ai_page_mutation_queue_task is not None:
            await _stop_background_task(ai_page_mutation_queue_task)
        if ai_image_generation_queue_task is not None:
            await _stop_background_task(ai_image_generation_queue_task)
        if ai_external_task_coordinator_task is not None:
            await _stop_background_task(ai_external_task_coordinator_task)
        if ai_component_mutation_queue_task is not None:
            await _stop_background_task(ai_component_mutation_queue_task)
        if model_catalog_sync_task is not None:
            await _stop_background_task(model_catalog_sync_task)
        # 所有后台写入任务都已停止，最后才释放单进程写锁。
        if sqlite_single_process_guard is not None:
            sqlite_single_process_guard.release()
            app.state.sqlite_single_process_guard = None


def create_app() -> FastAPI:
    """创建应用实例并注册路由与异常处理。"""

    settings = get_settings()
    configure_app_logging(settings)
    if settings.ai_test_mode == "mock":
        # mock 模式全局禁止真实模型网络请求；未被测试分派接管的
        # 模型调用会立即失败，FunctionModel 不受影响。
        from app.ai.testing.dispatch import enforce_mock_model_request_fence

        enforce_mock_model_request_fence()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.agent_background_run_manager = AgentBackgroundRunManager()
    # 单进程守卫在 lifespan 中获取：本模块底部有模块级 create_app()，
    # 在导入期抢文件锁会让任何 import app 的脚本/测试都可能失败。
    app.state.sqlite_single_process_guard = None
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

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        """就绪探针：数据库可连通、渲染 Worker 已配置；不替代 /healthz 存活语义。

        不探测 Renderer 存活：外部服务抖动不应把 Backend 打成 not_ready。
        """

        checks: dict[str, Any] = {}

        try:
            async with get_session_factory()() as session:
                await session.execute(text("SELECT 1"))
            checks["database_reachable"] = True
        except Exception as exc:  # noqa: BLE001
            checks["database_reachable"] = False
            checks["database_error"] = type(exc).__name__

        checks["render_workers_configured"] = bool(settings.render_workers_config)
        checks["sqlite_single_process"] = app.state.sqlite_single_process_guard is not None
        # 静态元数据：只报告后端类型与临时性，不做连接探测，避免瞬断触发容器重启。
        runtime_state_backend, runtime_state_ephemeral = resolve_runtime_state_profile(settings.redis_url)
        checks["runtime_state_backend"] = runtime_state_backend
        checks["runtime_state_ephemeral"] = runtime_state_ephemeral

        ready = checks["database_reachable"] and checks["render_workers_configured"]
        return JSONResponse(
            {"status": "ready" if ready else "not_ready", "checks": checks},
            status_code=200 if ready else 503,
        )

    @app.get("/metrics/db-write", include_in_schema=False)
    async def db_write_metrics() -> JSONResponse:
        """导出进程内 SQLite 写路径打点快照，供基线采集；默认关闭时仍返回 enabled=false。"""

        return JSONResponse(write_path_metrics.snapshot())

    @app.get("/metrics/runtime-state", include_in_schema=False)
    async def runtime_state_metrics() -> JSONResponse:
        """导出运行态后端聚合指标，供容量基线与排障使用。

        只返回后端类型与聚合计数/字节，不返回 key 名称、payload 内容或连接串。
        """

        store = RuntimeArtifactStore()
        stats = store.runtime.stats()
        return JSONResponse(stats.as_dict())

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
            headers=exc.headers,
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
    """把动态 Agent 注册表挂载到当前 FastAPI 应用。"""

    settings = get_settings()
    if not settings.ai_enabled:
        return

    app.state.ai_registry = AgentRegistry()


def _start_page_screenshot_queue_task() -> asyncio.Task[None]:
    """启动页面截图队列后台任务。"""

    return asyncio.create_task(
        run_page_screenshot_queue_loop(get_session_factory()),
        name="page-screenshot-queue",
    )


def _start_asset_render_hint_backfill_queue_task() -> asyncio.Task[None]:
    """启动资源比例回填队列后台任务。"""

    return asyncio.create_task(
        run_asset_render_hint_backfill_queue_loop(get_session_factory()),
        name="asset-render-hint-backfill-queue",
    )


async def _stop_background_task(task: asyncio.Task[None]) -> None:
    """取消后台任务并等待退出，避免应用关闭时遗留清理协程。"""

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _log_runtime_state_startup(app: FastAPI) -> None:
    """记录运行态后端类型、临时性、进程边界与清扫周期，不输出 URL 或 key 内容。"""

    settings = get_settings()
    backend_kind, ephemeral = resolve_runtime_state_profile(settings.redis_url)
    logger.info(
        "运行态存储后端已就绪。",
        extra={
            "event": "runtime_state.startup",
            "runtime_state_backend": backend_kind,
            "runtime_state_ephemeral": ephemeral,
            "runtime_state_sweep_interval_seconds": round(
                float(settings.runtime_artifact_sweep_interval_seconds), 3
            )
            if ephemeral
            else None,
            "sqlite_single_process": app.state.sqlite_single_process_guard is not None,
        },
    )


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
