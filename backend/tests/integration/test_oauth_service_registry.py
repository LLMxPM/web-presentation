"""文件功能：验证 MCP 服务运维的真实认证、停用不复活、事务回滚及并发交换围栏。"""

import asyncio

import pytest
from app.core.exceptions import AppException
from app.core.security import verify_password
from app.models.oauth_audit import OAuthAuditEvent
from app.models.oauth_credential import OAuthToken
from app.models.oauth_registration import OAuthMcpService
from app.services.oauth import resource_service
from app.services.oauth.delegated_identity import authenticate_delegated
from app.services.oauth.resource_service import OAuthResourceService
from app.services.oauth.service_registry import OAuthServiceRegistry
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fixtures.oauth import POLICY
from tests.fixtures.oauth_resource import exchange_data, service_request

SECRET = "registry-secret-" * 3
ROTATED = "rotated-secret-" * 3


async def test_register_only_public_metadata_and_real_authentication(
    oauth_database, mcp_access
):
    """新服务绑定配置 audience、只存哈希，公共输出无秘密并可真实自省。"""
    registry = OAuthServiceRegistry(oauth_database, POLICY)
    summary = await registry.create("new-mcp", "新 MCP 服务", SECRET)
    assert (
        summary.resource == POLICY.mcp_resource
        and summary.api_audience == POLICY.api_audience
    )
    assert summary.is_active is True
    assert set(summary.to_dict()) == {
        "service_id",
        "name",
        "resource",
        "api_audience",
        "is_active",
    }
    async with oauth_database() as session:
        row = await session.get(OAuthMcpService, "new-mcp")
        assert row.secret_hash != SECRET and verify_password(SECRET, row.secret_hash)
        audit = await session.scalar(
            select(OAuthAuditEvent).where(OAuthAuditEvent.service_id == "new-mcp")
        )
        assert audit.event == "service_created" and audit.user_id is None
        assert row.secret_hash not in repr(summary)
    result = await OAuthResourceService(oauth_database, POLICY).response(
        "introspection",
        service_request(
            {"token": mcp_access["access_token"]}, service_id="new-mcp", secret=SECRET
        ),
    )
    assert result.body["active"] is True
    assert [row.service_id for row in await registry.list_services()] == [
        "mcp-service",
        "new-mcp",
    ]


@pytest.mark.parametrize(
    "service_id,name,secret",
    [
        ("desktop", "冲突", SECRET),
        ("mcp-service", "重复", SECRET),
        ("https://other.test", "非法 ID", SECRET),
        ("bad ID", "非法 ID", SECRET),
        ("new-mcp", "", SECRET),
        ("new-mcp", "含\n控制字符", SECRET),
        ("new-mcp", "短密钥", "short"),
        ("new-mcp", "空白密钥", " " * 32),
    ],
)
async def test_registration_rejects_overwrite_or_invalid_input(
    oauth_database, mcp_access, service_id, name, secret
):
    """错误输入和同名登记不能覆盖已启用服务，也不能创建第二份身份。"""
    registry = OAuthServiceRegistry(oauth_database, POLICY)
    with pytest.raises(ValueError):
        await registry.create(service_id, name, secret)
    async with oauth_database() as session:
        assert (
            await session.scalar(select(func.count()).select_from(OAuthMcpService)) == 1
        )
        assert verify_password(
            "service-secret",
            (await session.get(OAuthMcpService, "mcp-service")).secret_hash,
        )


async def test_rotate_disable_and_explicit_enable_never_revives_old_delegation(
    oauth_database, mcp_access
):
    """旧 Basic 即时失效；停用撤销旧委托，显式换新密钥启用后旧委托仍拒绝。"""
    registry = OAuthServiceRegistry(oauth_database, POLICY)
    service = OAuthResourceService(oauth_database, POLICY)
    await registry.rotate("mcp-service", SECRET)
    data = {"token": mcp_access["access_token"]}
    assert (await service.response("introspection", service_request(data))).body[
        "error"
    ] == "invalid_client"
    assert (
        await service.response("introspection", service_request(data, secret=SECRET))
    ).body["active"]
    delegated = await service.response(
        "exchange",
        service_request(exchange_data(mcp_access["access_token"]), secret=SECRET),
    )
    async with oauth_database() as session:
        assert (
            await authenticate_delegated(
                session, delegated.body["access_token"], POLICY
            )
        ).user.id == 1
        exchanged_audit = await session.scalar(
            select(OAuthAuditEvent).where(
                OAuthAuditEvent.event == "token_exchanged",
            )
        )
        assert exchanged_audit.service_id == "mcp-service"
    for _ in range(2):
        assert (await registry.disable("mcp-service")).is_active is False
    assert (await registry.rotate("mcp-service", ROTATED)).is_active is False
    assert (
        await service.response("introspection", service_request(data, secret=ROTATED))
    ).body["error"] == "invalid_client"
    assert (await registry.rotate("mcp-service", SECRET, enable=True)).is_active is True
    assert (
        await service.response("introspection", service_request(data, secret=SECRET))
    ).body["active"]
    async with oauth_database() as session:
        with pytest.raises(AppException):
            await authenticate_delegated(
                session, delegated.body["access_token"], POLICY
            )
        events = (
            await session.scalars(
                select(OAuthAuditEvent.event).where(
                    OAuthAuditEvent.service_id == "mcp-service",
                )
            )
        ).all()
        assert events.count("service_disabled") == 1
        assert events.count("service_enabled") == 1


