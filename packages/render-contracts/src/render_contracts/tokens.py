"""文件功能：定义渲染接入票据、预览访问凭证与请求摘要计算。"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from urllib.parse import urlparse

from render_contracts.constants import ADMISSION_TICKET_VERSION, WORKER_CREDENTIAL_PURPOSE

_HASH_SEPARATOR: Final[str] = "\x1f"
# extra_http_headers 中禁止覆盖的逐跳/凭据头（大小写不敏感）。
_FORBIDDEN_PREVIEW_HEADERS: Final[frozenset[str]] = frozenset({"authorization", "cookie", "host"})
# 云元数据与常见内部元数据主机名，导航/资源基址一律拒绝。
_BLOCKED_URL_HOSTS: Final[frozenset[str]] = frozenset(
    {
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.goog",
        "metadata",
        "fd00:ec2::254",
        "instance-data",
    }
)


def canonical_json(payload: Any) -> str:
    """生成稳定 JSON 字符串，用于摘要与签名。"""

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(value: str | bytes) -> str:
    """计算 UTF-8 字符串或字节的 SHA-256 十六进制摘要。"""

    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def compute_request_digest(
    *,
    owner_key: str,
    business_stage: str,
    operation: str,
    input_digest: str,
    render_digest: str,
) -> str:
    """计算规范化语义输入摘要，不包含短期凭证。"""

    parts = [owner_key, business_stage, operation, input_digest, render_digest]
    return sha256_hex(_HASH_SEPARATOR.join(parts))


def compute_render_digest(
    *,
    render_profile_digest: str,
    viewport: dict[str, Any],
    operation_options: dict[str, Any],
) -> str:
    """计算渲染环境摘要，包含 profile、视口与操作参数。"""

    payload = {
        "render_profile_digest": render_profile_digest,
        "viewport": viewport,
        "operation_options": operation_options,
    }
    return sha256_hex(canonical_json(payload))


def compute_request_key(
    *,
    owner_key: str,
    business_stage: str,
    operation: str,
    input_digest: str,
    render_digest: str,
) -> str:
    """计算请求幂等唯一键。"""

    return compute_request_digest(
        owner_key=owner_key,
        business_stage=business_stage,
        operation=operation,
        input_digest=input_digest,
        render_digest=render_digest,
    )


def _validate_http_url(url: str, field_name: str) -> None:
    """仅允许 http/https 普通 URL，拒绝空 scheme、file:// 与链路本地地址。"""

    from render_contracts.errors import RenderContractError

    raw = (url or "").strip()
    if not raw:
        raise RenderContractError(f"{field_name} 不能为空。")
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise RenderContractError(f"{field_name} 仅允许 http/https URL。")
    host = parsed.hostname or ""
    if not host:
        raise RenderContractError(f"{field_name} 缺少主机名。")
    lowered_host = host.lower().strip("[]")
    if lowered_host in _BLOCKED_URL_HOSTS or lowered_host.startswith("169.254."):
        raise RenderContractError(f"{field_name} 禁止指向元数据/链路本地地址。")
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is not None and addr.is_link_local:
        raise RenderContractError(f"{field_name} 禁止指向链路本地地址。")


