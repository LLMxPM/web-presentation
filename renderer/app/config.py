"""文件功能：独立 Renderer 执行服务配置，不连接业务数据库。"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from uuid import uuid4

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 公开占位密钥，启动与读取时一律拒绝，避免回退到弱 HMAC 密钥。
_PLACEHOLDER_CREDENTIALS = frozenset(
    {
        "",
        "change-me-render-secret",
        "change-me",
        "replace-with-strong-shared-secret",
        "replace-me",
    }
)


class RendererSettings(BaseSettings):
    """Renderer 运行配置；非法静态配置启动失败。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    render_worker_id: str = "renderer-local"
    render_worker_epoch: str = Field(default_factory=lambda: uuid4().hex)
    render_host: str = "0.0.0.0"
    render_port: int = 7400
    render_service_credential: str = ""
    render_service_credential_file: str | None = None
    render_profile_manifest: str | None = None
    render_profile_digest: str = "profile.v1"
    render_cleanup_grace_seconds: float = 5.0
    render_result_ttl_seconds: int = 600
    render_workspace_dir: str = ".tmp/renderer"
    runtime_protocol_version: str = "render-ready.v1"
    result_schema_version: str = "render-result.v1"
    protocol_version: str = "internal/render/v1"
    max_png_bytes: int = 32 * 1024 * 1024
    max_diagnostics_json_bytes: int = 1024 * 1024
    max_component_scenarios: int = 16
    max_canvas_pixels: int = 16_000_000
    max_canvas_edge: int = 8192

    @field_validator("render_cleanup_grace_seconds")
    @classmethod
    def validate_cleanup_grace(cls, value: float) -> float:
        """清理宽限必须为正。"""

        if value <= 0:
            raise ValueError("RENDER_CLEANUP_GRACE_SECONDS 必须大于 0。")
        return value

    @field_validator("render_result_ttl_seconds")
    @classmethod
    def validate_result_ttl(cls, value: int) -> int:
        """终态产物保留期必须为正。"""

        if value <= 0:
            raise ValueError("RENDER_RESULT_TTL_SECONDS 必须大于 0。")
        return value

    @model_validator(mode="after")
    def validate_credential_configured(self) -> "RendererSettings":
        """凭证 fail-closed：secret 文件缺失/空文件直接失败；内联密钥拒绝占位与空值。"""

        self._load_credential_secret()
        return self

    def _load_credential_secret(self) -> bytes:
        """读取并校验服务身份密钥；绝不回退到空字节 HMAC 密钥。"""

        if self.render_service_credential_file:
            path = Path(self.render_service_credential_file).expanduser()
            if not path.is_file():
                raise ValueError(
                    "RENDER_SERVICE_CREDENTIAL_FILE 指向的密钥文件不存在，拒绝以空密钥启动。"
                )
            secret = path.read_bytes().strip()
            if not secret:
                raise ValueError(
                    "RENDER_SERVICE_CREDENTIAL_FILE 密钥文件为空，拒绝以空密钥启动。"
                )
            secret_text = secret.decode("utf-8", errors="ignore").strip()
            if secret_text in _PLACEHOLDER_CREDENTIALS:
                raise ValueError(
                    "RENDER_SERVICE_CREDENTIAL_FILE 包含占位密钥，拒绝以弱 HMAC 密钥启动。"
                )
            return secret
        raw = (self.render_service_credential or "").strip()
        if raw in _PLACEHOLDER_CREDENTIALS:
            raise ValueError(
                "RENDER_SERVICE_CREDENTIAL 不得使用占位符或空值，请改用 secret 文件或强随机密钥。"
            )
        return raw.encode("utf-8")

    @property
    def workspace_path(self) -> Path:
        """返回执行临时目录。"""

        path = Path(self.render_workspace_dir).expanduser()
        if not path.is_absolute():
            path = (Path(__file__).resolve().parents[1] / path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def credential_secret(self) -> bytes:
        """读取服务身份密钥；文件优先且 fail-closed，空文件/空内联绝不回退空字节。"""

        return self._load_credential_secret()


@lru_cache
def get_renderer_settings() -> RendererSettings:
    """缓存 Renderer 配置。"""

    return RendererSettings()
