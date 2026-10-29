"""文件功能：验证项目音量的默认值、完整替换、cue 资源校验与原子失败语义。"""

from __future__ import annotations

from httpx import AsyncClient

DEFAULT_AUDIO = {
    "master_volume_percent": 100,
    "narration_volume_percent": 100,
    "effects_volume_percent": 30,
    "cue_bindings": [],
}


async def _create_workspace(client: AsyncClient, name: str) -> int:
    """创建工作空间并返回 ID。"""

    response = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _create_project(client: AsyncClient, workspace_id: int, name: str, **extra: object) -> dict:
    """创建项目并返回响应对象。"""

    response = await client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": "active", **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _upload_audio(client: AsyncClient, workspace_id: int, name: str) -> dict:
    """上传最小音频资源并返回响应对象。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (f"{name}.mp3", b"audio-contract-bytes", "audio/mpeg")},
        data={"asset_type": "audio", "tags": "[]", "name": name},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _create_image(client: AsyncClient, workspace_id: int, name: str) -> dict:
    """创建 SVG 图片资源，用于非 audio 绑定反例。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "image",
            "name": name,
            "original_name": f"{name}.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16"/></svg>',
            "tags": [],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _audio_settings(bindings: list[dict], **volumes: int) -> dict:
    """构造完整的项目音频设置载荷。"""

    return {
        "master_volume_percent": volumes.get("master", 80),
        "narration_volume_percent": volumes.get("narration", 90),
        "effects_volume_percent": volumes.get("effects", 40),
        "cue_bindings": bindings,
    }


def _normalized(settings: dict) -> dict:
    """API 按 cue key 稳定排序返回绑定，比较时不依赖请求顺序。"""

    return {
        **settings,
        "cue_bindings": sorted(settings["cue_bindings"], key=lambda item: item["key"]),
    }