@dataclass(slots=True, frozen=True)
class PreviewAccess:
    """只用于特定 artifact 的短期读取授权。"""

    navigation_base_url: str
    preview_token: str
    artifact_id: str
    expires_at: str
    runtime_protocol_version: str
    asset_base_url: str | None = None
    platform_asset_base_url: str | None = None
    extra_http_headers: dict[str, str] | None = None

    def to_dict(self) -> dict[str, object]:
        """序列化预览访问授权。"""

        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "PreviewAccess":
        """从字典解析预览访问授权。"""

        return cls(
            navigation_base_url=str(payload.get("navigation_base_url") or ""),
            preview_token=str(payload.get("preview_token") or ""),
            artifact_id=str(payload.get("artifact_id") or ""),
            expires_at=str(payload.get("expires_at") or ""),
            runtime_protocol_version=str(payload.get("runtime_protocol_version") or ""),
            asset_base_url=(str(payload["asset_base_url"]) if payload.get("asset_base_url") else None),
            platform_asset_base_url=(
                str(payload["platform_asset_base_url"])
                if payload.get("platform_asset_base_url")
                else None
            ),
            extra_http_headers=(
                {str(k): str(v) for k, v in dict(payload["extra_http_headers"]).items()}
                if isinstance(payload.get("extra_http_headers"), dict)
                else None
            ),
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        """判断预览授权是否已过期。"""

        current = now or datetime.now(UTC)
        try:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        except ValueError:
            return True
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return current >= expires

    def validate(self) -> None:
        """校验预览访问 URL 白名单与禁止覆盖的请求头。"""

        from render_contracts.errors import RenderContractError

        _validate_http_url(self.navigation_base_url, "navigation_base_url")
        if self.asset_base_url is not None:
            _validate_http_url(self.asset_base_url, "asset_base_url")
        if self.platform_asset_base_url is not None:
            _validate_http_url(self.platform_asset_base_url, "platform_asset_base_url")
        if self.extra_http_headers:
            for key in self.extra_http_headers:
                if str(key).lower() in _FORBIDDEN_PREVIEW_HEADERS:
                    raise RenderContractError(f"extra_http_headers 禁止携带 {key}。")


@dataclass(slots=True, frozen=True)
class AdmissionTicket:
    """签名绑定请求摘要、attempt、workspace、Worker/epoch 与 slot generation 的接入票据。"""

    version: str
    ticket_id: str
    attempt_id: str
    request_digest: str
    workspace_id: int
    worker_id: str
    worker_epoch: str
    slot_generation: int
    issued_at: str
    accept_before: str
    stop_by: str
    signature: str

    def to_dict(self) -> dict[str, object]:
        """序列化接入票据。"""

        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "AdmissionTicket":
        """从字典解析接入票据。"""

        return cls(
            version=str(payload.get("version") or ADMISSION_TICKET_VERSION),
            ticket_id=str(payload.get("ticket_id") or ""),
            attempt_id=str(payload.get("attempt_id") or ""),
            request_digest=str(payload.get("request_digest") or ""),
            workspace_id=int(payload.get("workspace_id") or 0),
            worker_id=str(payload.get("worker_id") or ""),
            worker_epoch=str(payload.get("worker_epoch") or ""),
            slot_generation=int(payload.get("slot_generation") or 0),
            issued_at=str(payload.get("issued_at") or ""),
            accept_before=str(payload.get("accept_before") or ""),
            stop_by=str(payload.get("stop_by") or ""),
            signature=str(payload.get("signature") or ""),
        )

    def unsigned_payload(self) -> dict[str, Any]:
        """返回参与签名的规范化字段。"""

        return {
            "version": self.version,
            "ticket_id": self.ticket_id,
            "attempt_id": self.attempt_id,
            "request_digest": self.request_digest,
            "workspace_id": self.workspace_id,
            "worker_id": self.worker_id,
            "worker_epoch": self.worker_epoch,
            "slot_generation": self.slot_generation,
            "issued_at": self.issued_at,
            "accept_before": self.accept_before,
            "stop_by": self.stop_by,
        }

    def validate(
        self,
        *,
        request_digest: str | None = None,
        workspace_id: int | None = None,
        attempt_id: str | None = None,
        secret: bytes | None = None,
        now: datetime | None = None,
        worker_id: str | None = None,
        worker_epoch: str | None = None,
        slot_generation: int | None = None,
    ) -> None:
        """校验票据绑定关系、接收期限与停止期限。"""

        from render_contracts.errors import RenderContractError

        if self.version != ADMISSION_TICKET_VERSION:
            raise RenderContractError("接入票据版本不受支持。")
        if request_digest is not None and self.request_digest != request_digest:
            raise RenderContractError("接入票据 request_digest 不匹配。")
        if workspace_id is not None and self.workspace_id != workspace_id:
            raise RenderContractError("接入票据 workspace 不匹配。")
        if attempt_id is not None and self.attempt_id != attempt_id:
            raise RenderContractError("接入票据 attempt_id 不匹配。")
        if not self.ticket_id:
            raise RenderContractError("接入票据缺少 ticket_id。")
        if worker_id is not None and self.worker_id != worker_id:
            raise RenderContractError("接入票据 worker_id 不匹配。")
        if worker_epoch is not None and self.worker_epoch != worker_epoch:
            raise RenderContractError("接入票据 worker_epoch 不匹配。")
        if slot_generation is not None and self.slot_generation != slot_generation:
            if self.slot_generation > slot_generation:
                raise RenderContractError("接入票据 slot generation 未接管/未签发。")
            raise RenderContractError("接入票据 slot generation 过期。")
        current = now or datetime.now(UTC)
        try:
            accept_before = datetime.fromisoformat(self.accept_before.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RenderContractError("接入票据 accept_before 非法。") from exc
        if accept_before.tzinfo is None:
            accept_before = accept_before.replace(tzinfo=UTC)
        if current >= accept_before:
            raise RenderContractError("接入票据已超过接收期限。")
        try:
            stop_by = datetime.fromisoformat(self.stop_by.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RenderContractError("接入票据 stop_by 非法。") from exc
        if stop_by.tzinfo is None:
            stop_by = stop_by.replace(tzinfo=UTC)
        if current >= stop_by:
            raise RenderContractError("接入票据已超过停止期限。")
        if secret is not None:
            expected = sign_payload(self.unsigned_payload(), secret)
            if not hmac.compare_digest(expected, self.signature):
                raise RenderContractError("接入票据签名无效。")

    @classmethod
    def issue(
        cls,
        *,
        secret: bytes,
        request_digest: str,
        workspace_id: int,
        worker_id: str,
        worker_epoch: str,
        slot_generation: int,
        accept_before: datetime,
        stop_by: datetime,
        attempt_id: str,
        ticket_id: str | None = None,
        issued_at: datetime | None = None,
    ) -> "AdmissionTicket":
        """签发并签名接入票据；attempt_id 必须绑定进签名载荷。"""

        from render_contracts.errors import RenderContractError

        if not attempt_id:
            raise RenderContractError("签发接入票据必须提供 attempt_id。")
        issued = issued_at or datetime.now(UTC)
        ticket = cls(
            version=ADMISSION_TICKET_VERSION,
            ticket_id=ticket_id or secrets.token_urlsafe(16),
            attempt_id=attempt_id,
            request_digest=request_digest,
            workspace_id=workspace_id,
            worker_id=worker_id,
            worker_epoch=worker_epoch,
            slot_generation=slot_generation,
            issued_at=_format_utc(issued),
            accept_before=_format_utc(accept_before),
            stop_by=_format_utc(stop_by),
            signature="",
        )
        signature = sign_payload(ticket.unsigned_payload(), secret)
        return cls(**{**ticket.to_dict(), "signature": signature})  # type: ignore[arg-type]


def sign_payload(payload: dict[str, Any], secret: bytes) -> str:
    """使用 HMAC-SHA256 签名规范化 payload。"""

    return hmac.new(secret, canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def _format_utc(value: datetime) -> str:
    """把 datetime 规范化为 UTC ISO 字符串。"""

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def issue_worker_credential(*, worker_id: str, secret: bytes, ttl_seconds: int = 86400) -> str:
    """为 Renderer 服务身份生成可轮换的访问凭证，固定 purpose 为 render-service。"""

    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    payload = {
        "purpose": WORKER_CREDENTIAL_PURPOSE,
        "worker_id": worker_id,
        "issued_at": _format_utc(issued_at),
        "expires_at": _format_utc(expires_at),
        "nonce": secrets.token_urlsafe(12),
    }
    signature = sign_payload(payload, secret)
    return canonical_json({**payload, "signature": signature})


def verify_worker_credential(token: str, secret: bytes) -> str | None:
    """校验 Renderer 服务身份凭证，成功时返回 worker_id。"""

    try:
        payload = json.loads(token)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    signature = str(payload.pop("signature", "") or "")
    expected = sign_payload(payload, secret)
    if not hmac.compare_digest(expected, signature):
        return None
    if payload.get("purpose") != WORKER_CREDENTIAL_PURPOSE:
        return None
    try:
        expires_at = datetime.fromisoformat(str(payload.get("expires_at", "")).replace("Z", "+00:00"))
    except ValueError:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) >= expires_at:
        return None
    return str(payload.get("worker_id") or "") or None
