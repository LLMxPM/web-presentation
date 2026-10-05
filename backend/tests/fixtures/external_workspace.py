"""文件功能：在 OAuth 隔离库内准备同一用户授权两个空间的 PAT/委托测试身份。"""

import pytest

from app.models.oauth_grant import OAuthGrant
from app.models.page import Page
from app.models.workspace import WorkspaceMember
from app.models.workspace_component import WorkspaceComponent
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.services.api_access_token_service import ApiAccessTokenService
from tests.fixtures.oauth_mutations import (
    SCOPES,
    SOURCE,
    other_user_access,
    refresh_access,
)


@pytest.fixture
async def multi_workspace_client(oauth_mutation_client):
    """扩展真实 Grant 和成员关系；所有凭证仍通过生产发行流程，不覆盖鉴权依赖。"""
    client, factory, access, _ = oauth_mutation_client
    await other_user_access(client, factory)
    async with factory() as session:
        session.add(WorkspaceMember(workspace_id=2, user_id=1))
        (await session.get(OAuthGrant, "grant-1")).workspace_ids = [1, 2]
        session.add(Page(id=2, workspace_id=2, project_id=2, code="second-page", title="空间二页面", page_content=SOURCE, created_by=1))
        session.add(WorkspaceComponent(id=2, workspace_id=2, code="second-component", name="空间二组件", import_name="SecondCard", content=SOURCE, created_by=1))
        await session.commit()
        pat = await ApiAccessTokenService(session).create_token(user_id=1, payload=ApiAccessTokenCreateRequest(
            name="双空间测试", workspace_ids=[1, 2], scopes=SCOPES))
    issued = await refresh_access(client, access["refresh_token"])
    return client, factory, issued, pat.token
