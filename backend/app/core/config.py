"""文件功能：集中定义应用配置，并从环境变量与 .env 文件读取运行参数。"""

from pathlib import Path
from functools import lru_cache
import json
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_DIR = Path(__file__).resolve().parents[2]


def parse_runtime_target_list(raw: str) -> list[str]:
    """解析多副本 Runtime 目标列表：支持 JSON 字符串数组或逗号分隔。

    返回去重、去尾斜杠后的地址列表；空配置返回空列表，由调用方决定回退。
    非法 JSON 数组在启动期抛错，避免运行期才发现配置不可用。
    """

    text = str(raw or "").strip()
    if not text:
        return []

    items: list[object]
    if text.startswith("["):
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Runtime 目标列表必须是合法 JSON 数组：{text}") from exc
        if not isinstance(decoded, list):
            raise ValueError(f"Runtime 目标列表 JSON 必须是数组：{text}")
        items = decoded
    else:
        items = text.split(",")

    resolved: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = str(item or "").strip().rstrip("/")
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return resolved


class AppSettings(BaseSettings):
    """应用配置模型，负责约束数据库、鉴权和跨域等关键参数。"""

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "页面管理后台"
    app_version: str = "1.0.0"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_reload: bool = True
    app_timezone: str = "Asia/Shanghai"
    log_level: str = "INFO"
    log_format: str = "json"
    access_log_enabled: bool = True
    client_error_log_enabled: bool = True
    client_error_log_max_bytes: int = 16384
    database_url: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/web_presentation"
    database_connect_timeout_seconds: float = 10.0
    # SQLite 写路径打点：默认关闭，仅基线采集期开启（监听器本身有开销）
    database_write_path_metrics_enabled: bool = False
    default_admin_username: str = "admin"
    default_admin_password: str = "Admin123456"
    default_admin_display_name: str = "平台系统管理员"
    session_cookie_name: str = "wp_user_session"
    session_ttl_hours: int = 24
    session_secure: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"])
    runtime_base_url: str = "http://127.0.0.1:7373"
    # 分角色部署时按职责指定 Runtime 内部目标；留空回退 runtime_base_url。
    runtime_preview_base_url: str = ""
    runtime_check_base_url: str = ""
    # 计算角色多副本目标列表：JSON 数组或逗号分隔；留空回退对应单地址。
    runtime_check_base_urls: str = ""
    # 选址冷却：同一目标连续失败达到阈值后短暂跳过，冷却到期自动恢复参与轮询。
    runtime_target_failure_threshold: int = 3
    runtime_target_cooldown_seconds: float = 15.0
    # 全链路准入：Backend 同时在途的 check/light 内部调用上限；<=0 表示不限制。
    # light（可视化编辑、资源比例测量）与 check 独立计数，避免长编译诊断队头阻塞轻量工具。
    runtime_check_max_inflight: int = 16
    runtime_light_max_inflight: int = 16
    runtime_public_base_url: str | None = None
    runtime_shared_secret: str = "change-me"
    runtime_service_token_audience: str = "runtime-backend"
    # Runtime RS256 签名身份：多 Backend 必须共享同一私钥；轮换期用 previous_keys 保留旧钥验签。
    # 读取顺序：RUNTIME_RSA_PRIVATE_KEY（PEM）→ RUNTIME_RSA_PRIVATE_KEY_FILE（共享路径/密钥挂载）
    # → 旧版本地 data/runtime_rsa_key.pem → 单实例自动生成。
    runtime_rsa_private_key: str = ""
    runtime_rsa_private_key_file: str | None = None
    runtime_rsa_key_id: str = "default-key-1"
    # 轮换期验签旧钥：JSON 数组，每项 {"kid": "...", "private_key_file": "..."} 或 {"kid": "...", "private_key": "PEM..."}。
    runtime_rsa_previous_keys: list[dict[str, str]] = Field(default_factory=list)
    # 仅单实例/Lite 允许缺省时自动生成本地密钥；多副本必须显式提供共享私钥。
    runtime_rsa_allow_auto_generate: bool = True
    # 声明本部署运行多 Backend 副本：启动期强制共享签名密钥、AI/Renderer 凭证与对象存储前提。
    backend_multi_instance: bool = False
    # local 对象存储位于已验证共享卷时显式确认；多 Backend 下默认要求 s3。
    object_storage_shared_volume: bool = False
    runtime_request_timeout_seconds: float = 10.0
    runtime_diagnostics_request_timeout_seconds: float = 180.0
    # 项目整包构建持久领取：Runtime Build Worker 通过 claim API 拉取并 renew 续租。
    # 租约时长仍是未续租场景的安全下限；重试预算与总 deadline 由 Backend 统一裁决。
    project_build_lease_seconds: int = 960
    project_build_max_attempts: int = 3
    # 任务创建即确定的绝对 wall-clock 期限：领取租约、attempt 令牌 TTL、续租后的
    # 新租约与 Runtime 执行预算全部裁剪到该时刻之前，超期即不再承认所有权。
    project_build_total_deadline_seconds: int = 3600
    # recovery-only 队列循环的扫描间隔；真正执行由 Runtime Build Worker 拉取。
    project_build_queue_poll_interval_seconds: float = 1.0
    # Runtime Build Worker 领取任务时使用的共享服务凭证；空值时拒绝 claim（fail-closed），
    # 本地开发/测试可注入固定值。与 RENDER_SERVICE_CREDENTIAL 同属内部服务身份。
    # 生产优先使用 *_FILE（Docker secret 挂载），避免密钥进入环境变量。
    runtime_build_worker_credential: str = ""
    runtime_build_worker_credential_file: str | None = None
    # Runtime 回传构建归档的接收上限：流式写入过程中即时判定并中止，
    # 不把体量不可信的归档整包读进 Backend 进程。
    project_build_artifact_max_bytes: int = 512 * 1024 * 1024
    backend_public_base_url: str = "http://127.0.0.1:8000"
    # 远程渲染执行服务配置（Backend 不再安装或持有 Playwright/Chromium）
    render_workers_config: list[dict[str, str]] = Field(
        default_factory=lambda: [{"worker_id": "renderer-local", "base_url": "http://127.0.0.1:7400"}]
    )
    render_service_credential_file: str | None = None
    render_service_credential: str = ""
    render_profile_manifest: str | None = None
    render_profile_digest: str = "profile.v1"
    render_global_concurrency: int = 1
    render_workspace_concurrency: int = 1
    render_queue_size: int = 64
    render_workspace_queue_size: int = 16
    render_request_timeout_seconds: float = 120.0
    render_max_attempts: int = 3
    render_scheduler_poll_interval_seconds: float = 0.25
    render_wait_poll_interval_seconds: float = 0.25
    render_attempt_lease_seconds: float = 180.0
    render_unknown_reconcile_after_seconds: float = 30.0
    render_artifact_max_bytes: int = 32 * 1024 * 1024
    render_runtime_navigation_base_url: str | None = None
    render_runtime_asset_base_url: str | None = None
    render_platform_asset_base_url: str | None = None
    ai_enabled: bool = True
    ai_test_mode: str = "disabled"
    ai_secret_encryption_key: str = ""
    ai_agent_os_id: str = "backend-agentos"
    ai_agent_token_ttl_seconds: int = 600
    ai_tool_auth_window_seconds: int = 1800
    ai_tool_auth_max_seconds: int = 7200
    ai_agent_stream_idle_timeout_seconds: float = 180.0
    ai_run_owner_ttl_seconds: float = Field(default=90.0, ge=3)
    ai_run_owner_heartbeat_seconds: float = Field(default=10.0, ge=1)
    ai_run_owner_sweep_seconds: float = Field(default=10.0, ge=1)
    ai_agent_tool_stream_idle_timeout_seconds: float = 600.0
    ai_external_task_enqueue_timeout_seconds: float = 30.0
    ai_llm_http_trace_enabled: bool = False
    ai_llm_http_trace_dir: str = ".tmp/llm-http-trace"
    ai_llm_http_trace_body_max_bytes: int = 200_000
    ai_model_catalog_sync_enabled: bool = True
    ai_image_transport_mode: str = "auto"
    ai_image_attachment_max_bytes: int = 10 * 1024 * 1024
    ai_image_model_url_reuse_window_seconds: int = 7200
    ai_image_model_url_ttl_seconds: int = 21600
    ai_image_model_url_expiry_safety_seconds: int = 300
    ai_image_history_max_hydrated_images: int = 10
    ai_image_history_max_hydrated_bytes: int = 30 * 1024 * 1024
    ai_page_mutation_concurrency: int = 1
    ai_page_mutation_max_active_jobs: int = 16
    ai_page_mutation_max_batch_size: int = 16
    ai_page_mutation_poll_interval_seconds: float = 0.5
    ai_external_task_poll_interval_seconds: float = 0.5
    ai_image_generation_poll_interval_seconds: float = 0.5
    ai_image_generation_heartbeat_seconds: int = 30
    ai_image_generation_lease_seconds: int = 300
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_key_prefix: str = "web_presentation"
    redis_healthcheck_timeout_seconds: float = 2.0
    runtime_preview_artifact_ttl_seconds: int = 3600
    runtime_artifact_sweep_interval_seconds: float = 30.0
    runtime_build_state_ttl_seconds: int = 604800
    # 进程内 memory:// 运行态的有限 payload 预算：2C4G Lite 实测混合负载峰值约 105MB，
    # 128MiB 留出余量并封住 1 小时 TTL 窗口内无限增长；超限在写入生效前拒绝。
    runtime_state_memory_max_bytes: int = 134217728
    runtime_state_memory_max_item_bytes: int = 16777216
    durable_job_lease_seconds: int = 300
    durable_job_heartbeat_seconds: int = 30
    page_screenshot_default_viewport_width: int = 1920
    page_screenshot_default_viewport_height: int = 1080
    page_screenshot_max_viewport_width: int = 4096
    page_screenshot_max_viewport_height: int = 4096
    page_screenshot_timeout_seconds: float = 45.0
    page_screenshot_visual_ready_timeout_seconds: float = 25.0
    page_screenshot_batch_concurrency: int = 2
    page_screenshot_queue_concurrency: int = 1
    page_screenshot_queue_poll_interval_seconds: float = 1.0
    page_screenshot_ai_wait_timeout_seconds: float = 90.0
    asset_render_hint_backfill_queue_concurrency: int = 1
    asset_render_hint_backfill_queue_poll_interval_seconds: float = 1.0
    asset_render_hint_backfill_job_lease_seconds: int = 180
    page_screenshot_local_root: str = "data"
    page_screenshot_browser_executable_path: str | None = None
    page_screenshot_backend_base_url: str | None = None
    page_screenshot_runtime_public_base_url: str | None = None
    object_cache_idle_days: int = 30
    object_cache_max_bytes: int = 10737418240
    object_cache_sweep_interval_seconds: int = 21600
    
    # 资源管理器配置
    asset_storage_driver: str = "local"
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str | None = None
    s3_public_bucket: str | None = None
    s3_region: str | None = None
    s3_public_base_url: str | None = None

    # Mutation 任务与 External API 租约/幂等/PAT 配置
    mutation_job_lease_seconds: int = 45
    mutation_job_heartbeat_seconds: int = 15
    mutation_job_recovery_interval_seconds: int = 30
    mutation_job_max_attempts: int = 3
    mutation_job_retention_days: int = 7
    mutation_job_idle_poll_interval_seconds: float = 1.0
    mutation_job_error_poll_interval_seconds: float = 2.0
    mutation_job_recovery_backoff_seconds: float = 5.0
    idempotency_retention_days: int = 14
    asset_staging_retention_hours: int = 2
    pat_max_active_tokens: int = 25
    pat_max_ttl_days: int = 365

    @model_validator(mode="after")
    def validate_ai_run_owner_budget(self) -> "AppSettings":
        """存活租约至少覆盖三个心跳周期，避免正常调度抖动误判失效。"""

        if self.ai_run_owner_ttl_seconds < self.ai_run_owner_heartbeat_seconds * 3:
            raise ValueError("AI_RUN_OWNER_TTL_SECONDS 必须至少为心跳周期的三倍。")
        return self

    @field_validator("app_timezone")
    @classmethod
    def validate_app_timezone(cls, value: str) -> str:
        """校验业务时区配置有效，避免运行期再出现不可识别的时区字符串。"""

        normalized = value.strip()
        if not normalized:
            raise ValueError("APP_TIMEZONE 不能为空。")

        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"APP_TIMEZONE 配置无效：{normalized}") from exc

        return normalized

    @field_validator("database_connect_timeout_seconds")
    @classmethod
    def validate_database_connect_timeout_seconds(cls, value: float) -> float:
        """校验数据库连接超时时间有效，避免启动期长时间卡在网络探测。"""

        if value <= 0:
            raise ValueError("数据库连接超时时间必须大于 0。")
        return value

    @field_validator("asset_storage_driver")
    @classmethod
    def validate_asset_storage_driver(cls, value: str) -> str:
        """校验统一对象存储策略驱动。"""

        normalized = value.strip().lower()
        if normalized not in {"local", "s3"}:
            raise ValueError("ASSET_STORAGE_DRIVER 当前仅支持 local, s3。")
        return normalized

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """校验日志等级配置，避免启动后才发现不可识别等级。"""

        normalized = value.strip().upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL 仅支持 DEBUG, INFO, WARNING, ERROR, CRITICAL。")
        return normalized

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, value: str) -> str:
        """校验日志格式配置；生产默认使用 JSON Lines。"""

        normalized = value.strip().lower()
        if normalized not in {"json", "text"}:
            raise ValueError("LOG_FORMAT 仅支持 json, text。")
        return normalized

    @field_validator("client_error_log_max_bytes")
    @classmethod
    def validate_client_error_log_max_bytes(cls, value: int) -> int:
        """校验浏览器错误上报日志大小上限。"""

        if value <= 0:
            raise ValueError("CLIENT_ERROR_LOG_MAX_BYTES 必须大于 0。")
        return value

    @field_validator(
        "page_screenshot_default_viewport_width",
        "page_screenshot_default_viewport_height",
        "page_screenshot_max_viewport_width",
        "page_screenshot_max_viewport_height",
        "render_global_concurrency",
        "render_workspace_concurrency",
        "render_queue_size",
        "render_workspace_queue_size",
        "render_max_attempts",
        "ai_page_mutation_concurrency",
        "ai_page_mutation_max_active_jobs",
        "ai_page_mutation_max_batch_size",
        "durable_job_lease_seconds",
        "durable_job_heartbeat_seconds",
        "page_screenshot_batch_concurrency",
        "page_screenshot_queue_concurrency",
        "asset_render_hint_backfill_queue_concurrency",
        "asset_render_hint_backfill_job_lease_seconds",
        "project_build_lease_seconds",
        "project_build_max_attempts",
        "project_build_total_deadline_seconds",
        "project_build_artifact_max_bytes",
    )
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        """校验截图与远程渲染整数配置均为正数。"""

        if value <= 0:
            raise ValueError("截图与远程渲染整数配置必须为正整数。")
        return value

    @model_validator(mode="after")
    def validate_render_legacy_env_rejected(self) -> "AppSettings":
        """旧 Playwright 运行时配置不得静默忽略，必须替换为远程渲染配置。"""

        import os

        forbidden = [
            "PLAYWRIGHT_BROWSER_POOL_SIZE",
            "PLAYWRIGHT_TASK_CONCURRENCY",
            "PLAYWRIGHT_TASK_QUEUE_SIZE",
            "PLAYWRIGHT_TASK_QUEUE_WAIT_TIMEOUT_SECONDS",
            "PLAYWRIGHT_BROWSER_REUSE_ENABLED",
            "PLAYWRIGHT_BROWSER_RECYCLE_TASK_COUNT",
            "PLAYWRIGHT_BROWSER_RECYCLE_AGE_SECONDS",
            "PAGE_SCREENSHOT_BROWSER_EXECUTABLE_PATH",
        ]
        present = [name for name in forbidden if os.environ.get(name)]
        # .env 文件中的废弃键可能被 pydantic-settings 静默丢弃，必须单独扫描。
        for env_path in _iter_settings_env_files():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or "=" not in stripped:
                        continue
                    key = stripped.split("=", 1)[0].strip().strip('"').strip("'")
                    if key in forbidden and key not in present:
                        present.append(key)
            except OSError:
                continue
        if present:
            raise ValueError(
                "检测到已废弃的本地 Playwright 配置："
                + ", ".join(present)
                + "。请改用 RENDER_WORKERS_CONFIG / RENDER_PROFILE_MANIFEST 等远程渲染配置。"
            )
        return self

    @model_validator(mode="after")
    def validate_durable_job_lease_ratio(self) -> "AppSettings":
        """确保持久化任务租约至少覆盖三个心跳周期，避免正常慢任务被抢占。"""

        if self.durable_job_lease_seconds < self.durable_job_heartbeat_seconds * 3:
            raise ValueError("DURABLE_JOB_LEASE_SECONDS 必须至少为心跳间隔的3倍。")
        if self.ai_image_generation_lease_seconds < self.ai_image_generation_heartbeat_seconds * 3:
            raise ValueError("AI_IMAGE_GENERATION_LEASE_SECONDS 必须至少为心跳间隔的3倍。")
        return self

    @model_validator(mode="after")
    def validate_legacy_build_dispatch_env_rejected(self) -> "AppSettings":
        """Backend 主动派发构建的旧 HTTP 通道已删除，相关配置必须显式清理而不是静默忽略。"""

        import os

        retired = {
            "RUNTIME_BUILD_BASE_URL": "构建改由 Runtime Build Worker 拉取，Backend 不再选址 build 目标。",
            "RUNTIME_BUILD_BASE_URLS": "构建改由 Runtime Build Worker 拉取，Backend 不再选址 build 目标。",
            "RUNTIME_BUILD_MAX_INFLIGHT": "Backend 侧不再有 build 在途准入。",
            "RUNTIME_BUILD_REQUEST_TIMEOUT_SECONDS": "Backend 侧不再有 build HTTP 超时。",
            "PROJECT_BUILD_QUEUE_CONCURRENCY": "队列循环已改为 recovery-only，并发由 Runtime Worker 消费者数决定。",
        }
        present = [name for name in retired if os.environ.get(name)]
        # .env 文件中的废弃键可能被 pydantic-settings 静默丢弃，必须单独扫描。
        for env_path in _iter_settings_env_files():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or "=" not in stripped:
                        continue
                    key = stripped.split("=", 1)[0].strip().strip('"').strip("'")
                    if key in retired and key not in present:
                        present.append(key)
            except OSError:
                continue
        if present:
            reasons = "；".join(f"{name}：{retired[name]}" for name in present)
            raise ValueError(
                "检测到已废弃的 Backend 构建派发配置：" + reasons + "。请从环境变量与 .env 模板中删除这些键。"
            )
        return self

    @field_validator(
        "page_screenshot_timeout_seconds",
        "page_screenshot_visual_ready_timeout_seconds",
        "render_request_timeout_seconds",
        "render_scheduler_poll_interval_seconds",
        "render_wait_poll_interval_seconds",
        "render_attempt_lease_seconds",
        "render_unknown_reconcile_after_seconds",
        "ai_page_mutation_poll_interval_seconds",
        "ai_external_task_poll_interval_seconds",
        "ai_image_generation_poll_interval_seconds",
        "mutation_job_idle_poll_interval_seconds",
        "mutation_job_error_poll_interval_seconds",
        "mutation_job_recovery_backoff_seconds",
        "runtime_artifact_sweep_interval_seconds",
        "runtime_diagnostics_request_timeout_seconds",
        "page_screenshot_queue_poll_interval_seconds",
        "page_screenshot_ai_wait_timeout_seconds",
        "asset_render_hint_backfill_queue_poll_interval_seconds",
    )
    @classmethod
    def validate_positive_timeout(cls, value: float) -> float:
        """校验截图与渲染超时时间有效。"""

        if value <= 0:
            raise ValueError("截图与渲染超时时间配置必须大于 0。")
        return value

    @field_validator("object_cache_idle_days", "object_cache_max_bytes")
    @classmethod
    def validate_positive_object_cache_limit(cls, value: int) -> int:
        """校验对象缓存清理阈值为正整数。"""

        if value <= 0:
            raise ValueError("对象缓存清理阈值必须大于 0。")
        return value

    @field_validator("object_cache_sweep_interval_seconds")
    @classmethod
    def validate_non_negative_object_cache_interval(cls, value: int) -> int:
        """校验对象缓存扫描间隔，允许 0 表示关闭机会式扫描。"""

        if value < 0:
            raise ValueError("对象缓存扫描间隔不能小于 0。")
        return value

    @field_validator("backend_public_base_url")
    @classmethod
    def validate_backend_public_base_url(cls, value: str) -> str:
        """校验对外可访问的 Backend 基础地址非空，便于 Runtime 拼接配置地址。"""

        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("BACKEND_PUBLIC_BASE_URL 不能为空。")
        return normalized

    @field_validator("runtime_preview_base_url", "runtime_check_base_url")
    @classmethod
    def normalize_runtime_role_base_url(cls, value: str) -> str:
        """规范化分角色 Runtime 内部目标地址；允许留空表示回退 runtime_base_url。"""

        return str(value or "").strip()

    @field_validator("runtime_check_base_urls")
    @classmethod
    def validate_runtime_role_base_urls(cls, value: str) -> str:
        """校验多副本目标列表配置可被解析；非法 JSON 在启动期直接失败。"""

        normalized = str(value or "").strip()
        parse_runtime_target_list(normalized)
        return normalized

    @field_validator("runtime_target_failure_threshold")
    @classmethod
    def validate_runtime_target_failure_threshold(cls, value: int) -> int:
        """校验选址失败阈值非负；0 表示不做冷却，仅轮询。"""

        if value < 0:
            raise ValueError("RUNTIME_TARGET_FAILURE_THRESHOLD 不能小于 0。")
        return value

    @field_validator("runtime_target_cooldown_seconds")
    @classmethod
    def validate_runtime_target_cooldown_seconds(cls, value: float) -> float:
        """校验选址冷却时长非负。"""

        if value < 0:
            raise ValueError("RUNTIME_TARGET_COOLDOWN_SECONDS 不能小于 0。")
        return value

    @field_validator("runtime_public_base_url")
    @classmethod
    def validate_runtime_public_base_url(cls, value: str | None) -> str | None:
        """校验浏览器可访问的 Runtime 公网地址；未配置时允许回退到内网地址。"""

        if value is None:
            return None

        normalized = value.strip().rstrip("/")
        return normalized or None

    @field_validator("page_screenshot_backend_base_url", "page_screenshot_runtime_public_base_url")
    @classmethod
    def validate_optional_page_screenshot_base_url(cls, value: str | None) -> str | None:
        """校验截图浏览器专用基址；未配置时由截图服务按运行环境兜底。"""

        if value is None:
            return None

        normalized = value.strip().rstrip("/")
        return normalized or None

    @field_validator("runtime_service_token_audience")
    @classmethod
    def validate_runtime_service_token_audience(cls, value: str) -> str:
        """校验 Runtime 访问 Backend 内部接口使用的 audience 非空。"""

        normalized = value.strip()
        if not normalized:
            raise ValueError("RUNTIME_SERVICE_TOKEN_AUDIENCE 不能为空。")
        return normalized

    @field_validator("runtime_rsa_key_id")
    @classmethod
    def validate_runtime_rsa_key_id(cls, value: str) -> str:
        """校验当前签名 kid 非空，避免 JWKS 与 JWT 头无法匹配。"""

        normalized = value.strip()
        if not normalized:
            raise ValueError("RUNTIME_RSA_KEY_ID 不能为空。")
        return normalized

    @field_validator("runtime_rsa_private_key", "runtime_rsa_private_key_file")
    @classmethod
    def normalize_runtime_rsa_key_source(cls, value: str | None) -> str | None:
        """规范化签名私钥来源字符串；允许留空表示走本地/自动生成回退。"""

        if value is None:
            return None
        return value.strip()

    @field_validator("runtime_rsa_previous_keys")
    @classmethod
    def validate_runtime_rsa_previous_keys(cls, value: list[dict[str, str]]) -> list[dict[str, str]]:
        """校验轮换期旧钥条目同时提供 kid 与密钥来源，避免启动后才发现轮换配置不可用。"""

        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise ValueError(f"RUNTIME_RSA_PREVIOUS_KEYS 第 {index + 1} 项必须是对象。")
            has_file = bool(str(item.get("private_key_file") or item.get("public_key_file") or "").strip())
            has_inline = bool(str(item.get("private_key") or item.get("public_key") or "").strip())
            if has_file and has_inline:
                raise ValueError(f"RUNTIME_RSA_PREVIOUS_KEYS 第 {index + 1} 项只能提供文件或内联 PEM 之一。")
            if not has_file and not has_inline:
                raise ValueError(f"RUNTIME_RSA_PREVIOUS_KEYS 第 {index + 1} 项缺少密钥内容。")
            if not str(item.get("kid") or "").strip() and not has_file:
                raise ValueError(f"RUNTIME_RSA_PREVIOUS_KEYS 第 {index + 1} 项缺少 kid。")
        return value

    @field_validator("ai_agent_os_id")
    @classmethod
    def validate_ai_identifier(cls, value: str) -> str:
        """校验 AI 鉴权相关 audience/id 非空，避免 JWT 校验目标不明确。"""

        normalized = value.strip()
        if not normalized:
            raise ValueError("AI 鉴权标识不能为空。")
        return normalized

    @field_validator("ai_agent_token_ttl_seconds", "ai_tool_auth_window_seconds", "ai_tool_auth_max_seconds")
    @classmethod
    def validate_ai_token_ttl(cls, value: int) -> int:
        """校验 AI 短期令牌 TTL 为正整数。"""

        if value <= 0:
            raise ValueError("AI Token TTL 必须大于 0。")
        return value

    @field_validator(
        "ai_agent_stream_idle_timeout_seconds",
        "ai_agent_tool_stream_idle_timeout_seconds",
        "ai_external_task_enqueue_timeout_seconds",
    )
    @classmethod
    def validate_ai_agent_stream_idle_timeout_seconds(cls, value: float) -> float:
        """校验 Agent 模型流与工具流空闲超时，避免运行长期卡在非终态。"""

        if value <= 0:
            raise ValueError("AI Agent 流空闲超时时间必须大于 0。")
        return value

    @field_validator("ai_llm_http_trace_dir")
    @classmethod
    def validate_ai_llm_http_trace_dir(cls, value: str) -> str:
        """校验 LLM HTTP trace 输出目录非空，避免开启后无明确落盘位置。"""

        normalized = value.strip()
        if not normalized:
            raise ValueError("AI_LLM_HTTP_TRACE_DIR 不能为空。")
        return normalized

    @field_validator("ai_llm_http_trace_body_max_bytes")
    @classmethod
    def validate_ai_llm_http_trace_body_max_bytes(cls, value: int) -> int:
        """校验 LLM HTTP trace 请求体记录上限，避免配置为无效大小。"""

        if value <= 0:
            raise ValueError("AI_LLM_HTTP_TRACE_BODY_MAX_BYTES 必须大于 0。")
        return value

    @field_validator("ai_tool_auth_max_seconds")
    @classmethod
    def validate_ai_tool_auth_max_seconds(cls, value: int) -> int:
        """校验工具授权绝对上限不短于滑动窗口默认值。"""

        if value < 1800:
            raise ValueError("AI 工具授权绝对上限不能小于默认滑动窗口 1800 秒。")
        return value

    @field_validator("ai_test_mode")
    @classmethod
    def validate_ai_test_mode(cls, value: str) -> str:
        """校验 AI 测试模式，仅允许关闭或 mock 两种状态。"""

        normalized = value.strip().lower()
        if normalized not in {"disabled", "mock"}:
            raise ValueError("AI_TEST_MODE 仅支持 disabled, mock。")
        return normalized

    @field_validator("ai_image_transport_mode")
    @classmethod
    def validate_ai_image_transport_mode(cls, value: str) -> str:
        """校验图片传给模型时使用的传输策略。"""

        normalized = value.strip().lower()
        if normalized not in {"auto", "url", "base64"}:
            raise ValueError("AI_IMAGE_TRANSPORT_MODE 仅支持 auto, url, base64。")
        return normalized

    @field_validator("ai_image_attachment_max_bytes")
    @classmethod
    def validate_ai_image_attachment_max_bytes(cls, value: int) -> int:
        """校验用户图片附件大小上限。"""

        if value <= 0:
            raise ValueError("AI 图片附件大小上限必须大于 0。")
        return value

    @field_validator(
        "ai_image_model_url_reuse_window_seconds",
        "ai_image_model_url_ttl_seconds",
        "ai_image_model_url_expiry_safety_seconds",
        "ai_image_history_max_hydrated_images",
        "ai_image_history_max_hydrated_bytes",
    )
    @classmethod
    def validate_ai_image_positive_ints(cls, value: int) -> int:
        """校验 Agent 图片水合与模型 URL 复用相关配置为正整数。"""

        if value <= 0:
            raise ValueError("AI 图片水合与模型 URL 复用配置必须大于 0。")
        return value

    @field_validator("redis_key_prefix")
    @classmethod
    def validate_redis_key_prefix(cls, value: str) -> str:
        """校验 Redis key 前缀，避免空前缀污染共享实例。"""

        normalized = value.strip().strip(":")
        if not normalized:
            raise ValueError("REDIS_KEY_PREFIX 不能为空。")
        return normalized

    @field_validator("redis_healthcheck_timeout_seconds")
    @classmethod
    def validate_redis_healthcheck_timeout_seconds(cls, value: float) -> float:
        """校验 Redis 健康检查超时时间。"""

        if value <= 0:
            raise ValueError("Redis 健康检查超时时间必须大于 0。")
        return value

    @field_validator(
        "runtime_preview_artifact_ttl_seconds",
        "runtime_build_state_ttl_seconds",
        "runtime_state_memory_max_bytes",
        "runtime_state_memory_max_item_bytes",
    )
    @classmethod
    def validate_positive_runtime_state_int(cls, value: int) -> int:
        """校验 Redis 临时运行态 TTL 与进程内 payload 预算为正整数。"""

        if value <= 0:
            raise ValueError("Redis 临时运行态配置必须为正整数。")
        return value

    @model_validator(mode="after")
    def validate_mutation_job_timing_constraints(self) -> "AppSettings":
        """校验 Mutation 任务租约时间不小于心跳周期的 3 倍。"""

        if self.mutation_job_lease_seconds < self.mutation_job_heartbeat_seconds * 3:
            raise ValueError("MUTATION_JOB_LEASE_SECONDS 必须大于等于 MUTATION_JOB_HEARTBEAT_SECONDS * 3。")
        return self

    @property
    def page_screenshot_local_root_path(self) -> Path:
        """返回截图本地存储根目录的绝对路径。"""

        configured_path = Path(self.page_screenshot_local_root).expanduser()
        if configured_path.is_absolute():
            return configured_path
        return (Path(__file__).resolve().parents[2] / configured_path).resolve()

    def resolve_runtime_role_base_urls(self, role: str) -> list[str]:
        """按职责解析 Runtime 内部目标列表。

        回退顺序：多副本列表（runtime_check_base_urls）→ 单地址 → runtime_base_url。
        role 取 preview / check / light；preview 当前保持单目标，多副本仅开放给计算角色。
        light（轻量工具）与 check 共用计算目标，但准入与冷却独立计数。
        构建不在这里解析：Runtime Build Worker 通过 claim API 主动拉取任务。
        """

        effective_role = "check" if role == "light" else role
        plural_mapping = {
            "check": self.runtime_check_base_urls,
        }
        targets = parse_runtime_target_list(str(plural_mapping.get(effective_role) or ""))
        if targets:
            return targets

        singular_mapping = {
            "preview": self.runtime_preview_base_url,
            "check": self.runtime_check_base_url,
        }
        configured = str(singular_mapping.get(effective_role) or "").strip().rstrip("/")
        if configured:
            return [configured]
        fallback = self.runtime_base_url.strip().rstrip("/")
        return [fallback] if fallback else []

    def resolve_runtime_role_base_url(self, role: str) -> str:
        """按职责解析 Runtime 内部目标地址，未配置角色地址时回退 runtime_base_url。

        role 取 preview / check / light；返回值已去掉末尾斜杠。
        多副本配置下返回首个目标，完整列表见 resolve_runtime_role_base_urls。
        """

        targets = self.resolve_runtime_role_base_urls(role)
        return targets[0] if targets else ""

    @property
    def ai_llm_http_trace_dir_path(self) -> Path:
        """返回 LLM HTTP trace 文件输出目录的绝对路径。"""

        configured_path = Path(self.ai_llm_http_trace_dir).expanduser()
        if configured_path.is_absolute():
            return configured_path
        return (Path(__file__).resolve().parents[2] / configured_path).resolve()


