"""文件功能：集中定义应用配置，并从环境变量与 .env 文件读取运行参数。"""

from pathlib import Path
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """应用配置模型，负责约束数据库、鉴权和跨域等关键参数。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "页面管理后台"
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
    default_admin_username: str = "admin"
    default_admin_password: str = "Admin123456"
    default_admin_display_name: str = "平台系统管理员"
    session_cookie_name: str = "wp_user_session"
    session_ttl_hours: int = 24
    session_secure: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"])
    runtime_base_url: str = "http://127.0.0.1:7373"
    runtime_public_base_url: str | None = None
    runtime_shared_secret: str = "change-me"
    runtime_service_token_audience: str = "runtime-backend"
    runtime_request_timeout_seconds: float = 10.0
    backend_public_base_url: str = "http://127.0.0.1:8000"
    ai_enabled: bool = True
    ai_test_mode: str = "disabled"
    ai_secret_encryption_key: str = "vmgRweOsDpMtYVW7SSpceINYcXlUHFNndAby6vRv0iA="
    ai_agent_os_id: str = "backend-agentos"
    ai_agent_token_ttl_seconds: int = 600
    ai_tool_auth_window_seconds: int = 1800
    ai_tool_auth_max_seconds: int = 7200
    ai_db_url: str | None = None
    ai_db_schema: str = "agno"
    ai_session_table: str = "agno_sessions"
    ai_approvals_table: str = "agno_approvals"
    ai_session_retention_days: int = 15
    ai_session_cleanup_interval_seconds: int = 21600
    ai_session_cleanup_batch_size: int = 500
    ai_image_transport_mode: str = "auto"
    ai_image_attachment_max_bytes: int = 10 * 1024 * 1024
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_key_prefix: str = "web_presentation"
    redis_healthcheck_timeout_seconds: float = 2.0
    runtime_preview_artifact_ttl_seconds: int = 3600
    runtime_build_state_ttl_seconds: int = 604800
    page_screenshot_default_viewport_width: int = 1920
    page_screenshot_default_viewport_height: int = 1080
    page_screenshot_max_viewport_width: int = 4096
    page_screenshot_max_viewport_height: int = 4096
    page_screenshot_timeout_seconds: float = 45.0
    page_screenshot_visual_ready_timeout_seconds: float = 25.0
    page_screenshot_batch_concurrency: int = 2
    page_screenshot_queue_concurrency: int = 1
    page_screenshot_queue_poll_interval_seconds: float = 1.0
    page_screenshot_job_lease_seconds: int = 180
    page_screenshot_ai_wait_timeout_seconds: float = 90.0
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
        "page_screenshot_batch_concurrency",
        "page_screenshot_queue_concurrency",
        "page_screenshot_job_lease_seconds",
    )
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        """校验截图相关整数配置均为正数。"""

        if value <= 0:
            raise ValueError("截图尺寸配置必须为正整数。")
        return value

    @field_validator(
        "page_screenshot_timeout_seconds",
        "page_screenshot_visual_ready_timeout_seconds",
        "page_screenshot_queue_poll_interval_seconds",
        "page_screenshot_ai_wait_timeout_seconds",
    )
    @classmethod
    def validate_positive_timeout(cls, value: float) -> float:
        """校验截图超时时间有效。"""

        if value <= 0:
            raise ValueError("截图超时时间配置必须大于 0。")
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

    @field_validator("ai_tool_auth_max_seconds")
    @classmethod
    def validate_ai_tool_auth_max_seconds(cls, value: int) -> int:
        """校验工具授权绝对上限不短于滑动窗口默认值。"""

        if value < 1800:
            raise ValueError("AI 工具授权绝对上限不能小于默认滑动窗口 1800 秒。")
        return value

    @field_validator("ai_session_retention_days", "ai_session_cleanup_batch_size")
    @classmethod
    def validate_ai_session_positive_int(cls, value: int) -> int:
        """校验 AI 会话清理保留天数与批大小为正整数。"""

        if value <= 0:
            raise ValueError("AI 会话清理配置必须大于 0。")
        return value

    @field_validator("ai_session_cleanup_interval_seconds")
    @classmethod
    def validate_ai_session_cleanup_interval_seconds(cls, value: int) -> int:
        """校验 AI 会话清理间隔，允许 0 表示关闭后台清理。"""

        if value < 0:
            raise ValueError("AI 会话清理间隔不能小于 0。")
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
    )
    @classmethod
    def validate_positive_runtime_state_int(cls, value: int) -> int:
        """校验 Redis 临时运行态 TTL 配置为正整数。"""

        if value <= 0:
            raise ValueError("Redis 临时运行态配置必须为正整数。")
        return value

    @property
    def page_screenshot_local_root_path(self) -> Path:
        """返回截图本地存储根目录的绝对路径。"""

        configured_path = Path(self.page_screenshot_local_root).expanduser()
        if configured_path.is_absolute():
            return configured_path
        return (Path(__file__).resolve().parents[2] / configured_path).resolve()


@lru_cache
def get_settings() -> AppSettings:
    """缓存配置对象，避免同一进程中重复解析环境变量。"""

    return AppSettings()
