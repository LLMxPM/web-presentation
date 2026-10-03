"""文件功能：提供 OAuth 独立 SQLite/PG 数据库、固定协议边界及请求测试夹具。"""

import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import app.models  # noqa: F401
import pytest
from app.core.time_utils import utc_now
from app.db.base import Base
from app.models.oauth_credential import OAuthAuthorizationCode
from app.models.oauth_grant import OAuthGrant
from app.models.oauth_registration import OAuthClient
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services.oauth.policy import OAuthPolicy
from app.services.oauth.protocol import credential_digest
from app.services.oauth.request import ProtocolRequest
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

POLICY = OAuthPolicy(
    "https://platform.example.test",
    "https://mcp.example.test/mcp",
    "https://platform.example.test/api/v1",
)
VERIFIER = "a" * 48
REDIRECT = "https://client.example.test/callback"
SCOPES = ["page:read", "page:write"]
TABLES = [
    table
    for name, table in Base.metadata.tables.items()
    if name.startswith(("oauth_", "api_access_token"))
    or name in {"users", "user_sessions", "workspaces", "workspace_members"}
]


@pytest.fixture(params=["sqlite", "postgresql"])
async def oauth_database(request: pytest.FixtureRequest, tmp_path: Path):
    """每例创建独立数据库或专属 PG schema；连接串只接受明确的测试数据库名。"""
    admin_engine = None
    schema = "wp_oauth_probe_" + uuid4().hex
    if request.param == "postgresql":
        url = os.environ.get("OAUTH_TEST_POSTGRES_DATABASE_URL", "")
        if not url:
            if os.environ.get("OAUTH_TEST_POSTGRES_REQUIRED") == "1":
                pytest.fail("OAuth PG 门禁必须配置 OAUTH_TEST_POSTGRES_DATABASE_URL")
            pytest.skip("未配置专用 OAuth PostgreSQL 测试数据库")
        parsed = make_url(url)
        assert parsed.drivername == "postgresql+asyncpg"
        assert (parsed.database or "").startswith("wp_oauth_test_")
        admin_engine = create_async_engine(url)
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            url, connect_args={"server_settings": {"search_path": schema}}
        )
    else:
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{(tmp_path / 'oauth.db').as_posix()}"
        )

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _) -> None:
            """让 SQLite 也真实验证凭证链外键约束。"""
            connection.execute("PRAGMA foreign_keys=ON")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=TABLES)
            )
        async with factory() as session:
            session.add(
                User(
                    id=1,
                    username="oauth-user",
                    password_hash="unused",
                    display_name="测试用户",
                    preview_size_presets=[],
                )
            )
            session.add(Workspace(id=1, code="oauth-space", name="授权空间"))
            session.add(
                OAuthClient(
                    client_id="desktop",
                    name="测试客户端",
                    redirect_uris=[REDIRECT],
                    scopes=SCOPES,
                    resource=POLICY.mcp_resource,
                    auth_method="none",
                )
            )
            await session.flush()
            session.add(WorkspaceMember(workspace_id=1, user_id=1))
            session.add(
                OAuthGrant(
                    grant_id="grant-1",
                    user_id=1,
                    client_id="desktop",
                    issuer=POLICY.issuer,
                    resource=POLICY.mcp_resource,
                    workspace_ids=[1],
                    scopes=SCOPES,
                )
            )
            await session.flush()
            session.add(
                OAuthAuthorizationCode(
                    code_hash=credential_digest("original-code"),
                    grant_id="grant-1",
                    redirect_uri=REDIRECT,
                    scopes=SCOPES,
                    code_challenge=create_s256_code_challenge(VERIFIER),
                    code_challenge_method="S256",
                    created_at=utc_now(),
                    expires_at=utc_now() + timedelta(seconds=POLICY.code_ttl_seconds),
                )
            )
            await session.commit()
        yield factory
    finally:
        await engine.dispose()
        if admin_engine is not None:
            async with admin_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin_engine.dispose()


def request_data(**changes) -> dict[str, str]:
    """生成真实表单用例，保持原始客户端、回调、资源及 PKCE 绑定。"""
    return {
        "grant_type": "authorization_code",
        "client_id": "desktop",
        "code": "original-code",
        "redirect_uri": REDIRECT,
        "resource": POLICY.mcp_resource,
        "code_verifier": VERIFIER,
        **changes,
    }


def token_request(data: dict[str, str]) -> ProtocolRequest:
    """内部调用也使用受信 issuer URI，不能从请求 Host 选发行身份。"""
    return ProtocolRequest(
        method="POST", uri=POLICY.issuer + "/oauth/token", pairs=data.items()
    )
