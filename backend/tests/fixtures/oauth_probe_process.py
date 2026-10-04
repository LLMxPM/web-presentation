"""文件功能：在独立进程执行真实 OAuth 服务事务，凭证只经私有 stdin/stdout 管道交换。"""

import asyncio
import json
import os
import sys

from app.services.oauth.request import ProtocolRequest
from app.services.oauth.resource_service import OAuthResourceService
from app.services.oauth.service_registry import OAuthServiceRegistry
from app.services.oauth.token_service import OAuthTokenService
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.fixtures.oauth import POLICY


async def main():
    """仅接受明确测试库/专属 Schema，共同放行后执行生产锁与事务，禁止领域 Mock。"""
    data = json.loads(sys.stdin.readline())
    url = make_url(os.environ['OAUTH_TEST_POSTGRES_DATABASE_URL'])
    assert url.drivername == 'postgresql+asyncpg' and (url.database or '').startswith('wp_oauth_test_')
    assert data['schema'].startswith('wp_oauth_probe_')
    engine = create_async_engine(url, connect_args={'server_settings': {'search_path': data['schema']}})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.connect() as connection:
            await connection.exec_driver_sql('SELECT 1')
        print('ready', flush=True)
        assert sys.stdin.readline().strip() == 'run'
        request = ProtocolRequest(method='POST', uri=POLICY.issuer + '/oauth/token',
                                  pairs=data.get('pairs', []), headers=data.get('headers', {}))
        if data['action'] == 'token':
            result = await OAuthTokenService(factory, POLICY).token_response(request)
            output = {'status': result.status_code, 'body': result.body}
        elif data['action'] == 'exchange':
            result = await OAuthResourceService(factory, POLICY).response('exchange', request)
            output = {'status': result.status_code, 'body': result.body}
        else:
            assert data['action'] == 'disable'
            result = await OAuthServiceRegistry(factory, POLICY).disable('mcp-service')
            output = {'status': 200, 'active': result.is_active}
        print('wp-oauth-probe-result ' + json.dumps(output), flush=True)
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
