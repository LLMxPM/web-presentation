"""文件功能：仅为专属 Docker MCP 演练库准备两个已批准 Grant，不替代真实 ChatGPT consent。"""

import asyncio
import json
import secrets
from datetime import timedelta
from pathlib import Path

import app.models  # noqa: F401 - 注册完整生产 ORM。
from app.core.config import get_settings
from app.core.oauth_config import resolve_oauth_policy
from app.core.security import hash_password
from app.core.time_utils import utc_now
from app.db.session import get_session_factory, reset_database_state
from app.models.oauth_credential import OAuthAuthorizationCode
from app.models.oauth_grant import OAuthGrant
from app.models.oauth_registration import OAuthClient
from app.models.user import User
from app.models.workspace import Project, Workspace, WorkspaceMember
from app.services.oauth.protocol import credential_digest
from app.services.oauth.service_registry import OAuthServiceRegistry
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from sqlalchemy.engine import make_url

SCOPES = ["page:read", "page:write", "component:read", "component:write", "project:read", "project:write", "preview:run"]


async def seed():
    """数据库名必须有独占测试前缀；凭证仅写入私有忽略目录，不输出原始值。"""
    settings = get_settings()
    assert (make_url(settings.database_url).database or "").startswith("wp_oauth_test_mcp_docker_")
    policy = resolve_oauth_policy(settings)
    factory = get_session_factory()
    secret = Path("/probe-private/service-secret").read_text(encoding="utf-8")
    await OAuthServiceRegistry(factory, policy).create("docker-mcp", "容器 MCP 验收", secret)
    client = "docker-client"
    redirect = "https://client.example.test/callback"
    values = []
    async with factory() as session:
        session.add(OAuthClient(client_id=client, name="容器协议客户端", redirect_uris=[redirect],
            scopes=SCOPES, resource=policy.mcp_resource, auth_method="none"))
        for offset in (1, 2):
            user, workspace = 1000 + offset, 1000 + offset
            password, verifier, code = secrets.token_urlsafe(32), secrets.token_urlsafe(48), secrets.token_urlsafe(32)
            grant = "docker-grant-" + str(offset)
            session.add(User(id=user, username="docker-user-" + str(offset), password_hash=hash_password(password),
                display_name="容器用户" + str(offset), preview_size_presets=[]))
            session.add(Workspace(id=workspace, code="docker-space-" + str(offset), name="容器空间" + str(offset)))
            await session.flush()
            session.add(WorkspaceMember(workspace_id=workspace, user_id=user, role="owner"))
            session.add(Project(id=workspace, workspace_id=workspace, code="docker-project-" + str(offset),
                name="容器项目" + str(offset), theme_config_yaml="{}", created_by=user))
            session.add(OAuthGrant(grant_id=grant, user_id=user, client_id=client, issuer=policy.issuer,
                resource=policy.mcp_resource, workspace_ids=[workspace], scopes=SCOPES))
            await session.flush()
            session.add(OAuthAuthorizationCode(code_hash=credential_digest(code), grant_id=grant, redirect_uri=redirect,
                scopes=SCOPES, code_challenge=create_s256_code_challenge(verifier), code_challenge_method="S256",
                created_at=utc_now(), expires_at=utc_now() + timedelta(seconds=policy.code_ttl_seconds)))
            values.append({"user_id": user, "workspace_id": workspace, "project_id": workspace, "grant_id": grant,
                "password": password, "username": "docker-user-" + str(offset), "code": code,
                "verifier": verifier, "client_id": client, "redirect_uri": redirect})
        await session.commit()
    Path("/probe-private/credentials.json").write_text(json.dumps(values), encoding="utf-8")
    await reset_database_state()
    print("专属演练库与两个预批准 Grant 已准备；未执行 ChatGPT consent。")


if __name__ == "__main__":
    asyncio.run(seed())
