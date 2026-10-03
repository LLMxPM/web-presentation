"""文件功能：验证真实 Cookie 下的授权批准/拒绝、空间缩权、nonce/session 围栏及并发消费。"""

import asyncio
from urllib.parse import parse_qs, urlsplit

import pytest
from app.core.time_utils import utc_now
from app.models.oauth_credential import OAuthAuthorizationCode
from app.models.oauth_grant import OAuthConsentRequest, OAuthGrant
from app.models.oauth_registration import OAuthClient
from app.models.user import UserSession
from app.models.workspace import WorkspaceMember
from app.services.oauth.chatgpt_client import CHATGPT_CLIENT_ID, CHATGPT_REDIRECT_URI
from app.services.oauth.protocol import credential_digest
from sqlalchemy import func, select, update

from tests.fixtures.oauth import POLICY, VERIFIER
from tests.fixtures.oauth_consent import consent_query

BASE = "/api/v1/account/oauth/consents"


async def begin(client):
    """从真实确认入口取得短期 nonce 和当前空间选项。"""
    response = await client.post(BASE, json={"authorization_query": consent_query()})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    return response.json()


def decision(view, **changes):
    """批准时明确选择一个空间和只读权限，不依赖默认全选。"""
    return {"approved": True, "csrf_token": view["csrf_token"], "workspace_ids": [1], "scopes": ["page:read"], **changes}


async def test_approve_narrows_scope_and_code_can_only_be_exchanged_once(oauth_http_client):
    """批准缩权必须进入 Grant 与 Code，原始 nonce/code 不得出现在持久记录中。"""
    client, factory, _ = oauth_http_client
    view = await begin(client)
    assert view["workspaces"] == [{"id": 1, "name": "授权空间"}]
    confirmed = await client.post(f'{BASE}/{view["request_id"]}/decision', json=decision(view))
    assert confirmed.status_code == 200, confirmed.text
    params = parse_qs(urlsplit(confirmed.json()["redirect_uri"]).query)
    assert params["iss"] == [POLICY.issuer] and params["state"] == ["test-state"]
    async with factory() as session:
        pending = await session.get(OAuthConsentRequest, view["request_id"])
        code = await session.get(OAuthAuthorizationCode, credential_digest(params["code"][0]))
        grant = await session.get(OAuthGrant, code.grant_id)
        assert grant.workspace_ids == [1] and grant.scopes == code.scopes == ["page:read"]
        assert pending.csrf_hash == credential_digest(view["csrf_token"])
        assert pending.consumed_at is not None
    form = {"grant_type": "authorization_code", "client_id": CHATGPT_CLIENT_ID,
            "code": params["code"][0], "redirect_uri": CHATGPT_REDIRECT_URI,
            "resource": POLICY.mcp_resource, "code_verifier": VERIFIER}
    token = await client.post("/oauth/token", data=form)
    assert token.status_code == 200, token.text
    assert token.json()["scope"] == "page:read"
    assert token.headers["cache-control"] == "private, no-store"
    replay = await client.post("/oauth/token", data=form)
    assert replay.json()["error"] == "invalid_grant"


@pytest.mark.parametrize("changes", [
    {"csrf_token": "wrong" * 10}, {"workspace_ids": []}, {"workspace_ids": [999]},
    {"workspace_ids": [1, 1]}, {"scopes": []}, {"scopes": ["asset:write"]},
])
async def test_invalid_decision_does_not_consume_or_issue(oauth_http_client, changes):
    """错误 nonce、无空间、跨空间与权限扩张均失败，正确请求仍可使用。"""
    client, factory, _ = oauth_http_client
    view = await begin(client)
    result = await client.post(f'{BASE}/{view["request_id"]}/decision', json=decision(view, **changes))
    assert result.status_code == 403
    async with factory() as session:
        pending = await session.get(OAuthConsentRequest, view["request_id"])
        assert pending.consumed_at is None
        assert await session.scalar(select(func.count()).select_from(OAuthGrant)) == 1
    correct = await client.post(f'{BASE}/{view["request_id"]}/decision', json=decision(view))
    assert correct.status_code == 200


