"""文件功能：验证旁白默认开放，无需任何测试功能门或环境开关。"""

from __future__ import annotations

from httpx import AsyncClient



async def _create_workspace(client: AsyncClient, name: str) -> int:
    """创建工作空间并返回 ID。"""

    response = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _create_project(client: AsyncClient, workspace_id: int) -> int:
    """创建项目并返回 ID。"""

    response = await client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "音频能力门禁项目", "status": "active"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]








async def test_narration_page_is_allowed_by_default(
    authenticated_client: AsyncClient,

) -> None:
    """旁白源码可直接保存，仍经过参数、权限与资源边界校验。"""

    workspace_id = await _create_workspace(authenticated_client, "页面旁白开放空间")
    project_id = await _create_project(authenticated_client, workspace_id)
    response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": '<template><main><AssetAudio name="bgm" purpose="narration" /></main></template>',
            "file_type": "vue",
            "title": "旁白开放",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )

    assert response.status_code == 200, response.text
