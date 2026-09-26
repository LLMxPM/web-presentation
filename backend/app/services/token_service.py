"""文件功能：管理 RS256 密钥环、JWKS 输出，以及预览与 AI 场景的短期 JWT 签发与校验。"""

import time
from typing import Any

from cryptography.hazmat.primitives import serialization
import jwt

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.signing_identity import SigningKeyring, load_signing_keyring


class TokenService:
    """管理 RSA 签名密钥环与其 JWKS 输出，并提供签发 JWS 方法。"""

    _keyring: SigningKeyring | None = None

    @classmethod
    def _ensure_keys_loaded(cls) -> SigningKeyring:
        """加载并缓存进程内签名密钥环；密钥来源与轮换语义见 signing_identity。"""

        if cls._keyring is not None:
            return cls._keyring

        cls._keyring = load_signing_keyring(get_settings())
        return cls._keyring

    @classmethod
    def reset_signing_keyring(cls) -> None:
        """清空进程内签名密钥缓存，供测试与密钥更换后重新加载使用。"""

        cls._keyring = None

    @classmethod
    def get_jwks(cls) -> dict:
        """获取标准的 JWKS 响应数据；轮换期同时公布旧钥公钥。"""

        return cls._ensure_keys_loaded().jwks()

    @classmethod
    def get_public_pem(cls) -> str:
        """返回 JWT 验签所需的 PEM 公钥文本（当前签名钥）。"""

        keyring = cls._ensure_keys_loaded()
        pem_bytes = keyring.signing.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return pem_bytes.decode("utf-8")

    @classmethod
    def generate_signed_token(
        cls,
        payload: dict[str, Any],
        *,
        expires_in_seconds: int,
        issuer: str = "backend",
        subject: str | None = None,
    ) -> str:
        """使用当前 RSA 私钥签发通用短期 JWT。"""

        keyring = cls._ensure_keys_loaded()
        now = int(time.time())
        normalized_payload = dict(payload)
        normalized_payload.setdefault("iss", issuer)
        normalized_payload.setdefault("iat", now)
        normalized_payload.setdefault("exp", now + expires_in_seconds)
        if subject is not None:
            normalized_payload.setdefault("sub", subject)

        return jwt.encode(
            normalized_payload,
            keyring.signing.private_key,
            algorithm="RS256",
            headers={"kid": keyring.signing.kid},
        )

    @classmethod
    def verify_signed_token(
        cls,
        token: str,
        *,
        audience: str | list[str] | None = None,
        verify_exp: bool = True,
    ) -> dict[str, Any]:
        """校验并解析通用短期 JWT；轮换期旧票据按 kid 命中旧钥，在 TTL 内仍有效。"""

        keyring = cls._ensure_keys_loaded()
        decode_kwargs: dict[str, Any] = {
            "algorithms": ["RS256"],
            "options": {"verify_exp": verify_exp},
        }
        if audience is not None:
            decode_kwargs["audience"] = audience

        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise jwt.InvalidTokenError("令牌头无法解析。") from exc
        candidates = keyring.verification_keys_for(header.get("kid"))

        last_error: Exception | None = None
        for candidate in candidates:
            try:
                decoded_payload = jwt.decode(token, candidate.public_key, **decode_kwargs)
                return dict(decoded_payload)
            except jwt.PyJWTError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise jwt.InvalidTokenError("没有可用于验签的签名密钥。")

    @classmethod
    def generate_preview_context_token(
        cls,
        *,
        artifact_id: str,
        preview_kind: str,
        scope_type: str,
        workspace_id: int | str,
        entry_descriptor: dict[str, Any],
        asset_base_url: str,
        trace_id: str,
        tenant_id: str,
        project_id: int | str | None = None,
        component_preview_mode: str | None = None,
        component_source: str | None = None,
        component_code: str | None = None,
        component_version_no: int | None = None,
        runtime_kit_component_name: str | None = None,
        runtime_kit_manifest_version: str | None = None,
        asset_id: int | str | None = None,
        expires_in_seconds: int = 3600,
    ) -> str:
        """签发统一的无状态预览上下文 Token。"""

        keyring = cls._ensure_keys_loaded()

        now = int(time.time())
        payload: dict[str, Any] = {
            "iss": "backend",
            "aud": "runtime-preview",
            "sub": "preview-artifact",
            "tenant_id": str(tenant_id),
            "artifact_id": str(artifact_id),
            "preview_kind": str(preview_kind),
            "scope_type": str(scope_type),
            "workspace_id": str(workspace_id),
            "entry_descriptor": entry_descriptor,
            "asset_base_url": asset_base_url,
            "trace_id": trace_id,
            "iat": now,
            "exp": now + expires_in_seconds,
            "jti": f"preview-artifact-{artifact_id}-{now}",
        }
        if project_id is not None:
            payload["project_id"] = str(project_id)
        if component_preview_mode:
            payload["component_preview_mode"] = str(component_preview_mode)
        if component_source:
            payload["component_source"] = str(component_source)
        if component_code:
            payload["component_code"] = str(component_code)
        if component_version_no is not None:
            payload["component_version_no"] = int(component_version_no)
        if runtime_kit_component_name:
            payload["runtime_kit_component_name"] = str(runtime_kit_component_name)
        if runtime_kit_manifest_version:
            payload["runtime_kit_manifest_version"] = str(runtime_kit_manifest_version)
        if asset_id is not None:
            payload["asset_id"] = str(asset_id)

        return jwt.encode(
            payload,
            keyring.signing.private_key,
            algorithm="RS256",
            headers={"kid": keyring.signing.kid},
        )

    @classmethod
    def verify_preview_context_token(cls, token: str, *, verify_exp: bool = True) -> dict[str, Any]:
        """校验并解析无状态预览上下文 Token。"""

        return cls.verify_signed_token(
            token,
            audience="runtime-preview",
            verify_exp=verify_exp,
        )

    @classmethod
    def generate_runtime_build_command_token(
        cls,
        *,
        job_id: int | str,
        artifact_id: str,
        project_id: int | str,
        workspace_id: int | str,
        base_url: str,
        attempt_id: str | None = None,
        lease_owner: str | None = None,
        expires_in_seconds: int = 900,
    ) -> str:
        """签发 Runtime 内部整包构建命令令牌；attempt 与租约拥有者绑定限权身份。"""

        now = int(time.time())
        payload = {
            "iss": "backend",
            "aud": "runtime-build",
            "sub": "runtime-build-job",
            "job_id": str(job_id),
            "artifact_id": str(artifact_id),
            "project_id": str(project_id),
            "workspace_id": str(workspace_id),
            "base_url": str(base_url),
            "iat": now,
            "exp": now + expires_in_seconds,
            "jti": f"runtime-build-job-{job_id}-{now}",
        }
        if attempt_id:
            payload["attempt_id"] = str(attempt_id)
        if lease_owner:
            payload["lease_owner"] = str(lease_owner)
        return cls.generate_signed_token(
            payload,
            expires_in_seconds=expires_in_seconds,
            subject="runtime-build-job",
        )

    @classmethod
    def verify_runtime_build_command_token(cls, token: str, *, verify_exp: bool = True) -> dict[str, Any]:
        """校验并解析 Runtime 内部整包构建命令令牌。"""

        return cls.verify_signed_token(
            token,
            audience="runtime-build",
            verify_exp=verify_exp,
        )

    @classmethod
    def generate_runtime_diagnostics_command_token(
        cls,
        *,
        artifact_id: str,
        workspace_id: int | str,
        project_id: int | str | None = None,
        expires_in_seconds: int = 900,
    ) -> str:
        """签发 Runtime 内部代码诊断命令令牌。"""

        now = int(time.time())
        payload = {
            "iss": "backend",
            "aud": "runtime-diagnostics",
            "sub": "runtime-diagnostics",
            "artifact_id": str(artifact_id),
            "workspace_id": str(workspace_id),
            "iat": now,
            "exp": now + expires_in_seconds,
            "jti": f"runtime-diagnostics-{artifact_id}-{now}",
        }
        if project_id is not None:
            payload["project_id"] = str(project_id)
        return cls.generate_signed_token(
            payload,
            expires_in_seconds=expires_in_seconds,
            subject="runtime-diagnostics",
        )

    @classmethod
    def verify_runtime_diagnostics_command_token(cls, token: str, *, verify_exp: bool = True) -> dict[str, Any]:
        """校验并解析 Runtime 内部代码诊断命令令牌。"""

        return cls.verify_signed_token(
            token,
            audience="runtime-diagnostics",
            verify_exp=verify_exp,
        )

    @classmethod
    def generate_runtime_service_access_token(
        cls,
        *,
        artifact_id: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        """签发供 Runtime 回源 Backend 内部 artifact 接口使用的短期服务令牌。

        必须绑定 artifact_id：无作用域令牌不得进入 artifact 读取链路，
        否则会抵消 artifact 绑定、对任意 artifact 有效。
        """

        normalized_artifact_id = str(artifact_id or "").strip()
        if not normalized_artifact_id:
            raise AppException(
                status_code=500,
                code="RUNTIME_SERVICE_TOKEN_ARTIFACT_REQUIRED",
                detail="Runtime 服务令牌必须绑定 artifact_id。",
            )
        settings = get_settings()
        payload: dict[str, Any] = {
            "aud": settings.runtime_service_token_audience,
            "scope": "runtime-artifact-read",
            "artifact_id": normalized_artifact_id,
        }
        return cls.generate_signed_token(
            payload,
            expires_in_seconds=expires_in_seconds,
            subject="runtime-service",
        )

    @classmethod
    def generate_runtime_internal_tool_token(cls, *, expires_in_seconds: int = 900) -> str:
        """签发供 Backend 调用 Runtime 轻量内部工具的短期令牌，不绑定 artifact。"""

        settings = get_settings()
        payload: dict[str, Any] = {
            "aud": settings.runtime_service_token_audience,
            "scope": "runtime-internal-tool",
        }
        return cls.generate_signed_token(
            payload,
            expires_in_seconds=expires_in_seconds,
            subject="runtime-service",
        )

    @classmethod
    def verify_runtime_service_access_token(cls, token: str, *, verify_exp: bool = True) -> dict[str, Any]:
        """校验 Runtime 回源 Backend 内部 artifact 接口使用的短期服务令牌。"""

        settings = get_settings()
        return cls.verify_signed_token(
            token,
            audience=settings.runtime_service_token_audience,
            verify_exp=verify_exp,
        )
