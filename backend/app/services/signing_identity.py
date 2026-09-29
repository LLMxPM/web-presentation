"""文件功能：解析 Runtime RS256 签名身份（当前私钥、轮换期旧钥与 JWKS），并校验多 Backend 共享密钥前提。"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.fernet import Fernet

from app.core.config import AppSettings, get_settings
from app.db.profile import resolve_deployment_profile

logger = logging.getLogger(__name__)

# 旧版本地密钥文件名：单实例/Lite 可继续读取或自动生成；多 Backend 不得依赖该默认路径。
LEGACY_KEY_FILENAME = "runtime_rsa_key.pem"

# 代码内置默认加密密钥：多 Backend 下必须替换为实例间一致的自定义密钥。
_DEFAULT_AI_SECRET_ENCRYPTION_KEYS = frozenset({
    "",
    "vmgRweOsDpMtYVW7SSpceINYcXlUHFNndAby6vRv0iA=",
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
})

_REJECTED_RENDER_SECRET_PLACEHOLDERS = frozenset({
    "",
    "change-me-render-secret",
    "change-me",
    "replace-with-strong-shared-secret",
    "replace-me",
})

# 单实例/Lite 也禁止直接采用的示例弱口令与占位构建凭证（P1-Secrets）。
_REJECTED_ADMIN_PASSWORD_PLACEHOLDERS = frozenset({
    "change-admin-password",
    "admin",
    "password",
    "123456",
    "replace-me",
})
_REJECTED_BUILD_CREDENTIAL_PLACEHOLDERS = frozenset({
    "change-build-worker-credential",
    "change-me",
    "replace-me",
    "replace-with-strong-shared-secret",
})


class SigningIdentityError(RuntimeError):
    """签名身份配置缺失、无法解析或不满足多 Backend 共享前提时抛出。"""


@dataclass(frozen=True)
class SigningKey:
    """单个 RS256 密钥：kid 用于 JWKS 与 JWT 头匹配，source 仅用于排障日志。"""

    kid: str
    private_key: RSAPrivateKey | None
    public_key: RSAPublicKey
    source: str


@dataclass(frozen=True)
class SigningKeyring:
    """签名密钥环：签名只用当前密钥，验签覆盖轮换期保留的旧钥。"""

    signing: SigningKey
    verification_keys: tuple[SigningKey, ...]

    def verification_keys_for(self, kid: str | None) -> tuple[SigningKey, ...]:
        """按 JWT 头 kid 选择验签密钥；未知 kid 时回退到全部可用密钥。"""

        if kid:
            matched = tuple(key for key in self.verification_keys if key.kid == kid)
            if matched:
                return matched
        return self.verification_keys

    def jwks(self) -> dict[str, Any]:
        """输出含当前钥与轮换期旧钥的 JWKS，供 Runtime 验签旧票据。"""

        return {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": key.kid,
                    "use": "sig",
                    "alg": "RS256",
                    "n": _to_base64url(key.public_key.public_numbers().n),
                    "e": _to_base64url(key.public_key.public_numbers().e),
                }
                for key in self.verification_keys
            ]
        }


def _to_base64url(value: int) -> str:
    """把 RSA 大整数编码为 JWKS 使用的无填充 base64url。"""

    byte_len = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(byte_len, byteorder="big")).decode("ascii").rstrip("=")


def requires_shared_identity(settings: AppSettings) -> bool:
    """判断当前部署是否按多 Backend 副本约束（显式声明或多进程 worker）。"""

    return resolve_deployment_profile(settings).multi_process_requested


def _load_private_key_from_pem(pem_data: bytes, *, source: str) -> RSAPrivateKey:
    """解析 PEM 私钥；格式非法时抛出签名身份错误。"""

    try:
        loaded = serialization.load_pem_private_key(pem_data, password=None, backend=default_backend())
    except Exception as exc:  # noqa: BLE001 - cryptography 抛出多种解析异常
        raise SigningIdentityError(f"签名私钥无法解析（{source}）：{exc}") from exc
    if not isinstance(loaded, RSAPrivateKey):
        raise SigningIdentityError(f"签名私钥必须是 RSA 私钥（{source}）。")
    return loaded


def _load_public_key_from_pem(pem_data: bytes, *, source: str) -> RSAPublicKey:
    """解析 PEM 公钥或从私钥提取公钥，供轮换期验签使用。"""

    try:
        loaded_private = serialization.load_pem_private_key(pem_data, password=None, backend=default_backend())
        return loaded_private.public_key()
    except Exception:  # noqa: BLE001 - 不是私钥时再按公钥解析
        pass
    try:
        loaded_public = serialization.load_pem_public_key(pem_data, backend=default_backend())
    except Exception as exc:  # noqa: BLE001
        raise SigningIdentityError(f"轮换期旧钥无法解析（{source}）：{exc}") from exc
    if not isinstance(loaded_public, RSAPublicKey):
        raise SigningIdentityError(f"轮换期旧钥必须是 RSA 密钥（{source}）。")
    return loaded_public


def _build_signing_key(kid: str, private_key: RSAPrivateKey, *, source: str) -> SigningKey:
    """由私钥构建签名密钥条目。"""

    return SigningKey(
        kid=kid,
        private_key=private_key,
        public_key=private_key.public_key(),
        source=source,
    )


def _resolve_signing_key(settings: AppSettings) -> SigningKey:
    """解析当前签名私钥。

    读取顺序：环境变量 PEM → 显式文件路径（共享路径/密钥挂载）→ 旧版本地文件 →
    单实例自动生成。多 Backend 模式禁止自动生成，且必须显式配置共享私钥来源，
    避免各副本落到本地默认路径后各自生成不同密钥。
    """

    kid = settings.runtime_rsa_key_id.strip()
    multi = requires_shared_identity(settings)

    inline_pem = (settings.runtime_rsa_private_key or "").strip()
    if inline_pem:
        private_key = _load_private_key_from_pem(inline_pem.encode("utf-8"), source="env")
        return _build_signing_key(kid, private_key, source="env")

    configured_file = (settings.runtime_rsa_private_key_file or "").strip()
    if configured_file:
        path = Path(configured_file).expanduser()
        if not path.is_file():
            raise SigningIdentityError(f"签名私钥文件不存在：{path}")
        private_key = _load_private_key_from_pem(path.read_bytes(), source=str(path))
        return _build_signing_key(kid, private_key, source="file")

    if multi:
        raise SigningIdentityError(
            "多 Backend 部署必须通过 RUNTIME_RSA_PRIVATE_KEY 或 RUNTIME_RSA_PRIVATE_KEY_FILE "
            "提供实例间共享的签名私钥（共享路径/密钥挂载），禁止各副本自动生成。"
        )

    legacy_path = settings.page_screenshot_local_root_path / LEGACY_KEY_FILENAME
    if legacy_path.is_file():
        private_key = _load_private_key_from_pem(legacy_path.read_bytes(), source=str(legacy_path))
        return _build_signing_key(kid, private_key, source="legacy-file")

    if not settings.runtime_rsa_allow_auto_generate:
        raise SigningIdentityError(
            "未配置签名私钥来源，且已禁止自动生成（RUNTIME_RSA_ALLOW_AUTO_GENERATE=false）："
            "请提供 RUNTIME_RSA_PRIVATE_KEY 或 RUNTIME_RSA_PRIVATE_KEY_FILE。"
        )

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    legacy_path.write_bytes(pem)
    logger.warning(
        "已自动生成单实例签名私钥（仅限单实例/Lite）：%s",
        legacy_path,
        extra={"event": "signing_identity.key.generated", "source": str(legacy_path)},
    )
    return _build_signing_key(kid, private_key, source="generated")


def _load_previous_keys(settings: AppSettings) -> list[SigningKey]:
    """解析轮换期保留的旧钥列表，仅用于验签与 JWKS 公布。"""

    result: list[SigningKey] = []
    seen_kids: set[str] = set()
    for index, item in enumerate(settings.runtime_rsa_previous_keys):
        if not isinstance(item, dict):
            raise SigningIdentityError(f"RUNTIME_RSA_PREVIOUS_KEYS 第 {index + 1} 项必须是对象。")
        raw_file = str(item.get("private_key_file") or item.get("public_key_file") or "").strip()
        raw_inline = str(item.get("private_key") or item.get("public_key") or "").strip()
        if raw_file and raw_inline:
            raise SigningIdentityError(f"RUNTIME_RSA_PREVIOUS_KEYS 第 {index + 1} 项只能提供文件或内联 PEM 之一。")

        if raw_file:
            path = Path(raw_file).expanduser()
            if not path.is_file():
                raise SigningIdentityError(f"轮换期旧钥文件不存在：{path}")
            pem_data = path.read_bytes()
            source = str(path)
            default_kid = path.stem
        elif raw_inline:
            pem_data = raw_inline.encode("utf-8")
            source = f"previous_keys[{index}]"
            default_kid = ""
        else:
            raise SigningIdentityError(f"RUNTIME_RSA_PREVIOUS_KEYS 第 {index + 1} 项缺少密钥内容。")

        kid = str(item.get("kid") or default_kid or "").strip()
        if not kid:
            raise SigningIdentityError(f"RUNTIME_RSA_PREVIOUS_KEYS 第 {index + 1} 项缺少 kid。")
        if kid in seen_kids:
            raise SigningIdentityError(f"RUNTIME_RSA_PREVIOUS_KEYS 中 kid 重复：{kid}")
        seen_kids.add(kid)

        public_key = _load_public_key_from_pem(pem_data, source=source)
        result.append(SigningKey(kid=kid, private_key=None, public_key=public_key, source=source))
    return result


def load_signing_keyring(settings: AppSettings | None = None) -> SigningKeyring:
    """加载签名密钥环：当前签名钥 + 轮换期旧钥；不缓存，由调用方决定进程内缓存。"""

    resolved = settings or get_settings()
    signing = _resolve_signing_key(resolved)
    previous = _load_previous_keys(resolved)
    for old in previous:
        if old.kid == signing.kid:
            raise SigningIdentityError(
                f"轮换期旧钥 kid 与当前签名 kid 冲突：{signing.kid}；请先为新钥分配新 kid。"
            )
    verification_keys = (signing, *previous)
    return SigningKeyring(signing=signing, verification_keys=verification_keys)


def _ensure_shared_secret_material(settings: AppSettings) -> None:
    """多 Backend 下要求 AI 凭证加密密钥与 Renderer 服务凭证为显式共享值。"""

    ai_key = (settings.ai_secret_encryption_key or "").strip()
    if ai_key in _DEFAULT_AI_SECRET_ENCRYPTION_KEYS:
        raise SigningIdentityError(
            "多 Backend 部署必须配置实例间一致的 AI_SECRET_ENCRYPTION_KEY（禁止默认/占位值）。"
        )
    try:
        Fernet(ai_key.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - Fernet 对非法密钥抛出多种异常
        raise SigningIdentityError(
            "AI_SECRET_ENCRYPTION_KEY 不是合法 Fernet 密钥；多 Backend 必须使用同一把可解密密钥。"
        ) from exc

    credential_file = (settings.render_service_credential_file or "").strip()
    if credential_file:
        path = Path(credential_file).expanduser()
        if not path.is_file():
            raise SigningIdentityError(f"Renderer 服务凭证文件不存在：{path}")
        secret = path.read_bytes().strip().decode("utf-8", errors="ignore").strip()
    else:
        secret = (settings.render_service_credential or "").strip()
    if secret in _REJECTED_RENDER_SECRET_PLACEHOLDERS:
        raise SigningIdentityError(
            "多 Backend 部署必须配置实例间一致的 RENDER_SERVICE_CREDENTIAL(_FILE)，禁止占位密钥。"
        )


def _ensure_shared_object_storage(settings: AppSettings) -> None:
    """多 Backend 下对象产物必须落在共享存储：S3，或经运维确认的共享文件卷。"""

    if settings.asset_storage_driver == "s3":
        return
    if settings.object_storage_shared_volume:
        logger.warning(
            "多 Backend 使用本地对象存储，已按共享文件卷放行；请确保所有副本挂载同一共享卷。",
            extra={"event": "signing_identity.object_storage.shared_volume"},
        )
        return
    raise SigningIdentityError(
        "多 Backend 部署必须使用共享对象存储：请配置 ASSET_STORAGE_DRIVER=s3，"
        "或确认本地目录为共享卷后设置 OBJECT_STORAGE_SHARED_VOLUME=true。"
    )


def _ensure_shared_runtime_state(settings: AppSettings) -> None:
    """多 Backend 下运行态必须是真实 Redis，不得使用进程内 memory://。"""

    scheme = str(settings.redis_url or "").strip().partition("://")[0].strip().lower()
    if scheme == "memory":
        raise SigningIdentityError(
            "多 Backend 部署禁止 memory:// 运行态：请配置真实 redis:// 或 rediss://。"
        )


