"""文件功能：验证组件分享包携带页面音频资源并在目标工作空间重建引用。"""

from __future__ import annotations

import io
import json
import zipfile

from httpx import AsyncClient


async def _create_workspace(client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回 ID。"""

    response = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


async def _upload_audio(client: AsyncClient, workspace_id: int, name: str) -> dict:
    """上传组件分享包测试使用的音频资源。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (f"{name}.mp3", b"component-audio-bytes", "audio/mpeg")},
        data={"asset_type": "audio", "tags": "[]", "name": name},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_component_share_package_should_roundtrip_audio_reference(
    authenticated_client: AsyncClient,
) -> None:
    """组件包应自动收录 AssetAudio 引用，导入后保留资源名、hash 与可播放字节。"""

    source_workspace_id = await _create_workspace(authenticated_client, "组件音频源空间")
    audio_asset = await _upload_audio(authenticated_client, source_workspace_id, "confirm_soft")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": source_workspace_id,
            "name": "确认音效卡片",
            "import_name": "ConfirmSoundCard",
            "content": '<template><AssetAudio name="confirm_soft" class="w-full h-16" /></template>',
            "component_type": "内容组件",
            "preview_schema": '{"props":{"width":{"type":"number","default":960},"height":{"type":"number","default":96}}}',
        },
    )
    assert create_response.status_code == 200, create_response.text
    component_id = create_response.json()["id"]

    publish_response = await authenticated_client.post(
        f"/api/components/{component_id}/publish",
        json={"release_name": "audio-v1"},
    )
    assert publish_response.status_code == 200, publish_response.text

    export_response = await authenticated_client.post(
        "/api/components/export-package",
        json={"workspace_id": source_workspace_id, "component_ids": [component_id]},
    )
    assert export_response.status_code == 200, export_response.text
    with zipfile.ZipFile(io.BytesIO(export_response.content)) as archive:
        names = archive.namelist()
        assert any(name.startswith("assets/") and name.endswith(".mp3") for name in names)
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert any(
            item["name"] == "confirm_soft" and item["asset_type"] == "audio"
            for item in manifest["assets"]
        )

    target_workspace_id = await _create_workspace(authenticated_client, "组件音频目标空间")
    import_response = await authenticated_client.post(
        "/api/components/import-package",
        data={"workspace_id": str(target_workspace_id)},
        files={"archive": ("component.zip", export_response.content, "application/zip")},
    )
    assert import_response.status_code == 200, import_response.text
    imported = import_response.json()
    assert imported["imported_components"]
    assert any(
        item["name"] == "confirm_soft" and item["asset_type"] == "audio"
        for item in imported["assets"]
    )
    assert any(
        'AssetAudio name="confirm_soft"' in item["content"]
        for item in imported["imported_components"]
    )

    target_assets = await authenticated_client.get(
        f"/api/workspaces/{target_workspace_id}/assets",
        params={"asset_type": "audio"},
    )
    assert target_assets.status_code == 200
    items = target_assets.json()["items"]
    assert len(items) == 1
    assert items[0]["file_hash"] == audio_asset["file_hash"]

    file_response = await authenticated_client.get(
        f"/api/workspaces/{target_workspace_id}/assets/{items[0]['id']}/file",
    )
    assert file_response.status_code == 200
    assert file_response.content == b"component-audio-bytes"
