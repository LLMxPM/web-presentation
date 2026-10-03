"""文件功能：定义与 PAT 存储解耦的外部主体、凭证来源及统一 Scope/空间权限检查。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.enums import RecordStatus
from app.models.user import User
from app.models.workspace import WorkspaceMember


@dataclass(frozen=True, slots=True)
class PatCredential:
    """已验证 PAT 的兼容快照，只保存公共信息，不持有原始令牌或 ORM 记录。"""

    token_id: int
    public_id: str
    name: str
    expires_at: datetime | None
    source: Literal["pat"] = field(default="pat", init=False)


@dataclass(frozen=True, slots=True)
class DelegatedCredential:
    """委托验证器完成授权检查后的身份快照；本结构本身不负责认证。"""

    public_id: str
    grant_id: str
    client_id: str
    service_id: str
    issuer: str
    audience: str
    expires_at: datetime
    source: Literal["delegated"] = field(default="delegated", init=False)


@dataclass(frozen=True, slots=True)
class ExternalPrincipal:
    """统一外部业务主体；权限快照不可变，空间访问仍复核当前成员资格。"""

    user: User = field(repr=False)
    credential: PatCredential | DelegatedCredential
    workspace_ids: frozenset[int]
    scopes: frozenset[str]
    all_workspaces: bool = False

    def __post_init__(self) -> None:
        """拒绝未知身份和委托全空间授权，并冻结传入的权限集合。"""

        if not isinstance(self.credential, (PatCredential, DelegatedCredential)):
            raise ValueError("外部主体必须使用已验证的 PAT 或委托凭证来源。")
        if isinstance(self.credential, DelegatedCredential) and self.all_workspaces:
            raise ValueError("委托凭证必须授权具体工作空间，不能授权未来空间。")
        object.__setattr__(self, "workspace_ids", frozenset(self.workspace_ids))
        object.__setattr__(self, "scopes", frozenset(self.scopes))

    def has_scope(self, scope: str) -> bool:
        """判断权限快照是否包含指定业务 Scope。"""

        return scope in self.scopes

    def has_all_scopes(self, required_scopes: tuple[str, ...]) -> bool:
        """判断是否拥有操作要求的全部 Scope；空要求允许通过。"""

        return all(scope in self.scopes for scope in required_scopes)

    def has_required_scopes(self, required_scopes: tuple[str, ...], *, mode: str = "all") -> bool:
        """按注册表的 all/any 规则判断权限；未知模式拒绝而非隐式放行。"""

        if mode == "any":
            return any(scope in self.scopes for scope in required_scopes)
        if mode == "all":
            return self.has_all_scopes(required_scopes)
        raise ValueError(f"未知 Scope 判断模式：{mode}")

    def can_access_workspace(self, workspace_id: int) -> bool:
        """判断授权范围是否覆盖空间；此结果不能替代实时成员检查。"""

        return self.all_workspaces or workspace_id in self.workspace_ids

    async def ensure_workspace_access(self, workspace_id: int, session: AsyncSession) -> None:
        """同时校验凭证空间范围与用户当前的活跃成员资格。"""

        if not self.can_access_workspace(workspace_id):
            raise AppException(
                status_code=403,
                code="WORKSPACE_NOT_AUTHORIZED",
                detail=f"当前令牌未被授权访问工作空间 ID {workspace_id}。",
            )
        member = await session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == self.user.id,
                WorkspaceMember.status == RecordStatus.ACTIVE.value,
            )
        )
        if member is None:
            raise AppException(
                status_code=403,
                code="PERMISSION_DENIED",
                detail=f"用户已不再是工作空间 ID {workspace_id} 的活跃成员。",
            )
