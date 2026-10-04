"""文件功能：用真实平台 Cookie 和隔离数据库装配 OAuth HTTP/确认测试，不启动开发服务。"""

from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import urlencode

import httpx
import pytest
from app.api import dependencies_external, oauth_http
from app.api.routes import oauth_account, oauth_public
from app.api.routes.external import (
    components,
    mutations,
    pages,
    preview,
    system,
    workspaces,
)
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.security import hash_session_token
from app.core.time_utils import utc_now
from app.db.session import get_db_session
from app.models.user import UserSession
from app.services.oauth import consent_service
from app.services.oauth.chatgpt_client import (
    CHATGPT_CLIENT_ID,
    CHATGPT_REDIRECT_URI,
    validate_chatgpt_metadata,
)
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from tests.fixtures.oauth import POLICY, VERIFIER


def consent_query(**changes) -> str:
    """保持真实 ChatGPT 客户端、resource 与 S256 绑定，允许负例覆盖。"""
    return urlencode({
        "client_id": CHATGPT_CLIENT_ID, "redirect_uri": CHATGPT_REDIRECT_URI,
        "response_type": "code", "resource": POLICY.mcp_resource,
        "scope": "page:read page:write", "state": "test-state",
        "code_challenge": create_s256_code_challenge(VERIFIER), "code_challenge_method": "S256",
        **changes,
    })


@pytest.fixture
async def oauth_http_client(oauth_database, monkeypatch):
    """只替换网络元数据，不绕过真实 Cookie、Authlib、ORM、一次性消费和提交。"""
    factory = oauth_database
    settings = SimpleNamespace(
        oauth_enabled=True, oauth_issuer=POLICY.issuer, oauth_mcp_resource=POLICY.mcp_resource,
        oauth_api_audience=POLICY.api_audience, oauth_editor_origin=POLICY.issuer,
        session_secure=True, cors_origins=[],
    )

    async def metadata(client_id, policy):
        """注入固定 OpenAI 文档；仍然通过生产验证函数验证精确身份和回调。"""
        return validate_chatgpt_metadata({
            "client_id": client_id, "redirect_uris": [CHATGPT_REDIRECT_URI],
            "token_endpoint_auth_methods_supported": ["none", "private_key_jwt"],
            "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        }, policy)

    monkeypatch.setattr(consent_service, "fetch_chatgpt_client", metadata)
    for module in (oauth_http, oauth_account, oauth_public, dependencies_external):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    for module in (oauth_account, oauth_public):
        monkeypatch.setattr(module, "get_session_factory", lambda: factory)
    async with factory() as session:
        session.add(UserSession(
            id=1, user_id=1, token_hash=hash_session_token("consent-cookie"),
            expires_at=utc_now() + timedelta(hours=24), last_active_at=utc_now(), is_active=True,
        ))
        await session.commit()

    async def session_dependency():
        """为真实 Cookie 依赖提供相同隔离数据库，每请求单独 Session。"""
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(oauth_public.router)
    app.include_router(oauth_account.router, prefix="/api")
    app.include_router(system.router, prefix="/api/v1")
    app.include_router(workspaces.router, prefix="/api/v1/workspaces")
    app.include_router(pages.router, prefix="/api/v1")
    app.include_router(components.router, prefix="/api/v1/components")
    app.include_router(mutations.router, prefix="/api/v1/jobs/mutations")
    app.include_router(preview.router, prefix="/api/v1")
    app.dependency_overrides[get_db_session] = session_dependency

    @app.exception_handler(AppException)
    async def app_error(_: Request, error: AppException):
        """保留应用错误状态和协议头，无测试特有放行逻辑。"""
        return JSONResponse({"code": error.code, "detail": error.detail}, status_code=error.status_code, headers=error.headers)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=POLICY.issuer) as client:
        client.cookies.set(get_settings().session_cookie_name, "consent-cookie")
        client.headers["Origin"] = POLICY.issuer
        yield client, factory, settings