@pytest.mark.parametrize("change", ["expired", "session", "membership", "client_disabled"])
async def test_confirm_rechecks_live_state(oauth_http_client, change):
    """展示之后的过期、会话注销、成员失效和客户端停用必须再次校验。"""
    client, factory, _ = oauth_http_client
    view = await begin(client)
    async with factory() as session:
        if change == "expired":
            await session.execute(update(OAuthConsentRequest).values(expires_at=utc_now()))
        elif change == "session":
            await session.execute(update(UserSession).values(is_active=False))
        elif change == "membership":
            await session.execute(update(WorkspaceMember).values(status="inactive"))
        else:
            await session.execute(update(OAuthClient).where(OAuthClient.client_id == CHATGPT_CLIENT_ID).values(is_active=False))
        await session.commit()
    result = await client.post(f'{BASE}/{view["request_id"]}/decision', json=decision(view))
    assert result.status_code in {401, 403}
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(OAuthGrant)) == 1


async def test_denial_is_once_only_and_carries_issuer_without_code(oauth_http_client):
    """用户拒绝不创建 Grant，错误回调仍保留原始 state/issuer。"""
    client, factory, _ = oauth_http_client
    view = await begin(client)
    path = f'{BASE}/{view["request_id"]}/decision'
    denied = await client.post(path, json=decision(view, approved=False))
    params = parse_qs(urlsplit(denied.json()["redirect_uri"]).query)
    assert params == {"error": ["access_denied"], "error_description": ["The resource owner or authorization server denied the request"], "state": ["test-state"], "iss": [POLICY.issuer]}
    assert (await client.post(path, json=decision(view))).status_code == 403
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(OAuthGrant)) == 1


async def test_concurrent_confirm_commits_one_grant(oauth_http_client):
    """两个独立事务同时消费同一 nonce，只能创建一次授权和授权码。"""
    client, factory, _ = oauth_http_client
    view = await begin(client)
    results = await asyncio.gather(*[
        client.post(f'{BASE}/{view["request_id"]}/decision', json=decision(view)) for _ in range(2)
    ])
    assert sorted(result.status_code for result in results) == [200, 403]
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(OAuthGrant)) == 2


async def test_new_cookie_session_cannot_confirm_old_session_request(oauth_http_client):
    """同一用户重新登录后的会话不能继承旧确认请求。"""
    from datetime import timedelta

    from app.core.config import get_settings
    from app.core.security import hash_session_token

    client, factory, _ = oauth_http_client
    view = await begin(client)
    async with factory() as session:
        session.add(UserSession(id=2, user_id=1, token_hash=hash_session_token("new-cookie"),
                                expires_at=utc_now() + timedelta(hours=24), last_active_at=utc_now()))
        await session.commit()
    client.cookies.clear()
    client.cookies.set(get_settings().session_cookie_name, "new-cookie")
    result = await client.post(f'{BASE}/{view["request_id"]}/decision', json=decision(view))
    assert result.status_code == 403


async def test_concurrent_first_cimd_registration_preserves_both_requests(oauth_http_client):
    """多个请求第一次遇到同一 ChatGPT ID，唯一注册竞态不能产生半条确认。"""
    client, factory, _ = oauth_http_client
    views = await asyncio.gather(begin(client), begin(client))
    assert views[0]["request_id"] != views[1]["request_id"]
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(OAuthClient).where(OAuthClient.client_id == CHATGPT_CLIENT_ID)) == 1
        assert await session.scalar(select(func.count()).select_from(OAuthConsentRequest)) == 2


async def test_confirm_commit_failure_rolls_back_code_grant_and_consumption(oauth_http_client, monkeypatch):
    """数据库提交失败时不交付含 Code 的回调，整批写入与消费一起回滚。"""
    from sqlalchemy.ext.asyncio import AsyncSession

    client, factory, _ = oauth_http_client
    view = await begin(client)

    async def failed_commit(_):
        """模拟事务最终提交失败，不能把已生成授权码作为成功结果交付。"""
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(AsyncSession, "commit", failed_commit)
    with pytest.raises(RuntimeError, match="simulated commit failure"):
        await client.post(f'{BASE}/{view["request_id"]}/decision', json=decision(view))
    async with factory() as session:
        assert (await session.get(OAuthConsentRequest, view["request_id"])).consumed_at is None
        assert await session.scalar(select(func.count()).select_from(OAuthGrant)) == 1
        assert await session.scalar(select(func.count()).select_from(OAuthAuthorizationCode)) == 1
