"""文件功能：跨两个独立 Python 进程验证 PG 授权码消费、刷新重放和服务停用/交换竞争。"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from app.models.oauth_credential import OAuthToken
from app.models.oauth_grant import OAuthGrant, OAuthRefreshFamily
from app.models.oauth_registration import OAuthMcpService
from app.services.oauth.protocol import credential_digest
from app.services.oauth.resource_service import OAuthResourceService
from app.services.oauth.service_registry import OAuthServiceRegistry
from app.services.oauth.token_service import OAuthTokenService
from sqlalchemy import select, text

from tests.fixtures.oauth import POLICY, request_data, token_request
from tests.fixtures.oauth_resource import exchange_data, service_request


async def race(factory, *actions):
    """只在独立 PG Schema 内运行；就绪屏障不修改锁、事务或 CAS 时序。"""
    if factory.kw['bind'].url.drivername != 'postgresql+asyncpg':
        pytest.skip('跨进程门禁需要明确的专属 PostgreSQL 测试库')
    async with factory() as session:
        schema = await session.scalar(text('SELECT current_schema()'))
    assert schema.startswith('wp_oauth_probe_')
    children = []
    try:
        for action in actions:
            process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'tests.fixtures.oauth_probe_process',
                cwd=Path(__file__).resolve().parents[2], env=dict(os.environ),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            children.append(process)
            process.stdin.write((json.dumps({'schema': schema, **action}) + '\n').encode())
            await process.stdin.drain()
        async with asyncio.timeout(30):
            ready = await asyncio.gather(*(process.stdout.readline() for process in children))
            assert all(value.strip() == b'ready' for value in ready), 'OAuth 独立进程未就绪'
            for process in children:
                process.stdin.write(b'run\n')
                await process.stdin.drain()
            results = await asyncio.gather(*(process.communicate() for process in children))
        assert all(process.returncode == 0 for process in children), 'OAuth 独立进程执行失败；不回显凭证管道'
        outputs = []
        for output, _ in results:
            # 生产审计日志也写 stdout；仅解析本夹具的结果帧，不修改生产日志处理器。
            framed = [line.removeprefix(b'wp-oauth-probe-result ') for line in output.splitlines()
                      if line.startswith(b'wp-oauth-probe-result ')]
            assert len(framed) == 1, 'OAuth 独立进程结果帧缺失或重复'
            outputs.append(json.loads(framed[0]))
        return outputs
    finally:
        for process in children:
            if process.returncode is None:
                process.terminate()
                await asyncio.wait_for(process.wait(), 5)


async def test_authorization_code_has_one_cross_process_winner(oauth_database):
    """相同授权码只能发行一次，不能依赖进程内字典实现一次性消费。"""
    action = {'action': 'token', 'pairs': list(request_data().items())}
    results = await race(oauth_database, action, action)
    assert sorted(result['status'] for result in results) == [200, 400]
    assert next(result for result in results if result['status'] == 400)['body']['error'] == 'invalid_grant'
    async with oauth_database() as session:
        tokens = (await session.scalars(select(OAuthToken))).all()
        assert len(tokens) == 2


async def test_refresh_replay_revokes_cross_process_winner(oauth_database):
    """竞争旧 refresh 后整链撤销，即使另一个进程刚发行成功也不能继续使用。"""
    if oauth_database.kw['bind'].url.drivername != 'postgresql+asyncpg':
        pytest.skip('跨进程门禁需要专属 PostgreSQL')
    issued = await OAuthTokenService(oauth_database, POLICY).token_response(token_request(request_data()))
    assert issued.status_code == 200
    payload = {'grant_type': 'refresh_token', 'client_id': 'desktop', 'resource': POLICY.mcp_resource,
               'refresh_token': issued.body['refresh_token']}
    action = {'action': 'token', 'pairs': list(payload.items())}
    results = await race(oauth_database, action, action)
    assert sorted(result['status'] for result in results) == [200, 400]
    winner = next(result['body'] for result in results if result['status'] == 200)
    async with oauth_database() as session:
        grant = await session.get(OAuthGrant, 'grant-1')
        assert grant.revoked_at is not None and grant.revocation_reason == 'refresh_replay'
        assert (await session.scalar(select(OAuthRefreshFamily))).revoked_at is not None
    # 整链失效由 Grant/Family 判定，不要求每条已消费凭证另写 revoked_at。
    retry = await OAuthTokenService(oauth_database, POLICY).token_response(
        token_request({**payload, 'refresh_token': winner['refresh_token']}))
    assert retry.status_code == 400 and retry.body['error'] == 'invalid_grant'
    secret = 'mcp-multiprocess-secret-2026-safe-test'
    await OAuthServiceRegistry(oauth_database, POLICY).create('mcp-service', '并发探针', secret)
    introspected = await OAuthResourceService(oauth_database, POLICY).response(
        'introspection', service_request({'token': winner['access_token']}, secret=secret))
    assert introspected.body == {'active': False}


async def test_disable_and_exchange_cross_process_cannot_leave_active_delegation(oauth_database, mcp_access):
    """真实事务先后顺序可以不同；最终服务停用、委托全失效，用户 Grant 保留。"""
    request = service_request(exchange_data(mcp_access['access_token']))
    exchange, disabled = await race(oauth_database, {'action': 'exchange', 'pairs': list(exchange_data(mcp_access['access_token']).items()), 'headers': dict(request.headers)},
                                   {'action': 'disable'})
    assert disabled == {'status': 200, 'active': False}
    assert exchange['status'] in {200, 400}
    async with oauth_database() as session:
        assert not (await session.get(OAuthMcpService, 'mcp-service')).is_active
        assert (await session.get(OAuthGrant, 'grant-1')).revoked_at is None
        tokens = (await session.scalars(select(OAuthToken).where(OAuthToken.service_id == 'mcp-service'))).all()
        assert all(token.revoked_at is not None for token in tokens)
        if exchange['status'] == 200:
            assert any(token.token_hash == credential_digest(exchange['body']['access_token']) for token in tokens)