async def test_registration_commit_failure_rolls_back_state_and_audit(
    oauth_database, mcp_access, monkeypatch
):
    """运维提交失败时服务仍启用、委托和审计均没有部分写入。"""

    async def fail_commit(self):
        """注入提交故障，不在测试里接触开发数据库。"""
        raise RuntimeError("commit unavailable")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    with pytest.raises(RuntimeError):
        await OAuthServiceRegistry(oauth_database, POLICY).disable("mcp-service")
    async with oauth_database() as session:
        assert (await session.get(OAuthMcpService, "mcp-service")).is_active is True
        assert (
            await session.scalar(
                select(func.count())
                .select_from(OAuthAuditEvent)
                .where(
                    OAuthAuditEvent.service_id == "mcp-service",
                )
            )
            == 0
        )


async def test_duplicate_registration_race_only_creates_one_identity(oauth_database):
    """独立 Session 竞争同名注册只有一项成功，不依赖进程字典或隐式 upsert。"""
    results = await asyncio.gather(
        *[
            OAuthServiceRegistry(oauth_database, POLICY).create(
                "new-mcp", "并发服务", SECRET
            )
            for _ in range(2)
        ],
        return_exceptions=True,
    )
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert all(
        not isinstance(result, Exception)
        or isinstance(result, (ValueError, IntegrityError))
        for result in results
    )
    async with oauth_database() as session:
        assert (
            await session.scalar(select(func.count()).select_from(OAuthMcpService)) == 1
        )


@pytest.mark.parametrize("exchange_first", [False, True])
async def test_disable_exchange_commit_order_is_fenced(
    oauth_database, mcp_access, monkeypatch, exchange_first
):
    """交换先锁则停用撤销其结果；停用先提交则交换失败，重新启用也无旧委托复活。"""
    entered, release = asyncio.Event(), asyncio.Event()
    original_lock = resource_service.lock_service

    async def controlled_lock(session, service_id, policy):
        """分别控制进入服务锁前后，制造两种真实数据库事务提交顺序。"""
        if exchange_first:
            acquired = await original_lock(session, service_id, policy)
        entered.set()
        await asyncio.wait_for(release.wait(), 5)
        return (
            acquired
            if exchange_first
            else await original_lock(session, service_id, policy)
        )

    monkeypatch.setattr(resource_service, "lock_service", controlled_lock)
    registry = OAuthServiceRegistry(oauth_database, POLICY)
    exchange = asyncio.create_task(
        OAuthResourceService(oauth_database, POLICY).response(
            "exchange",
            service_request(exchange_data(mcp_access["access_token"])),
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        if exchange_first:
            disabled = asyncio.create_task(registry.disable("mcp-service"))
            release.set()
            result, _ = await asyncio.wait_for(asyncio.gather(exchange, disabled), 10)
            assert result.status_code == 200
        else:
            await registry.disable("mcp-service")
            release.set()
            result = await asyncio.wait_for(exchange, 5)
            assert result.body["error"] == "invalid_client"
        await registry.rotate("mcp-service", SECRET, enable=True)
        async with oauth_database() as session:
            if exchange_first:
                with pytest.raises(AppException):
                    await authenticate_delegated(
                        session, result.body["access_token"], POLICY
                    )
            else:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(OAuthToken)
                        .where(OAuthToken.kind == "delegated")
                    )
                    == 0
                )
    finally:
        release.set()
        if not exchange.done():
            exchange.cancel()
            await asyncio.gather(exchange, return_exceptions=True)
