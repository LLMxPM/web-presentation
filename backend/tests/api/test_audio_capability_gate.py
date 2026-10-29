"""文件功能：验证能力关闭时页面旁白、useAudioCue 与项目 cue 写入被稳定业务码硬拒绝。"""

from __future__ import annotations

from httpx import AsyncClient

AUDIO_CAPABILITY_UNAVAILABLE = "AUDIO_CAPABILITY_UNAVAILABLE"


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


async def test_page_content_audio_allowed_but_narration_rejected(
    authenticated_client: AsyncClient, closed_audio_capabilities: None
) -> None:
    """内容音频随 audio_assets 继续可用；旁白在 page_narration 关闭时拒绝落库。"""

    workspace_id = await _create_workspace(authenticated_client, "页面音频能力空间")
    project_id = await _create_project(authenticated_client, workspace_id)

    content_audio = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": '<template><main><AssetAudio name="bgm" /></main></template>',
            "file_type": "vue",
            "title": "内容音频",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert content_audio.status_code == 200, content_audio.text

    narration = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": '<template><main><AssetAudio name="bgm" purpose="narration" /></main></template>',
            "file_type": "vue",
            "title": "旁白",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert narration.status_code == 422, narration.text
    assert narration.json()["code"] == AUDIO_CAPABILITY_UNAVAILABLE
    assert "page_narration" in narration.json()["message"]

    listed = await authenticated_client.get(f"/api/pages?workspace_id={workspace_id}&project_assigned=true")
    assert listed.status_code == 200, listed.text
    titles = [item["title"] for item in listed.json()["items"]]
    assert titles == ["内容音频"]


async def test_page_use_audio_cue_alias_is_rejected(
    authenticated_client: AsyncClient, closed_audio_capabilities: None
) -> None:
    """别名导入的 useAudioCue 调用同样按 audio_cues 能力拒绝，避免绕过门禁。"""

    workspace_id = await _create_workspace(authenticated_client, "页面 cue 能力空间")
    project_id = await _create_project(authenticated_client, workspace_id)
    source = (
        "<template><main>确认</main></template>\n"
        "<script setup lang=\"ts\">\n"
        "import { useAudioCue as playCue } from '@runtime-kit/public/composables/audio/useAudioCue.v1'\n"
        "const { playCue: play } = playCue()\n"
        "play('interaction.confirm')\n"
        "</script>\n"
    )

    response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": source,
            "file_type": "vue",
            "title": "cue 页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == AUDIO_CAPABILITY_UNAVAILABLE
    assert "audio_cues" in response.json()["message"]


async def test_component_narration_is_rejected(
    authenticated_client: AsyncClient, closed_audio_capabilities: None
) -> None:
    """组件创建同样受能力门禁约束，不靠发布阶段兜底。"""

    workspace_id = await _create_workspace(authenticated_client, "组件音频能力空间")
    response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "旁白组件",
            "import_name": "NarrationCard",
            "content": '<template><AssetAudio name="bgm" purpose="narration" /></template>',
            "component_type": "内容组件",
            "preview_schema": '{"props":{"width":{"type":"number","default":960},"height":{"type":"number","default":96}}}',
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == AUDIO_CAPABILITY_UNAVAILABLE
    assert "page_narration" in response.json()["message"]


async def test_narration_page_is_allowed_when_capability_open(
    authenticated_client: AsyncClient,
    open_audio_capabilities: None,
) -> None:
    """能力开放组合下相同源码可以保存，证明拒绝来自能力而非语法误判。"""

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
