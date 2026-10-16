"""文件功能：验证素材票据声明的单一判定规则，以及预览上下文 Token 携带的显式声明。"""

from __future__ import annotations

from app.services.asset_access_policy import resolve_asset_base_url_auth
from app.services.token_service import TokenService

_PROTECTED_BASE = "https://backend.example/preview/artifacts/rt_1/assets"


def _generate_token(asset_base_url: str) -> str:
    """按给定素材基础地址签发最小预览上下文 Token。"""

    return TokenService.generate_preview_context_token(
        artifact_id="rt_1",
        preview_kind="project",
        scope_type="project",
        workspace_id=1,
        entry_descriptor={"entry_type": "route", "route": "/"},
        asset_base_url=asset_base_url,
        trace_id="req-auth-policy",
        tenant_id="tenant_1",
        expires_in_seconds=60,
    )


def test_resolve_asset_base_url_auth_by_shape() -> None:
    """受保护预览入口声明为需要票据，其余形态（含空值与历史公开入口）都不附票据。"""

    assert resolve_asset_base_url_auth(_PROTECTED_BASE) == "preview_token"
    assert resolve_asset_base_url_auth(f"{_PROTECTED_BASE}/") == "preview_token"
    assert resolve_asset_base_url_auth(f"{_PROTECTED_BASE}?v=2") == "preview_token"
    assert resolve_asset_base_url_auth("http://127.0.0.1:8000/preview/artifacts/rt_1/assets") == "preview_token"

    assert resolve_asset_base_url_auth("https://backend.example/public/assets/1") == "none"
    assert resolve_asset_base_url_auth("https://backend.example/api/workspaces/1/assets") == "none"
    assert resolve_asset_base_url_auth("https://backend.example/preview/artifacts/rt_1/assets-other") == "none"
    assert resolve_asset_base_url_auth("https://assets.example/releases/release_1") == "none"
    assert resolve_asset_base_url_auth("") == "none"
    assert resolve_asset_base_url_auth(None) == "none"


def test_preview_context_token_should_declare_asset_base_url_auth() -> None:
    """签发预览上下文时必须把素材票据类型写进票据，供运行时查表而不是推断。"""

    protected_claims = TokenService.verify_preview_context_token(_generate_token(_PROTECTED_BASE))
    assert protected_claims["asset_base_url"] == _PROTECTED_BASE
    assert protected_claims["asset_base_url_auth"] == "preview_token"

    legacy_claims = TokenService.verify_preview_context_token(
        _generate_token("https://backend.example/public/assets/1")
    )
    assert legacy_claims["asset_base_url_auth"] == "none"
