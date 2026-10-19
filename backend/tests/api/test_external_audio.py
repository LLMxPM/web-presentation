"""文件功能：验证 External API 音频资源上传替换与项目音频设置读写、幂等及跨空间拒绝。"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.db.session import get_session_factory
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService
from app.services.workspace_style_service import WorkspaceStyleService


async def _create_external_actor(scopes: list[str]) -> tuple[str, int]:
    """创建独立用户、工作空间与指定 Scope 的 PAT。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = User(
            username=f"audio_ext_{uuid.uuid4().hex[:8]}",
            password_hash="hash",
            display_name="Audio External User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()
        workspace = Workspace(
            code=f"ws-audio-{uuid.uuid4().hex[:8]}",
            name="External 音频空间",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add(workspace)
        await session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role="owner",
                status=RecordStatus.ACTIVE.value,
            )
        )
        await session.flush()
        await WorkspaceStyleService(session).create_default_style_for_workspace(workspace, user.id)
        token_result = await ApiAccessTokenService(session).create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Audio-PAT",
                workspace_ids=[workspace.id],
                scopes=scopes,
                expires_in_days=30,
            ),
        )
        await session.commit()
        return token_result.token, workspace.id


def _headers(token: str, workspace_id: int, idempotency_key: str | None = None) -> dict[str, str]:
    """构造 External 请求头；写操作按需附加幂等键。"""

    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(workspace_id)}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


