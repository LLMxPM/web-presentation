"""文件功能：验证项目预览 artifact 固化放映配置、逐页生效值下发及旧快照不随项目配置变化。"""

from __future__ import annotations

from httpx import AsyncClient

INITIAL_SLIDESHOW = {
    "transition": {"effect": "fade", "duration_ms": 400},
    "advance": {"mode": "timer", "delay_ms": 5000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
    "loop": True,
    "auto_start": False,
}

UPDATED_SLIDESHOW = {
    "transition": {"effect": "none", "duration_ms": 0},
    "advance": {"mode": "manual", "delay_ms": 9000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
    "loop": False,
    "auto_start": True,
}


async def _setup_project(client: AsyncClient) -> tuple[int, int, list[int]]:
    """创建工作空间、带放映配置的项目与两个页面，返回工作空间、项目与页面 ID。"""

    workspace_response = await client.post("/api/workspaces", json={"name": "预览放映空间", "status": "active"})
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "预览放映项目",
            "status": "active",
            "slideshow": INITIAL_SLIDESHOW,
        },
    )
    assert project_response.status_code == 200, project_response.text
    project_id = project_response.json()["id"]

    page_ids: list[int] = []
    for title in ("预览首页", "预览次页"):
        page_response = await client.post(
            "/api/pages",
            json={
                "workspace_id": workspace_id,
                "project_id": project_id,
                "title": title,
                "page_content": f"<template><div>{title}</div></template>",
                "file_type": "vue",
                "status": "active",
            },
        )
        assert page_response.status_code == 200, page_response.text
        page_ids.append(page_response.json()["id"])

    routes_response = await client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page_ids[0],
                    "transition": {"effect": "push", "duration_ms": 700},
                },
                {
                    "route_type": "page",
                    "route": "second",
                    "order": 1,
                    "page_id": page_ids[1],
                },
            ]
        },
    )
    assert routes_response.status_code == 200, routes_response.text
    return workspace_id, project_id, page_ids


async def _create_preview(client: AsyncClient, project_id: int) -> str:
    """创建整项目预览 artifact 并返回 artifact_id。"""

    response = await client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["artifact_id"])


async def _read_config_bundle(client: AsyncClient, artifact_id: str, runtime_service_headers) -> dict:
    """读取预览 artifact 的 Runtime 配置包。"""

    response = await client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers(artifact_id),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_preview_artifact_should_freeze_slideshow_defaults_and_effective_routes(
    authenticated_client: AsyncClient,
    runtime_service_headers,
) -> None:
    """预览配置包应包含项目默认值、playback 与每个叶子页的生效放映参数。"""

    _, project_id, _ = await _setup_project(authenticated_client)
    artifact_id = await _create_preview(authenticated_client, project_id)
    bundle = await _read_config_bundle(authenticated_client, artifact_id, runtime_service_headers)

    routes_bundle = bundle["routes"]
    assert routes_bundle["transitionDefaults"] == {"effect": "fade", "durationMs": 400}
    assert routes_bundle["playback"] == {
        "autoStart": False,
        "loop": True,
        "advanceDefaults": {"mode": "timer", "delayMs": 5000, "mediaTimeoutMs": 300000, "timelineTimeoutMs": 300000},
    }

    routes = {item["route"]: item for item in routes_bundle["routes"]}
    assert routes["home"]["meta"]["transition"] == {"effect": "push", "durationMs": 700}
    assert routes["home"]["meta"]["advance"] == {"mode": "timer", "delayMs": 5000, "mediaTimeoutMs": 300000, "timelineTimeoutMs": 300000}
    assert routes["second"]["meta"]["transition"] == {"effect": "fade", "durationMs": 400}
    assert routes["second"]["meta"]["advance"] == {"mode": "timer", "delayMs": 5000, "mediaTimeoutMs": 300000, "timelineTimeoutMs": 300000}


