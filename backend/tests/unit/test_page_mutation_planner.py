"""文件功能：验证页面 Mutation Planner 的版本基线校验与源码编辑规划。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.mutation_planners.page_mutation_planner import PageMutationPlanner


@pytest.mark.asyncio
async def test_plan_apply_edits_uses_page_current_version_for_base_check() -> None:
    """页面详情对象不能直接作为版本号传入乐观锁校验。"""

    current_content = "<template><main>旧内容</main></template>"
    next_content = "<template><main>新内容</main></template>"
    page_detail = SimpleNamespace(
        project_id=7,
        current_version_no=2,
        title="测试页面",
        summary="页面摘要",
        speaker_notes=None,
    )

    planner = PageMutationPlanner.__new__(PageMutationPlanner)
    planner.page_service = SimpleNamespace(
        get=AsyncMock(return_value=page_detail),
        get_version_content=AsyncMock(
            return_value=SimpleNamespace(content=current_content)
        ),
    )
    planner.code_check_service = SimpleNamespace(
        check_page_code=AsyncMock(
            return_value={
                "success": True,
                "status": "passed",
                "summary": "代码检查通过。",
                "diagnostics": [],
            }
        )
    )

    result = await planner.plan_apply_edits(
        workspace_id=1,
        project_id=7,
        page_id=11,
        base_version_no=2,
        user_id=3,
        edits=[{"type": "rewrite_file", "content": next_content}],
    )

    assert result.success is True
    assert result.prepared_content == next_content
    planner.page_service.get_version_content.assert_awaited_once_with(
        11, 2, user_id=3
    )
    planner.code_check_service.check_page_code.assert_awaited_once()

