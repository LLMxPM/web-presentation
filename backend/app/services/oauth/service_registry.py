"""文件功能：提供受信 MCP 服务的显式登记、密钥轮换和停用事务，仅返回公共元数据。"""

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.time_utils import utc_now
from app.db.retry import run_with_write_retry
from app.models.oauth_audit import OAuthAuditEvent
from app.models.oauth_credential import OAuthToken
from app.models.oauth_registration import OAuthClient, OAuthMcpService
from app.repositories.oauth_resource_repository import lock_service
from app.services.oauth.policy import OAuthPolicy


@dataclass(frozen=True, slots=True)
class ServiceSummary:
    """运维输出只包含公共登记信息，不包含原始密钥或哈希。"""

    service_id: str
    name: str
    resource: str
    api_audience: str
    is_active: bool

    def to_dict(self) -> dict:
        """输出可序列化的公共元数据，供 CLI 和部署核对使用。"""
        return asdict(self)


def _summary(service: OAuthMcpService) -> ServiceSummary:
    """在 Session 关闭前提取公共标量，避免泄漏 ORM 密钥字段。"""
    return ServiceSummary(
        service.service_id,
        service.name,
        service.resource,
        service.api_audience,
        service.is_active,
    )


def _secret_hash(secret: str) -> str:
    """密钥必须为至少 32 字符的可打印 ASCII，不接受空白或无法用于 Basic 的字符。"""
    if not 32 <= len(secret) <= 512 or any(not 33 <= ord(c) <= 126 for c in secret):
        raise ValueError("服务密钥须为 32～512 字符的可打印 ASCII，不能包含空白。")
    return hash_password(secret)


def _audit(session: AsyncSession, service_id: str, event: str) -> None:
    """只保存固定事件和公共服务 ID；不保存密钥、哈希或运维命令内容。"""
    session.add(
        OAuthAuditEvent(
            event_id=uuid4().hex,
            event=event,
            service_id=service_id,
            created_at=utc_now(),
        )
    )


class OAuthServiceRegistry:
    """只管理服务身份；服务永远不能因此获得用户、空间或业务 Scope。"""

    def __init__(
        self, session_factory: Callable[[], AsyncSession], policy: OAuthPolicy
    ):
        """登记的源/目标地址固定来自已校验部署配置，不接受命令行任意 audience。"""
        self.session_factory = session_factory
        self.policy = policy

    async def list_services(self) -> list[ServiceSummary]:
        """列出全部公共登记，包含停用项，便于发现旧部署的地址残留。"""
        async with self.session_factory() as session:
            rows = await session.scalars(
                select(OAuthMcpService).order_by(OAuthMcpService.service_id)
            )
            return [_summary(row) for row in rows]

    async def create(self, service_id: str, name: str, secret: str) -> ServiceSummary:
        """仅创建新身份；重复 ID、客户端 ID 冲突或错误输入均不能覆盖旧配置。"""
        if not re.fullmatch(r"[a-z][a-z0-9._-]{0,127}", service_id):
            raise ValueError("服务 ID 须为小写字母开头的 1～128 字符标识。")
        if not name.strip() or len(name) > 128 or any(ord(c) < 32 for c in name):
            raise ValueError("服务名称须为 1～128 字符且不含控制字符。")
        hashed = _secret_hash(secret)

        async def persist(session: AsyncSession) -> ServiceSummary:
            """登记不采用 upsert，防止旧 ID 的秘密轮换或停用状态被意外覆盖。"""
            if await session.get(OAuthClient, service_id) or await session.get(
                OAuthMcpService, service_id
            ):
                raise ValueError("服务 ID 已存在或与用户客户端冲突。")
            row = OAuthMcpService(
                service_id=service_id,
                name=name.strip(),
                secret_hash=hashed,
                resource=self.policy.mcp_resource,
                api_audience=self.policy.api_audience,
                is_active=True,
            )
            session.add(row)
            _audit(session, service_id, "service_created")
            await session.commit()
            return _summary(row)

        return await run_with_write_retry(
            persist,
            session_factory=self.session_factory,
            backoff_delays=(0.02, 0.05, 0.1),
        )

    async def rotate(
        self, service_id: str, secret: str, *, enable: bool = False
    ) -> ServiceSummary:
        """立即替换 Basic 密钥；停用项仅在显式 enable 时恢复，已有委托不因轮换复活。"""
        return await self._change(
            service_id, hashed=_secret_hash(secret), enable=enable
        )

    async def disable(self, service_id: str) -> ServiceSummary:
        """停用身份并撤销该服务已签发委托；重复调用保持同一效果，不删除业务 Job。"""
        return await self._change(service_id, hashed=None, enable=False)

    async def _change(
        self, service_id: str, *, hashed: str | None, enable: bool
    ) -> ServiceSummary:
        """与交换共用服务 UPDATE 围栏，停用提交后不能留下随后可复活的在途委托。"""

        async def persist(session: AsyncSession) -> ServiceSummary:
            """在服务锁内复核部署边界并原子提交密钥/状态及委托撤销。"""
            if not await lock_service(
                session, service_id, self.policy, require_active=False
            ):
                raise ValueError("服务不存在或与当前部署的源/目标地址不匹配。")
            row = await session.get(OAuthMcpService, service_id, populate_existing=True)
            if hashed is None:
                was_active = row.is_active
                row.is_active = False
                await session.execute(
                    update(OAuthToken)
                    .where(
                        OAuthToken.service_id == service_id,
                        OAuthToken.kind == "delegated",
                        OAuthToken.revoked_at.is_(None),
                    )
                    .values(revoked_at=utc_now())
                    .execution_options(synchronize_session=False)
                )
                if was_active:
                    _audit(session, service_id, "service_disabled")
            else:
                row.secret_hash = hashed
                _audit(session, service_id, "service_secret_rotated")
                if enable:
                    if not row.is_active:
                        _audit(session, service_id, "service_enabled")
                    row.is_active = True
            await session.commit()
            return _summary(row)

        return await run_with_write_retry(
            persist,
            session_factory=self.session_factory,
            backoff_delays=(0.02, 0.05, 0.1),
        )
