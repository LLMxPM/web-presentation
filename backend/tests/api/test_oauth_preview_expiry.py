"""文件功能：使用真实委托/预览构建和隔离运行态，验证外部预览期限、Scope 与空间边界。"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.project_route import ProjectRoute
from app.services import preview_service, runtime_artifact_store
from app.services.preview_service import PreviewService
from app.services.redis_runtime_client import create_runtime_state_client
from app.services.signing_identity import SigningKey, SigningKeyring
from app.services.token_service import TokenService
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.fixtures.oauth import POLICY
from tests.fixtures.oauth_mutations import delegate_headers, other_user_access


@pytest.fixture
async def media_client(oauth_mutation_client, monkeypatch):
    """使用独立 memory 运行态和仅存进程的测试签名钥，不连接开发 Redis 或媒体服务。"""
    settings = get_settings().model_copy(
        update={
            "backend_public_base_url": POLICY.issuer,
            "runtime_preview_artifact_ttl_seconds": 60,
        }
    )
    runtime = create_runtime_state_client(redis_url="memory://preview-" + uuid4().hex)
    monkeypatch.setattr(preview_service, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime_artifact_store, "get_settings", lambda: settings)
    monkeypatch.setattr(
        runtime_artifact_store, "get_redis_runtime_client", lambda: runtime
    )
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key = SigningKey(
        kid="preview-test",
        private_key=private,
        public_key=private.public_key(),
        source="test",
    )
    monkeypatch.setattr(
        TokenService, "_keyring", SigningKeyring(signing=key, verification_keys=(key,))
    )
    async with oauth_mutation_client[1]() as session:
        session.add(
            ProjectRoute(
                project_id=1,
                page_id=1,
                route="/",
                order=0,
                route_type="page",
                created_by=1,
            )
        )
        await session.commit()
    yield *oauth_mutation_client, settings, runtime


@pytest.mark.parametrize(
    "path,payload,kind",
    [
        ("/api/v1/pages/1/preview-artifact", None, "page"),
        ("/api/v1/projects/1/preview-artifact", {}, "project"),
    ],
)
@pytest.mark.parametrize("ttl", [60, 7200])
async def test_preview_expiry_matches_signed_deadline_and_cache(
    media_client, path, payload, kind, ttl
):
    """页/项目沿用真实预览构建，响应 exp 与票据相等，不晚于缓存，也不扩大原一小时上限。"""
    client, _, access, _, settings, runtime = media_client
    settings.runtime_preview_artifact_ttl_seconds = ttl
    headers = await delegate_headers(client, access["access_token"])
    before = utc_now()
    response = await client.post(path, json=payload, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert (
        expires_at.tzinfo is not None
        and 0 < (expires_at - before).total_seconds() <= min(ttl, 3600) + 1
    )
    url = urlsplit(body["preview_url"])
    assert url.scheme == "https" and url.netloc == "platform.example.test"
    assert url.path == "/preview/artifacts/" + body["artifact_id"]
    claims = TokenService.verify_preview_context_token(parse_qs(url.query)["token"][0])
    stored = await runtime_artifact_store.RuntimeArtifactStore(runtime).get_expires_at(
        body["artifact_id"]
    )
    assert int(expires_at.timestamp()) == claims["exp"] and expires_at <= stored
    assert (
        body["workspace_id"] == body["project_id"] == 1 and body["preview_kind"] == kind
    )
    assert claims["tenant_id"] == "tenant_1" and claims["aud"] == "runtime-preview"


async def test_preview_permissions_precede_artifact_creation(media_client, monkeypatch):
    """缺 preview:run、错误空间和跨用户请求都在构建前失败，不能创建可转交的签名地址。"""
    client, factory, access, _, _, _ = media_client
    create = AsyncMock(side_effect=AssertionError("越权请求触发了预览构建"))
    monkeypatch.setattr(PreviewService, "create_preview_artifact", create)
    headers = await delegate_headers(
        client, access["access_token"], scopes=["page:read", "project:read"]
    )
    for entity in ("pages", "projects"):
        response = await client.post(
            f"/api/v1/{entity}/1/preview-artifact", json={}, headers=headers
        )
        assert (
            response.status_code == 403
            and response.json()["code"] == "INSUFFICIENT_SCOPE"
        )
    other = await other_user_access(client, factory)
    foreign = {
        **await delegate_headers(client, other["access_token"]),
        "X-Workspace-ID": "2",
    }
    for entity in ("pages", "projects"):
        assert (
            await client.post(
                f"/api/v1/{entity}/1/preview-artifact", json={}, headers=foreign
            )
        ).status_code == 403
    create.assert_not_awaited()


@pytest.mark.parametrize("expired", [False, True])
async def test_missing_preview_deadline_fails_without_guessing(
    media_client, monkeypatch, expired
):
    """写入后元数据丢失或到期时不返回猜测的截止时间或可用预览承诺。"""
    client, _, access, _, _, _ = media_client
    monkeypatch.setattr(
        runtime_artifact_store.RuntimeArtifactStore,
        "get_expires_at",
        AsyncMock(return_value=utc_now() - timedelta(seconds=1) if expired else None),
    )
    result = await client.post(
        "/api/v1/pages/1/preview-artifact",
        headers=await delegate_headers(client, access["access_token"]),
    )
    assert (
        result.status_code == 410
        and result.json()["code"] == "PREVIEW_ARTIFACT_EXPIRED"
    )


async def test_corrupt_preview_deadline_is_rejected(media_client):
    """持久化期限损坏不能退回默认 TTL 或忽略校验。"""
    *_, runtime = media_client
    store = runtime_artifact_store.RuntimeArtifactStore(runtime)
    # 使用存储公开查询，保持现有 key 词汇；损坏数据仅限当前独立运行态。
    runtime.hset(store._meta_key("broken"), {"expires_at": "invalid"})
    with pytest.raises(AppException) as caught:
        await store.get_expires_at("broken")
    assert caught.value.code == "PREVIEW_ARTIFACT_METADATA_INVALID"
