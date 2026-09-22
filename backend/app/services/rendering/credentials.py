"""文件功能：管理 Renderer 服务身份凭证读取与轮换校验，并提供快照敏感字段加密。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import AppSettings, get_settings
from render_contracts.errors import (
    ERROR_CODE_INTERNAL_ERROR,
    ERROR_CODE_SERVICE_UNAVAILABLE,
    RenderError,
    RenderExecutionError,
)
from render_contracts.tokens import issue_worker_credential, verify_worker_credential

_PLACEHOLDER_SECRETS = frozenset({
    "",
    "change-me-render-secret",
    "change-me",
    "replace-with-strong-shared-secret",
    "replace-me",
})


class RenderCredentialService:
    """读取服务访问凭证文件，生成可校验的服务身份 token，并加密快照中的短期凭证。"""

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self._fernet: Fernet | None = None

    def _cipher(self) -> Fernet:
        """返回用于快照敏感字段的 Fernet；密钥来自应用级加密密钥。"""

        if self._fernet is None:
            key = (self.settings.ai_secret_encryption_key or "").strip()
            if not key:
                raise RenderExecutionError(
                    RenderError.from_code(
                        ERROR_CODE_INTERNAL_ERROR,
                        message="缺少应用级加密密钥，无法保护渲染快照凭证。",
                        stage="configuration",
                    )
                )
            try:
                self._fernet = Fernet(key.encode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                raise RenderExecutionError(
                    RenderError.from_code(
                        ERROR_CODE_INTERNAL_ERROR,
                        message="应用级加密密钥非法，无法保护渲染快照凭证。",
                        stage="configuration",
                    )
                ) from exc
        return self._fernet

    def encrypt_sensitive_payload(self, payload: dict[str, Any]) -> str:
        """加密快照中的短期凭证字段（preview_token / extra_http_headers）。"""

        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self._cipher().encrypt(raw).decode("utf-8")

    def decrypt_sensitive_payload(self, token: str) -> dict[str, Any]:
        """解密快照敏感凭证字段。"""

        if not token:
            return {}
        try:
            raw = self._cipher().decrypt(token.encode("utf-8"))
        except InvalidToken as exc:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_INTERNAL_ERROR,
                    message="渲染快照凭证解密失败。",
                    stage="configuration",
                )
            ) from exc
        payload = json.loads(raw.decode("utf-8"))
        return payload if isinstance(payload, dict) else {}

    def load_secret(self) -> bytes:
        """读取服务凭证密钥；缺失、空文件或占位符时启动派发即失败（fail-closed）。"""

        configured = self.settings.render_service_credential_file
        if configured:
            path = Path(configured).expanduser()
            if not path.is_file():
                raise RenderExecutionError(
                    RenderError.from_code(
                        ERROR_CODE_SERVICE_UNAVAILABLE,
                        message=f"Renderer 服务凭证文件不存在：{path}",
                        stage="configuration",
                    )
                )
            secret = path.read_bytes().strip()
            if not secret:
                raise RenderExecutionError(
                    RenderError.from_code(
                        ERROR_CODE_SERVICE_UNAVAILABLE,
                        message="Renderer 服务凭证文件为空，拒绝使用空 HMAC 密钥。",
                        stage="configuration",
                    )
                )
            if secret.decode("utf-8", errors="ignore").strip() in _PLACEHOLDER_SECRETS:
                raise RenderExecutionError(
                    RenderError.from_code(
                        ERROR_CODE_SERVICE_UNAVAILABLE,
                        message="Renderer 服务凭证文件包含占位密钥，拒绝使用。",
                        stage="configuration",
                    )
                )
            return secret
        raw = (self.settings.render_service_credential or "").strip()
        if raw in _PLACEHOLDER_SECRETS:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_SERVICE_UNAVAILABLE,
                    message=(
                        "未配置有效的 RENDER_SERVICE_CREDENTIAL 或 RENDER_SERVICE_CREDENTIAL_FILE，"
                        "拒绝使用占位密钥访问 Renderer。"
                    ),
                    stage="configuration",
                )
            )
        return raw.encode("utf-8")

    def issue_service_token(self, *, worker_id: str) -> str:
        """为 Backend→Renderer 调用签发服务身份凭证。"""

        secret = self.load_secret()
        return issue_worker_credential(worker_id=f"backend:{worker_id}", secret=secret, ttl_seconds=3600)

    def verify_renderer_token(self, token: str) -> str | None:
        """校验 Renderer 上报的服务身份 token。"""

        secret = self.load_secret()
        return verify_worker_credential(token, secret)