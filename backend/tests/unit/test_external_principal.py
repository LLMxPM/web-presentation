"""文件功能：验证外部主体的来源隔离、不可变授权快照和 PAT/委托共用的权限规则。"""

from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.user import User
from app.services.external_principal import DelegatedCredential, ExternalPrincipal, PatCredential


def _credential(source: str) -> PatCredential | DelegatedCredential:
    """构造已验证身份的测试快照，不模拟 HTTP Token 验证。"""

    if source == "pat":
        return PatCredential(token_id=1, public_id="pat-public", name="测试 PAT", expires_at=None)
    return DelegatedCredential(
        public_id="delegated-public", grant_id="grant-1", client_id="client-1", service_id="mcp-1",
        issuer="https://platform.example", audience="https://platform.example/api/v1", expires_at=utc_now(),
    )


@pytest.mark.parametrize("source", ["pat", "delegated"])
@pytest.mark.parametrize(
    ("required", "mode", "allowed"),
    [((), "all", True), ((), "any", False), (("page:read",), "all", True),
     (("page:read", "component:read"), "all", False), (("page:read", "component:read"), "any", True)],
)
def test_principal_scope_rules_are_source_independent(source: str, required: tuple[str, ...], mode: str, allowed: bool) -> None:
    """两种来源都遵循同一 all/any 判断，不能因来源增加权限。"""

    principal = ExternalPrincipal(User(id=1), _credential(source), frozenset({2}), frozenset({"page:read"}))
    assert principal.has_required_scopes(required, mode=mode) is allowed


def test_principal_permissions_are_frozen_and_sources_cannot_mix() -> None:
    """权限集合复制后不可变，委托身份不能启用全空间或使用伪造来源。"""

    spaces, scopes = {2}, {"page:read"}
    principal = ExternalPrincipal(User(id=1), _credential("pat"), spaces, scopes)
    spaces.add(3)
    scopes.add("page:write")
    assert not principal.can_access_workspace(3)
    assert not principal.has_scope("page:write")
    with pytest.raises(FrozenInstanceError):
        principal.all_workspaces = True
    with pytest.raises(ValueError, match="具体工作空间"):
        ExternalPrincipal(User(id=1), _credential("delegated"), frozenset({2}), frozenset(), all_workspaces=True)
    with pytest.raises(ValueError, match="凭证来源"):
        ExternalPrincipal(User(id=1), "delegated", frozenset({2}), frozenset())
    with pytest.raises(ValueError, match="未知 Scope"):
        principal.has_required_scopes((), mode="invalid")


@pytest.mark.parametrize("source", ["pat", "delegated"])
async def test_workspace_requires_both_authorization_and_live_membership(source: str) -> None:
    """授权空间外不得查询成员；授权空间内成员退出后也必须拒绝。"""

    principal = ExternalPrincipal(User(id=1), _credential(source), frozenset({2}), frozenset())
    session = AsyncMock()
    with pytest.raises(AppException) as outside:
        await principal.ensure_workspace_access(3, session)
    assert outside.value.code == "WORKSPACE_NOT_AUTHORIZED"
    session.scalar.assert_not_awaited()
    session.scalar.return_value = None
    with pytest.raises(AppException) as inactive:
        await principal.ensure_workspace_access(2, session)
    assert inactive.value.code == "PERMISSION_DENIED"
    session.scalar.return_value = object()
    await principal.ensure_workspace_access(2, session)
