"""文件功能：管理 RS256 密钥对、JWKS 输出，以及预览与 AI 场景的短期 JWT 签发与校验。"""

import time
from typing import Any

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import jwt

from app.core.config import get_settings


class TokenService:
    """管理 RSA 密钥与其 JWKS 输出，并提供签发 JWS 方法。"""

    _private_key = None
    _public_key = None
    _kid = "default-key-1"

    @classmethod
    def _ensure_keys_loaded(cls):
        if cls._private_key is not None:
            return

        settings = get_settings()
        key_path = settings.page_screenshot_local_root_path / "runtime_rsa_key.pem"
        key_path.parent.mkdir(parents=True, exist_ok=True)

        if key_path.exists():
            with open(key_path, "rb") as f:
                pem_data = f.read()
            cls._private_key = serialization.load_pem_private_key(pem_data, password=None, backend=default_backend())
            cls._public_key = cls._private_key.public_key()
        else:
            cls._private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            cls._public_key = cls._private_key.public_key()
            pem = cls._private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            with open(key_path, "wb") as f:
                f.write(pem)

    @classmethod
    def get_jwks(cls) -> dict:
        """获取标准的 JWKS 响应数据。"""
        cls._ensure_keys_loaded()
        
        numbers = cls._public_key.public_numbers()
        
        def to_base64url(val: int) -> str:
            import base64
            # val.to_bytes gives length based on bit_length
            byte_len = (val.bit_length() + 7) // 8
            b = val.to_bytes(byte_len, byteorder='big')
            return base64.urlsafe_b64encode(b).decode('ascii').rstrip('=')

        return {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": cls._kid,
                    "use": "sig",
                    "alg": "RS256",
                    "n": to_base64url(numbers.n),
                    "e": to_base64url(numbers.e)
                }
            ]
        }

    @classmethod
    def get_public_pem(cls) -> str:
        """返回 JWT 验签所需的 PEM 公钥文本。"""

        cls._ensure_keys_loaded()
        pem_bytes = cls._public_key.public_bytes(
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
        """使用统一 RSA 私钥签发通用短期 JWT。"""

        cls._ensure_keys_loaded()
        now = int(time.time())
        normalized_payload = dict(payload)
        normalized_payload.setdefault("iss", issuer)
        normalized_payload.setdefault("iat", now)
        normalized_payload.setdefault("exp", now + expires_in_seconds)
        if subject is not None:
            normalized_payload.setdefault("sub", subject)

        return jwt.encode(
            normalized_payload,
            cls._private_key,
            algorithm="RS256",
            headers={"kid": cls._kid},
        )

    @classmethod
    def verify_signed_token(
        cls,
        token: str,
        *,
        audience: str | list[str] | None = None,
        verify_exp: bool = True,
    ) -> dict[str, Any]:
        """校验并解析通用短期 JWT。"""

        cls._ensure_keys_loaded()
        decode_kwargs: dict[str, Any] = {
            "algorithms": ["RS256"],
            "options": {"verify_exp": verify_exp},
        }
        if audience is not None:
            decode_kwargs["audience"] = audience
        decoded_payload = jwt.decode(token, cls._public_key, **decode_kwargs)
        return dict(decoded_payload)

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

        cls._ensure_keys_loaded()

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
            cls._private_key,
            algorithm="RS256",
            headers={"kid": cls._kid},
        )

    @classmethod
    def verify_preview_context_token(cls, token: str, *, verify_exp: bool = True) -> dict[str, Any]:
        """校验并解析无状态预览上下文 Token。"""

        cls._ensure_keys_loaded()
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
        expires_in_seconds: int = 900,
    ) -> str:
        """签发 Runtime 内部整包构建命令令牌。"""

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
        return cls.generate_signed_token(
            payload,
            expires_in_seconds=expires_in_seconds,
            subject="runtime-build-job",
        )

    @classmethod
    def verify_runtime_build_command_token(cls, token: str, *, verify_exp: bool = True) -> dict[str, Any]:
        """校验并解析 Runtime 内部整包构建命令令牌。"""

        cls._ensure_keys_loaded()
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

        cls._ensure_keys_loaded()
        return cls.verify_signed_token(
            token,
            audience="runtime-diagnostics",
            verify_exp=verify_exp,
        )

    @classmethod
    def generate_runtime_service_access_token(
        cls,
        *,
        artifact_id: str | None = None,
        expires_in_seconds: int = 3600,
    ) -> str:
        """签发供 Runtime 回源 Backend 内部 artifact 接口使用的短期服务令牌。"""

        settings = get_settings()
        payload: dict[str, Any] = {
            "aud": settings.runtime_service_token_audience,
            "scope": "runtime-artifact-read",
        }
        if artifact_id is not None:
            payload["artifact_id"] = str(artifact_id)
        return cls.generate_signed_token(
            payload,
            expires_in_seconds=expires_in_seconds,
            subject="runtime-service",
        )

    @classmethod
    def verify_runtime_service_access_token(cls, token: str, *, verify_exp: bool = True) -> dict[str, Any]:
        """校验 Runtime 回源 Backend 内部 artifact 接口使用的短期服务令牌。"""

        settings = get_settings()
        cls._ensure_keys_loaded()
        return cls.verify_signed_token(
            token,
            audience=settings.runtime_service_token_audience,
            verify_exp=verify_exp,
        )