def _iter_settings_env_files() -> list[Path]:
    """列出配置可能读取的 .env 文件路径，供废弃键扫描。"""

    candidates = [
        _REPO_ROOT / ".env",
        _BACKEND_DIR / ".env",
    ]
    seen: set[Path] = set()
    result: list[Path] = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


@lru_cache
def get_settings() -> AppSettings:
    """缓存配置对象，避免同一进程中重复解析环境变量。"""

    return AppSettings()


def validate_runtime_role_targets(settings: AppSettings | None = None) -> None:
    """启动期校验分角色 Runtime 目标配置。

    - 各职责目标（preview/check）解析后必须是绝对 http(s) 地址（存在性校验）。
    - 计算角色多副本列表中的每个目标都要满足同一约束。
    - 若显式配置了 preview 专属地址，而 check 目标回退到同一地址，输出告警：
      preview 角色实例不开放诊断入口，不应被 Backend 当作 check 目标。
    """

    resolved = settings or get_settings()
    role_targets = {
        "preview": resolved.resolve_runtime_role_base_urls("preview"),
        "check": resolved.resolve_runtime_role_base_urls("check"),
    }
    for role, targets in role_targets.items():
        if not targets:
            raise ValueError(f"Runtime {role} 内部目标地址为空：请配置 RUNTIME_BASE_URL 或对应角色地址。")
        for target in targets:
            if not target.startswith(("http://", "https://")):
                raise ValueError(f"Runtime {role} 内部目标地址必须是绝对 http(s) 地址：{target}")

    explicit_preview = str(resolved.runtime_preview_base_url or "").strip().rstrip("/")
    preview_target = role_targets["preview"][0] if role_targets["preview"] else ""
    if explicit_preview and explicit_preview == preview_target and explicit_preview in role_targets["check"]:
        logging.getLogger(__name__).warning(
            "Runtime check 目标包含 preview 专属地址（%s）。preview 角色不开放诊断入口，"
            "请确认该地址不是 preview-only 实例，或改配 RUNTIME_CHECK_BASE_URL(S)。",
            explicit_preview,
            extra={
                "event": "runtime.role_target.mismatch",
                "role": "check",
                "target": explicit_preview,
            },
        )
