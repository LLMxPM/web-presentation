"""文件功能：验证项目服务创建流程的事务提交边界。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.user import User
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.schemas.project import ProjectCreateRequest
from app.schemas.workspace import WorkspaceCreateRequest
from app.services.project_service import ProjectService
from app.services.workspace_service import WorkspaceService


@pytest.mark.asyncio
async def test_project_create_commits_exactly_once(
    app_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """项目创建默认事务应仅由编码生成器提交一次。"""

    user = User(
        username="project_transaction_user",
        password_hash="hash123",
        display_name="Project Transaction User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    app_session.add(user)
    await app_session.commit()
    workspace = await WorkspaceService(app_session).create(
        WorkspaceCreateRequest(name="Project Transaction Workspace"),
        operator_id=user.id,
    )

    original_commit = app_session.commit
    commit_count = 0

    async def counted_commit() -> None:
        """记录项目创建期间的真实提交次数。"""

        nonlocal commit_count
        commit_count += 1
        await original_commit()

    monkeypatch.setattr(app_session, "commit", counted_commit)

    project = await ProjectService(app_session).create(
        ProjectCreateRequest(
            workspace_id=workspace.id,
            name="Single Commit Project",
        ),
        operator_id=user.id,
    )

    assert project.name == "Single Commit Project"
    assert commit_count == 1
