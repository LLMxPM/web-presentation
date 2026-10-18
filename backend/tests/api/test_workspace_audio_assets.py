"""文件功能：验证工作空间 audio 资源的上传、严格 MIME、替换与受保护分段读取。"""

from __future__ import annotations

import pytest
from app.models.asset import WorkspaceAsset
from httpx import AsyncClient
from sqlalchemy import String


async def _create_workspace(client: AsyncClient, name: str) -> int:
    """创建当前用户可管理的测试工作空间。"""

    response = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _upload_audio(
    client: AsyncClient,
    workspace_id: int,
    *,
    file_name: str,
    content_type: str,
    content: bytes,
    name: str,
) -> dict:
    """通过公开上传接口创建音频并返回响应对象。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (file_name, content, content_type)},
        data={"asset_type": "audio", "tags": '["音频"]', "name": name},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_workspace_asset_type_column_should_remain_string() -> None:
    """增加 audio 枚举不应把现有跨数据库字符串列变为数据库枚举。"""

    assert isinstance(WorkspaceAsset.__table__.c.asset_type.type, String)


@pytest.mark.parametrize(
    ("file_name", "content_type"),
    [
        ("narration.mp3", "audio/mpeg"),
        ("narration.m4a", "audio/mp4"),
        ("narration-alt.m4a", "audio/x-m4a"),
        ("narration.aac", "audio/aac"),
        ("effect.ogg", "audio/ogg"),
        ("effect.wav", "audio/wav"),
        ("effect-alt.wav", "audio/x-wav"),
    ],
)
async def test_audio_upload_should_accept_contract_formats(
    authenticated_client: AsyncClient,
    file_name: str,
    content_type: str,
) -> None:
    """契约允许的扩展名/MIME 组合应可上传并保持 audio 派生字段。"""

    workspace_id = await _create_workspace(authenticated_client, f"音频格式 {file_name}")
    payload = await _upload_audio(
        authenticated_client,
        workspace_id,
        file_name=file_name,
        content_type=content_type,
        content=b"audio-contract-bytes",
        name=file_name.replace(".", "_"),
    )

    assert payload["asset_type"] == "audio"
    assert payload["asset_role"] == "content"
    assert payload["render_type"] == "audio"
    assert payload["content_type"] == content_type
    assert payload["content_editable"] is False
    assert payload["approx_aspect_ratio"] is None

    list_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"asset_type": "audio"},
    )
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["items"]] == [payload["id"]]


@pytest.mark.parametrize(
    ("file_name", "content_type", "expected_code"),
    [
        ("narration.flac", "audio/flac", "ASSET_FILE_TYPE_UNSUPPORTED"),
        ("narration.mp3", "audio/wav", "ASSET_CONTENT_TYPE_UNSUPPORTED"),
        ("narration.mp3", "video/mp4", "ASSET_CONTENT_TYPE_UNSUPPORTED"),
        ("narration.mp3", "application/octet-stream", "ASSET_CONTENT_TYPE_UNSUPPORTED"),
        ("narration.m4a", "audio/mpeg", "ASSET_CONTENT_TYPE_UNSUPPORTED"),
    ],
)
async def test_audio_upload_should_reject_unsupported_or_mismatched_type(
    authenticated_client: AsyncClient,
    file_name: str,
    content_type: str,
    expected_code: str,
) -> None:
    """音频扩展名和 MIME 必须同时命中同一契约组合。"""

    workspace_id = await _create_workspace(authenticated_client, f"音频拒绝 {file_name} {content_type}")
    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (file_name, b"invalid-audio", content_type)},
        data={"asset_type": "audio", "tags": "[]", "name": "invalid_audio"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == expected_code


async def test_audio_should_not_use_text_content_endpoint(authenticated_client: AsyncClient) -> None:
    """audio 是二进制内容资源，不能通过文本创建接口绕过文件校验。"""

    workspace_id = await _create_workspace(authenticated_client, "音频不可文本创建")
    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "audio",
            "name": "not_text_audio",
            "original_name": "not-text.mp3",
            "content": "not-audio",
            "tags": [],
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "ASSET_CONTENT_EDIT_UNSUPPORTED"


async def test_audio_replace_should_revalidate_mime_and_create_history(
    authenticated_client: AsyncClient,
) -> None:
    """按 ID 替换继续执行 audio MIME 校验，成功后保留类型并创建历史。"""

    workspace_id = await _create_workspace(authenticated_client, "音频替换")
    original = await _upload_audio(
        authenticated_client,
        workspace_id,
        file_name="narration.mp3",
        content_type="audio/mpeg",
        content=b"original-audio",
        name="narration",
    )

    rejected = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{original['id']}/replace",
        files={"file": ("narration-v2.mp3", b"bad-type", "audio/wav")},
    )
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "ASSET_CONTENT_TYPE_UNSUPPORTED"

    replaced = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{original['id']}/replace",
        files={"file": ("narration-v2.wav", b"replacement-audio", "audio/wav")},
    )
    assert replaced.status_code == 200, replaced.text
    payload = replaced.json()
    assert payload["id"] == original["id"]
    assert payload["asset_type"] == "audio"
    assert payload["original_name"] == "narration-v2.wav"
    assert payload["content_type"] == "audio/wav"
    assert payload["file_hash"] != original["file_hash"]

    history_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"asset_type": "audio", "history_only": "true", "status": "archived"},
    )
    assert history_response.status_code == 200
    history_items = history_response.json()["items"]
    assert len(history_items) == 1
    assert history_items[0]["source_asset_id"] == original["id"]
    assert history_items[0]["content_type"] == "audio/mpeg"


async def test_audio_file_should_support_head_etag_and_range(authenticated_client: AsyncClient) -> None:
    """受保护音频读取应保持 MIME，并支持播放器 seek 所需的 HEAD/Range。"""

    workspace_id = await _create_workspace(authenticated_client, "音频分段读取")
    content = b"0123456789abcdef"
    asset = await _upload_audio(
        authenticated_client,
        workspace_id,
        file_name="seekable.mp3",
        content_type="audio/mpeg",
        content=content,
        name="seekable_audio",
    )
    file_url = f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file"

    head = await authenticated_client.head(file_url)
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-type"] == "audio/mpeg"
    assert head.headers["content-length"] == str(len(content))
    assert head.headers["accept-ranges"] == "bytes"

    ranged = await authenticated_client.get(file_url, headers={"Range": "bytes=4-9"})
    assert ranged.status_code == 206
    assert ranged.content == content[4:10]
    assert ranged.headers["content-type"] == "audio/mpeg"
    assert ranged.headers["content-range"] == f"bytes 4-9/{len(content)}"
    assert ranged.headers["etag"] == f'"{asset["file_hash"]}"'

    not_modified = await authenticated_client.get(
        file_url,
        headers={"If-None-Match": f'"{asset["file_hash"]}"'},
    )
    assert not_modified.status_code == 304
    assert not_modified.content == b""


async def test_audio_should_copy_archive_restore_and_download(authenticated_client: AsyncClient) -> None:
    """audio 复用统一二进制资源生命周期，不需要专用旁路。"""

    workspace_id = await _create_workspace(authenticated_client, "音频复制归档恢复")
    asset = await _upload_audio(
        authenticated_client,
        workspace_id,
        file_name="lifecycle.mp3",
        content_type="audio/mpeg",
        content=b"lifecycle-audio",
        name="lifecycle_audio",
    )

    copied = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/copy",
        json={"name": "lifecycle_audio_copy", "original_name": "lifecycle-copy.mp3"},
    )
    assert copied.status_code == 200, copied.text
    assert copied.json()["asset_type"] == "audio"
    assert copied.json()["file_hash"] == asset["file_hash"]

    archived = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/archive",
        json={"archive_reason": "音频生命周期测试"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    restored = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/restore",
        json={"restore_reason": "恢复音频"},
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"

    downloaded = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file",
        params={"download": 1},
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"lifecycle-audio"
    assert "attachment" in downloaded.headers["content-disposition"]
    assert "lifecycle.mp3" in downloaded.headers["content-disposition"]