def validate_shared_identity_deployment(settings: AppSettings | None = None) -> None:
    """启动期校验签名身份与共享密钥/对象存储前提，由应用生命周期调用。

    - 单实例：仅要求签名密钥可加载（含合法自动生成回退）。
    - 多 Backend：强制显式共享签名私钥，且 AI 凭证加密密钥、Renderer 服务凭证、
      对象存储与运行态均满足实例间一致前提。
    """

    resolved = settings or get_settings()
    keyring = load_signing_keyring(resolved)
    multi = requires_shared_identity(resolved)
    logger.info(
        "签名身份已加载。",
        extra={
            "event": "signing_identity.validated",
            "multi_instance": multi,
            "signing_kid": keyring.signing.kid,
            "signing_key_source": keyring.signing.source,
            "verification_key_count": len(keyring.verification_keys),
        },
    )
    # 单实例/Lite 也拒绝文档示例弱密钥，避免照抄 compose 模板直接上线。
    _ensure_no_placeholder_secrets(resolved)
    if not multi:
        return
    _ensure_shared_secret_material(resolved)
    _ensure_shared_object_storage(resolved)
    _ensure_shared_runtime_state(resolved)


def _ensure_no_placeholder_secrets(settings: AppSettings) -> None:
    """所有部署形态拒绝示例占位密钥；测试请使用真实随机值。"""

    ai_key = (settings.ai_secret_encryption_key or "").strip()
    if ai_key in _DEFAULT_AI_SECRET_ENCRYPTION_KEYS:
        raise SigningIdentityError(
            "AI_SECRET_ENCRYPTION_KEY 禁止使用默认/示例占位值；请生成新的 Fernet 密钥并长期保存。"
        )
    try:
        Fernet(ai_key.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - Fernet 对非法密钥抛出多种异常
        raise SigningIdentityError(
            "AI_SECRET_ENCRYPTION_KEY 不是合法 Fernet 密钥；请生成 32 字节随机值的 URL-safe base64。"
        ) from exc
    admin_password = (settings.default_admin_password or "").strip()
    if admin_password in _REJECTED_ADMIN_PASSWORD_PLACEHOLDERS:
        raise SigningIdentityError(
            "DEFAULT_ADMIN_PASSWORD 禁止使用示例弱口令；请在部署前替换为强随机口令。"
        )
    build_credential = (settings.runtime_build_worker_credential or "").strip()
    if build_credential and build_credential in _REJECTED_BUILD_CREDENTIAL_PLACEHOLDERS:
        raise SigningIdentityError(
            "RUNTIME_BUILD_WORKER_CREDENTIAL 禁止使用示例占位值；请生成强随机共享凭证。"
        )
    render_secret = (settings.render_service_credential or "").strip()
    if render_secret and render_secret in _REJECTED_RENDER_SECRET_PLACEHOLDERS:
        raise SigningIdentityError(
            "RENDER_SERVICE_CREDENTIAL 禁止使用示例占位值；请生成强随机共享凭证。"
        )


__all__ = [
    "LEGACY_KEY_FILENAME",
    "SigningIdentityError",
    "SigningKey",
    "SigningKeyring",
    "load_signing_keyring",
    "requires_shared_identity",
    "validate_shared_identity_deployment",
]