async def test_project_audio_settings_should_default_and_roundtrip(
    authenticated_client: AsyncClient,
    open_audio_capabilities: None,
) -> None:
    """省略音频设置时返回默认音量；完整创建、替换与清空都按提交值保存。"""

    workspace_id = await _create_workspace(authenticated_client, "项目音频空间")
    forward = await _upload_audio(authenticated_client, workspace_id, "whoosh")
    confirm = await _upload_audio(authenticated_client, workspace_id, "confirm")
    bindings = [
        {"key": "transition.forward", "asset_id": forward["id"], "gain_percent": 100},
        {"key": "interaction.confirm", "asset_id": confirm["id"], "gain_percent": 75},
    ]
    project = await _create_project(
        authenticated_client,
        workspace_id,
        "项目音频",
        audio_settings=_audio_settings(bindings),
    )

    expected = _normalized(_audio_settings(bindings))
    assert project["audio_settings"] == expected
    detail = await authenticated_client.get(f"/api/projects/{project['id']}")
    assert detail.json()["audio_settings"] == expected

    renamed = await authenticated_client.patch(
        f"/api/projects/{project['id']}",
        json={"name": "项目音频-改"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["audio_settings"] == expected

    cleared = await authenticated_client.patch(
        f"/api/projects/{project['id']}",
        json={"audio_settings": _audio_settings([], master=60)},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["audio_settings"] == _normalized(_audio_settings([], master=60))
    assert cleared.json()["audio_settings"]["cue_bindings"] == []
    assert cleared.json()["audio_settings"]["master_volume_percent"] == 60


async def test_project_audio_settings_should_reject_null_partial_and_duplicate(
    authenticated_client: AsyncClient,
    open_audio_capabilities: None,
) -> None:
    """顶层 null、缺字段、重复 cue 与非法 key/gain 均返回 422。"""

    workspace_id = await _create_workspace(authenticated_client, "项目音频拒绝空间")
    audio = await _upload_audio(authenticated_client, workspace_id, "reject-audio")
    project = await _create_project(authenticated_client, workspace_id, "项目音频拒绝")

    cases = [
        {"audio_settings": None},
        {"audio_settings": {"master_volume_percent": 50}},
        {"audio_settings": _audio_settings([
            {"key": "transition.forward", "asset_id": audio["id"]},
            {"key": "transition.forward", "asset_id": audio["id"]},
        ])},
        {"audio_settings": _audio_settings([{"key": "unknown.forward", "asset_id": audio["id"]}])},
        {"audio_settings": _audio_settings([{"key": "interaction.confirm", "asset_id": audio["id"], "gain_percent": 101}])},
        {"audio_settings": _audio_settings([{"key": "interaction.confirm", "asset_id": audio["id"], "gain_percent": 50.0}])},
    ]
    for payload in cases:
        response = await authenticated_client.patch(f"/api/projects/{project['id']}", json=payload)
        assert response.status_code == 422, (payload, response.text)

    detail = await authenticated_client.get(f"/api/projects/{project['id']}")
    assert detail.json()["audio_settings"] == DEFAULT_AUDIO


async def test_project_audio_settings_should_reject_invalid_assets_without_partial_write(
    authenticated_client: AsyncClient,
    open_audio_capabilities: None,
) -> None:
    """非 audio、跨空间、归档资源与不存在资源均拒绝，失败不改体积或 cue。"""

    workspace_id = await _create_workspace(authenticated_client, "项目音频资源空间")
    other_workspace_id = await _create_workspace(authenticated_client, "项目音频其它空间")
    audio = await _upload_audio(authenticated_client, workspace_id, "valid-audio")
    foreign_audio = await _upload_audio(authenticated_client, other_workspace_id, "foreign-audio")
    image = await _create_image(authenticated_client, workspace_id, "not-audio")
    archived = await _upload_audio(authenticated_client, workspace_id, "archived-audio")
    archive_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{archived['id']}/archive",
        json={"archive_reason": "测试归档"},
    )
    assert archive_response.status_code == 200, archive_response.text

    project = await _create_project(
        authenticated_client,
        workspace_id,
        "项目音频资源拒绝",
        audio_settings=_audio_settings(
            [{"key": "interaction.confirm", "asset_id": audio["id"]}],
            master=55,
        ),
    )

    invalid_bindings = [
        {"key": "interaction.confirm", "asset_id": image["id"]},
        {"key": "interaction.confirm", "asset_id": foreign_audio["id"]},
        {"key": "interaction.confirm", "asset_id": archived["id"]},
        {"key": "interaction.confirm", "asset_id": 999999},
    ]
    for binding in invalid_bindings:
        response = await authenticated_client.patch(
            f"/api/projects/{project['id']}",
            json={"audio_settings": _audio_settings([binding], master=10)},
        )
        assert response.status_code == 422, (binding, response.text)
        assert response.json()["code"] == "PROJECT_AUDIO_CUE_ASSET_INVALID"

    detail = await authenticated_client.get(f"/api/projects/{project['id']}")
    settings = detail.json()["audio_settings"]
    assert settings["master_volume_percent"] == 55
    assert settings["cue_bindings"] == [{"key": "interaction.confirm", "asset_id": audio["id"], "gain_percent": 100}]


async def test_project_workspace_move_should_clear_cue_bindings(
    authenticated_client: AsyncClient,
    open_audio_capabilities: None,
) -> None:
    """项目迁移工作空间时旧 cue 必须断开，避免跨空间资源引用。"""

    source_id = await _create_workspace(authenticated_client, "项目音频迁移源")
    target_id = await _create_workspace(authenticated_client, "项目音频迁移目标")
    audio = await _upload_audio(authenticated_client, source_id, "move-audio")
    project = await _create_project(
        authenticated_client,
        source_id,
        "项目音频迁移",
        audio_settings=_audio_settings([{"key": "transition.backward", "asset_id": audio["id"]}]),
    )

    moved = await authenticated_client.patch(
        f"/api/projects/{project['id']}",
        json={"workspace_id": target_id},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["workspace_id"] == target_id
    assert moved.json()["audio_settings"]["cue_bindings"] == []


async def test_project_audio_settings_should_reject_cues_when_capability_closed(
    authenticated_client: AsyncClient,
    closed_audio_capabilities: None,
) -> None:
    """audio_cues 关闭时拒绝非空绑定，但允许只更新音量与空 cue。"""

    workspace_id = await _create_workspace(authenticated_client, "项目音频关闭空间")
    audio = await _upload_audio(authenticated_client, workspace_id, "closed-cue")
    project = await _create_project(authenticated_client, workspace_id, "项目音频关闭")
    bindings = [{"key": "interaction.confirm", "asset_id": audio["id"], "gain_percent": 100}]

    created = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "项目音频关闭-创建",
            "status": "active",
            "audio_settings": _audio_settings(bindings),
        },
    )
    assert created.status_code == 422, created.text
    assert created.json()["code"] == "AUDIO_CAPABILITY_UNAVAILABLE"

    rejected_update = await authenticated_client.patch(
        f"/api/projects/{project['id']}",
        json={"audio_settings": _audio_settings(bindings)},
    )
    assert rejected_update.status_code == 422, rejected_update.text
    assert rejected_update.json()["code"] == "AUDIO_CAPABILITY_UNAVAILABLE"

    unchanged = await authenticated_client.get(f"/api/projects/{project['id']}")
    assert unchanged.json()["audio_settings"]["cue_bindings"] == []

    volume_only = await authenticated_client.patch(
        f"/api/projects/{project['id']}",
        json={"audio_settings": _audio_settings([], master=45)},
    )
    assert volume_only.status_code == 200, volume_only.text
    assert volume_only.json()["audio_settings"]["master_volume_percent"] == 45
