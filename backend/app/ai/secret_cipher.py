"""文件功能：提供大模型 API Key 的对称加密与脱敏能力。"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.exceptions import AppException


class LlmSecretCipher:
    """使用 Fernet 对用户模型 API Key 做加密与解密。"""

    def __init__(self) -> None:
        self._fernet = Fernet(get_settings().ai_secret_encryption_key.encode("utf-8"))

    def encrypt(self, value: str | None) -> str | None:
        """加密明文 API Key；空值直接返回。"""

        normalized = str(value or "").strip()
        if not normalized:
            return None
        return self._fernet.encrypt(normalized.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str | None) -> str | None:
        """解密密文 API Key；若密文无效则抛出业务异常。"""

        if not value:
            return None
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise AppException(status_code=500, code="AI_LLM_API_KEY_INVALID", detail="大模型密钥解密失败。") from exc

    @staticmethod
    def mask(value: str | None) -> str | None:
        """返回仅供界面显示的脱敏 API Key。"""

        normalized = str(value or "").strip()
        if not normalized:
            return None
        if len(normalized) <= 8:
            return "*" * len(normalized)
        return f"{normalized[:4]}{'*' * max(4, len(normalized) - 8)}{normalized[-4:]}"