async def _upload_audio(client: AsyncClient, workspace_id: int, name: str) -> int:
    """上传最小音频并返回资源 ID。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (f"{name}.mp3", b"audio-contract-bytes", "audio/mpeg")},
        data={"asset_type": "audio", "tags": "[]", "name": name},
    )
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


async def test_preview_artifact_should_freeze_audio_volume_and_cues(
    authenticated_client: AsyncClient,
    runtime_service_headers,
    open_audio_capabilities: None,
) -> None:
    """预览配置包固化音量与 cue 逻辑名，项目更新后旧 artifact 不热读。"""

    workspace_id, project_id, _ = await _setup_project(authenticated_client)
    audio_id = await _upload_audio(authenticated_client, workspace_id, "whoosh")
    initial_settings = {
        "master_volume_percent": 80,
        "narration_volume_percent": 90,
        "effects_volume_percent": 40,
        "cue_bindings": [{"key": "transition.forward", "asset_id": audio_id, "gain_percent": 100}],
    }
    update = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"audio_settings": initial_settings},
    )
    assert update.status_code == 200, update.text

    old_artifact_id = await _create_preview(authenticated_client, project_id)
    old_bundle = await _read_config_bundle(authenticated_client, old_artifact_id, runtime_service_headers)
    assert old_bundle["audio"] == {
        "volume": {"master": 0.8, "narration": 0.9, "effects": 0.4},
        "cues": {"transition.forward": {"assetName": "whoosh", "gain": 1.0}},
    }

    replaced = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={
            "audio_settings": {
                "master_volume_percent": 50,
                "narration_volume_percent": 60,
                "effects_volume_percent": 70,
                "cue_bindings": [],
            }
        },
    )
    assert replaced.status_code == 200, replaced.text

    frozen_bundle = await _read_config_bundle(authenticated_client, old_artifact_id, runtime_service_headers)
    assert frozen_bundle["audio"] == old_bundle["audio"]

    new_artifact_id = await _create_preview(authenticated_client, project_id)
    new_bundle = await _read_config_bundle(authenticated_client, new_artifact_id, runtime_service_headers)
    assert new_bundle["audio"] == {
        "volume": {"master": 0.5, "narration": 0.6, "effects": 0.7},
        "cues": {},
    }


async def test_existing_preview_artifact_should_not_hot_read_updated_slideshow(
    authenticated_client: AsyncClient,
    runtime_service_headers,
) -> None:
    """项目放映配置更新后，已创建的预览 artifact 保持原参数，新预览使用新参数。"""

    _, project_id, _ = await _setup_project(authenticated_client)
    old_artifact_id = await _create_preview(authenticated_client, project_id)

    update_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"slideshow": UPDATED_SLIDESHOW},
    )
    assert update_response.status_code == 200, update_response.text

    old_bundle = await _read_config_bundle(authenticated_client, old_artifact_id, runtime_service_headers)
    assert old_bundle["routes"]["transitionDefaults"] == {"effect": "fade", "durationMs": 400}
    assert old_bundle["routes"]["playback"]["advanceDefaults"] == {"mode": "timer", "delayMs": 5000, "mediaTimeoutMs": 300000, "timelineTimeoutMs": 300000}
    old_home = next(item for item in old_bundle["routes"]["routes"] if item["route"] == "home")
    assert old_home["meta"]["transition"] == {"effect": "push", "durationMs": 700}

    new_artifact_id = await _create_preview(authenticated_client, project_id)
    new_bundle = await _read_config_bundle(authenticated_client, new_artifact_id, runtime_service_headers)
    assert new_bundle["routes"]["transitionDefaults"] == {"effect": "none", "durationMs": 0}
    assert new_bundle["routes"]["playback"] == {
        "autoStart": True,
        "loop": False,
        "advanceDefaults": {"mode": "manual", "delayMs": 9000, "mediaTimeoutMs": 300000, "timelineTimeoutMs": 300000},
    }
    new_home = next(item for item in new_bundle["routes"]["routes"] if item["route"] == "home")
    # 路由原始覆盖不因项目默认值变化而重写。
    assert new_home["meta"]["transition"] == {"effect": "push", "durationMs": 700}
    assert new_home["meta"]["advance"] == {"mode": "manual", "delayMs": 9000, "mediaTimeoutMs": 300000, "timelineTimeoutMs": 300000}


async def test_preview_artifact_should_drop_cues_when_capability_closed(
    authenticated_client: AsyncClient,
    runtime_service_headers,
) -> None:
    """能力关闭时新快照不携带 cue；历史绑定只保留在存储中，不进入执行配置。"""

    from app.db.session import get_session_factory
    from app.models.project_audio_cue import ProjectAudioCueBinding

    workspace_id, project_id, _ = await _setup_project(authenticated_client)
    audio_id = await _upload_audio(authenticated_client, workspace_id, "legacy-cue")
    session_factory = get_session_factory()
    async with session_factory() as session:
        session.add(
            ProjectAudioCueBinding(
                project_id=project_id,
                cue_key="transition.forward",
                asset_id=audio_id,
                gain_percent=100,
            )
        )
        await session.commit()

    artifact_id = await _create_preview(authenticated_client, project_id)
    bundle = await _read_config_bundle(authenticated_client, artifact_id, runtime_service_headers)

    assert bundle["audio"]["cues"] == {}
    assert bundle["audio"]["volume"] == {"master": 1.0, "narration": 1.0, "effects": 0.3}