async def _upload_audio(
    client: AsyncClient,
    token: str,
    workspace_id: int,
    *,
    name: str,
    payload: bytes,
) -> dict:
    """通过 External 上传接口创建 audio 资源。"""

    response = await client.post(
        "/api/v1/assets",
        headers=_headers(token, workspace_id, f"audio-upload-{name}"),
        files={"file": (f"{name}.mp3", payload, "audio/mpeg")},
        data={"asset_type": "audio", "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _upload_image(client: AsyncClient, token: str, workspace_id: int) -> dict:
    """上传一张最小 PNG 资源，用于非 audio 绑定拒绝。"""

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    response = await client.post(
        "/api/v1/assets",
        headers=_headers(token, workspace_id, f"image-upload-{uuid.uuid4().hex[:8]}"),
        files={"file": ("cover.png", png, "image/png")},
        data={"asset_type": "image", "name": f"cover-{uuid.uuid4().hex[:6]}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_project(client: AsyncClient, token: str, workspace_id: int, payload: dict) -> dict:
    """通过 External API 创建项目。"""

    response = await client.post(
        "/api/v1/projects",
        json={"name": f"音频项目 {uuid.uuid4().hex[:6]}", "status": "active", **payload},
        headers=_headers(token, workspace_id, f"project-{uuid.uuid4().hex[:8]}"),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_external_audio_asset_should_upload_list_and_replace(client: AsyncClient) -> None:
    """audio 资源复用 External 资源接口完成上传、按类型查询与带基线替换。"""

    token, workspace_id = await _create_external_actor(["asset:read", "asset:write", "workspace:read"])
    asset = await _upload_audio(client, token, workspace_id, name="confirm", payload=b"first-audio")

    assert asset["asset_type"] == "audio"
    assert asset["render_type"] == "audio"
    assert asset["content_type"] == "audio/mpeg"

    listed = await client.get(
        "/api/v1/assets",
        params={"asset_type": "audio"},
        headers=_headers(token, workspace_id),
    )
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [asset["id"]]

    replaced = await client.post(
        f"/api/v1/assets/{asset['id']}/replace",
        headers=_headers(token, workspace_id, "audio-replace-1"),
        files={"file": ("confirm.mp3", b"second-audio", "audio/mpeg")},
        data={"expected_file_hash": asset["file_hash"]},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["asset_type"] == "audio"
    assert replaced.json()["file_hash"] != asset["file_hash"]


async def test_external_project_audio_settings_should_roundtrip_and_preserve(client: AsyncClient) -> None:
    """项目音频设置可创建、读取带资源摘要、更新、省略保留与显式清空。"""

    token, workspace_id = await _create_external_actor(
        ["project:read", "project:write", "asset:read", "asset:write", "workspace:read"]
    )
    asset = await _upload_audio(client, token, workspace_id, name="ding", payload=b"ding-audio")
    created = await _create_project(client, token, workspace_id, {
        "audio_settings": {
            "master_volume_percent": 80,
            "narration_volume_percent": 90,
            "effects_volume_percent": 25,
            "cue_bindings": [
                {"key": "transition.forward", "asset_id": asset["id"], "gain_percent": 75},
            ],
        },
    })
    assert created["audio_settings"] == {
        "master_volume_percent": 80,
        "narration_volume_percent": 90,
        "effects_volume_percent": 25,
        "cue_bindings": [
            {"key": "transition.forward", "asset_id": asset["id"], "gain_percent": 75},
        ],
    }

    project_id = created["id"]
    configuration = await client.get(
        f"/api/v1/projects/{project_id}/configuration",
        headers=_headers(token, workspace_id),
    )
    assert configuration.status_code == 200, configuration.text
    assert configuration.json()["audio_settings"] == {
        "master_volume_percent": 80,
        "narration_volume_percent": 90,
        "effects_volume_percent": 25,
        "cue_bindings": [
            {
                "key": "transition.forward",
                "asset_id": asset["id"],
                "asset_name": "ding",
                "asset_type": "audio",
                "asset_status": "active",
                "gain_percent": 75,
            },
        ],
    }

    update_payload = {
        "audio_settings": {
            "master_volume_percent": 60,
            "narration_volume_percent": 70,
            "effects_volume_percent": 40,
            "cue_bindings": [
                {"key": "transition.forward", "asset_id": asset["id"], "gain_percent": 50},
                {"key": "interaction.confirm", "asset_id": asset["id"], "gain_percent": 100},
            ],
        },
    }
    updated = await client.put(
        f"/api/v1/projects/{project_id}/configuration",
        json=update_payload,
        headers=_headers(token, workspace_id, "audio-settings-update"),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["audio_settings"]["master_volume_percent"] == 60
    assert len(updated.json()["audio_settings"]["cue_bindings"]) == 2

    # 同键同载荷重放返回首次结果。
    replay = await client.put(
        f"/api/v1/projects/{project_id}/configuration",
        json=update_payload,
        headers=_headers(token, workspace_id, "audio-settings-update"),
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["audio_settings"] == updated.json()["audio_settings"]

    # 旧客户端省略音频设置时保留现有绑定。
    renamed = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "音频项目改名"},
        headers=_headers(token, workspace_id, "audio-settings-rename"),
    )
    assert renamed.status_code == 200, renamed.text
    assert len(renamed.json()["audio_settings"]["cue_bindings"]) == 2

    # 显式空列表清空绑定，但保留音量。
    cleared = await client.put(
        f"/api/v1/projects/{project_id}/configuration",
        json={"audio_settings": {**update_payload["audio_settings"], "cue_bindings": []}},
        headers=_headers(token, workspace_id, "audio-settings-clear"),
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["audio_settings"]["cue_bindings"] == []
    assert cleared.json()["audio_settings"]["master_volume_percent"] == 60

    capabilities = await client.get(
        f"/api/v1/workspaces/{workspace_id}/capabilities",
        headers=_headers(token, workspace_id),
    )
    assert capabilities.status_code == 200
    assert capabilities.json()["slideshow"]["audio"] == {
        "schema_version": 1,
        "audio_assets": True,
        "page_narration": False,
        "audio_cues": False,
    }


async def test_external_project_audio_settings_should_reject_invalid_bindings(client: AsyncClient) -> None:
    """显式 null、跨空间、非 audio 与重复 key 均返回 422 且不部分落库。"""

    token, workspace_id = await _create_external_actor(
        ["project:read", "project:write", "asset:read", "asset:write", "workspace:read"]
    )
    project = await _create_project(client, token, workspace_id, {})
    project_id = project["id"]

    null_audio = await client.put(
        f"/api/v1/projects/{project_id}/configuration",
        json={"audio_settings": None},
        headers=_headers(token, workspace_id, "audio-null"),
    )
    assert null_audio.status_code == 422

    duplicated = await client.put(
        f"/api/v1/projects/{project_id}/configuration",
        json={"audio_settings": {
            "master_volume_percent": 100,
            "narration_volume_percent": 100,
            "effects_volume_percent": 30,
            "cue_bindings": [
                {"key": "interaction.confirm", "asset_id": 1, "gain_percent": 100},
                {"key": "interaction.confirm", "asset_id": 2, "gain_percent": 100},
            ],
        }},
        headers=_headers(token, workspace_id, "audio-duplicate"),
    )
    assert duplicated.status_code == 422

    image = await _upload_image(client, token, workspace_id)
    non_audio = await client.put(
        f"/api/v1/projects/{project_id}/configuration",
        json={"audio_settings": {
            "master_volume_percent": 100,
            "narration_volume_percent": 100,
            "effects_volume_percent": 30,
            "cue_bindings": [
                {"key": "interaction.confirm", "asset_id": image["id"], "gain_percent": 100},
            ],
        }},
        headers=_headers(token, workspace_id, "audio-non-audio"),
    )
    assert non_audio.status_code == 422
    assert non_audio.json()["code"] == "PROJECT_AUDIO_CUE_ASSET_INVALID"

    other_token, other_workspace = await _create_external_actor(["asset:read", "asset:write", "workspace:read"])
    foreign = await _upload_audio(client, other_token, other_workspace, name="foreign", payload=b"foreign-audio")
    cross_space = await client.put(
        f"/api/v1/projects/{project_id}/configuration",
        json={"audio_settings": {
            "master_volume_percent": 100,
            "narration_volume_percent": 100,
            "effects_volume_percent": 30,
            "cue_bindings": [
                {"key": "interaction.confirm", "asset_id": foreign["id"], "gain_percent": 100},
            ],
        }},
        headers=_headers(token, workspace_id, "audio-cross-space"),
    )
    assert cross_space.status_code == 422
    assert cross_space.json()["code"] == "PROJECT_AUDIO_CUE_ASSET_INVALID"

    unchanged = await client.get(
        f"/api/v1/projects/{project_id}/configuration",
        headers=_headers(token, workspace_id),
    )
    assert unchanged.json()["audio_settings"]["cue_bindings"] == []

    invalid_gain = await client.put(
        f"/api/v1/projects/{project_id}/configuration",
        json={"audio_settings": {
            "master_volume_percent": 100,
            "narration_volume_percent": 100,
            "effects_volume_percent": 30,
            "cue_bindings": [
                {"key": "interaction.confirm", "asset_id": image["id"], "gain_percent": 101},
            ],
        }},
        headers=_headers(token, workspace_id, "audio-gain"),
    )
    assert invalid_gain.status_code == 422


async def test_external_project_audio_cues_clear_should_keep_volumes_and_replay(client: AsyncClient) -> None:
    """原子清空只删除 cue 绑定，保留音量并支持同键重放。"""

    token, workspace_id = await _create_external_actor(
        ["project:read", "project:write", "asset:read", "asset:write", "workspace:read"]
    )
    asset = await _upload_audio(client, token, workspace_id, name="clear-cue", payload=b"clear-audio")
    project = await _create_project(client, token, workspace_id, {
        "audio_settings": {
            "master_volume_percent": 76,
            "narration_volume_percent": 88,
            "effects_volume_percent": 42,
            "cue_bindings": [
                {"key": "transition.forward", "asset_id": asset["id"], "gain_percent": 70},
                {"key": "interaction.confirm", "asset_id": asset["id"], "gain_percent": 90},
            ],
        },
    })
    project_id = project["id"]

    missing_key = await client.post(
        f"/api/v1/projects/{project_id}/audio-cues/clear",
        headers=_headers(token, workspace_id),
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"

    cleared = await client.post(
        f"/api/v1/projects/{project_id}/audio-cues/clear",
        headers=_headers(token, workspace_id, "audio-cues-clear"),
    )
    assert cleared.status_code == 200, cleared.text
    body = cleared.json()
    assert body["audio_settings"] == {
        "master_volume_percent": 76,
        "narration_volume_percent": 88,
        "effects_volume_percent": 42,
        "cue_bindings": [],
    }

    replay = await client.post(
        f"/api/v1/projects/{project_id}/audio-cues/clear",
        headers=_headers(token, workspace_id, "audio-cues-clear"),
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["audio_settings"] == body["audio_settings"]

    # 清空后仍可独立更新音量，且不会被 clear 回滚。
    updated = await client.put(
        f"/api/v1/projects/{project_id}/configuration",
        json={"audio_settings": {
            "master_volume_percent": 55,
            "narration_volume_percent": 88,
            "effects_volume_percent": 42,
            "cue_bindings": [],
        }},
        headers=_headers(token, workspace_id, "audio-volume-after-clear"),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["audio_settings"]["master_volume_percent"] == 55


async def test_external_project_audio_cues_clear_should_enforce_scope_and_workspace(client: AsyncClient) -> None:
    """清空接口遵守 project:write 与工作空间隔离，越权时不泄露项目身份。"""

    owner_token, workspace_id = await _create_external_actor(
        ["project:read", "project:write", "workspace:read"]
    )
    project = await _create_project(client, owner_token, workspace_id, {})
    project_id = project["id"]

    read_token, _ = await _create_external_actor(["project:read", "workspace:read"])
    forbidden = await client.post(
        f"/api/v1/projects/{project_id}/audio-cues/clear",
        headers=_headers(read_token, workspace_id, "audio-clear-readonly"),
    )
    assert forbidden.status_code == 403

    foreign_token, foreign_workspace = await _create_external_actor(
        ["project:read", "project:write", "workspace:read"]
    )
    foreign = await client.post(
        f"/api/v1/projects/{project_id}/audio-cues/clear",
        headers=_headers(foreign_token, foreign_workspace, "audio-clear-foreign"),
    )
    # PAT 未授权目标工作空间时在项目读取阶段即被拒绝，不泄露项目是否存在。
    assert foreign.status_code in {403, 404}
