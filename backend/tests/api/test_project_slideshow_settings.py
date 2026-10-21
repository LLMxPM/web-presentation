"""文件功能：验证项目放映配置的创建默认值、完整替换、非法请求与样式隔离。"""

from __future__ import annotations

from httpx import AsyncClient

DEFAULT_SLIDESHOW = {
    "transition": {"effect": "fade", "duration_ms": 400},
    "advance": {"mode": "manual", "delay_ms": 5000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
    "loop": False,
    "auto_start": False,
}

TIMER_SLIDESHOW = {
    "transition": {"effect": "push", "duration_ms": 800},
    "advance": {"mode": "timer", "delay_ms": 9000, "media_timeout_ms": 450000, "timeline_timeout_ms": 300000},
    "loop": True,
    "auto_start": True,
}


async def _create_workspace(client: AsyncClient, name: str) -> int:
    """创建工作空间并返回 ID。"""

    response = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200
    return response.json()["id"]


async def _create_project(client: AsyncClient, workspace_id: int, name: str, **extra: object) -> dict:
    """在指定工作空间下创建项目，返回响应 JSON。"""

    response = await client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": "active", **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_project_create_should_default_slideshow_and_read_back(authenticated_client: AsyncClient) -> None:
    """创建省略 slideshow 时返回后端默认完整值，并在详情中保持一致。"""

    workspace_id = await _create_workspace(authenticated_client, "放映默认空间")
    project = await _create_project(authenticated_client, workspace_id, "放映默认项目")

    assert project["slideshow"] == DEFAULT_SLIDESHOW

    detail = await authenticated_client.get(f"/api/projects/{project['id']}")
    assert detail.status_code == 200
    assert detail.json()["slideshow"] == DEFAULT_SLIDESHOW


async def test_project_create_should_accept_complete_slideshow(authenticated_client: AsyncClient) -> None:
    """创建时提供完整对象应按提交值保存，不做字段补全。"""

    workspace_id = await _create_workspace(authenticated_client, "放映创建空间")
    project = await _create_project(
        authenticated_client,
        workspace_id,
        "放映创建项目",
        slideshow=TIMER_SLIDESHOW,
    )

    assert project["slideshow"] == TIMER_SLIDESHOW


async def test_project_create_should_accept_media_end_advance(authenticated_client: AsyncClient) -> None:
    """能力开放后 media_end 可写入，省略超时补默认值，显式超时按提交值保存。"""

    workspace_id = await _create_workspace(authenticated_client, "媒体放映空间")
    default_timeout = await _create_project(
        authenticated_client,
        workspace_id,
        "媒体默认超时",
        slideshow={
            "transition": {"effect": "none", "duration_ms": 0},
            "advance": {"mode": "media_end", "delay_ms": 5000},
            "loop": False,
            "auto_start": False,
        },
    )
    assert default_timeout["slideshow"]["advance"] == {
        "mode": "media_end",
        "delay_ms": 5000,
        "media_timeout_ms": 300000,
        "timeline_timeout_ms": 300000,
    }

    explicit_timeout = await _create_project(
        authenticated_client,
        workspace_id,
        "媒体显式超时",
        slideshow={
            "transition": {"effect": "fade", "duration_ms": 400},
            "advance": {"mode": "media_end", "delay_ms": 6000, "media_timeout_ms": 120000, "timeline_timeout_ms": 300000},
            "loop": True,
            "auto_start": True,
        },
    )
    assert explicit_timeout["slideshow"]["advance"] == {
        "mode": "media_end",
        "delay_ms": 6000,
        "media_timeout_ms": 120000,
        "timeline_timeout_ms": 300000,
    }


async def test_project_patch_should_preserve_or_replace_slideshow(authenticated_client: AsyncClient) -> None:
    """PATCH 省略放映配置时保留原值，提供完整对象时整体替换。"""

    workspace_id = await _create_workspace(authenticated_client, "放映更新空间")
    project = await _create_project(authenticated_client, workspace_id, "放映更新项目", slideshow=TIMER_SLIDESHOW)

    rename = await authenticated_client.patch(f"/api/projects/{project['id']}", json={"name": "放映更新项目-改"})
    assert rename.status_code == 200, rename.text
    assert rename.json()["slideshow"] == TIMER_SLIDESHOW

    replace = await authenticated_client.patch(
        f"/api/projects/{project['id']}",
        json={"slideshow": DEFAULT_SLIDESHOW},
    )
    assert replace.status_code == 200, replace.text
    assert replace.json()["slideshow"] == DEFAULT_SLIDESHOW

    detail = await authenticated_client.get(f"/api/projects/{project['id']}")
    assert detail.json()["slideshow"] == DEFAULT_SLIDESHOW


async def test_project_patch_should_reject_null_or_partial_slideshow(authenticated_client: AsyncClient) -> None:
    """顶层 null 与缺字段对象都必须 422，不能静默补全。"""

    workspace_id = await _create_workspace(authenticated_client, "放映拒绝空间")
    project = await _create_project(authenticated_client, workspace_id, "放映拒绝项目")

    null_response = await authenticated_client.patch(
        f"/api/projects/{project['id']}",
        json={"slideshow": None},
    )
    assert null_response.status_code == 422

    partial_response = await authenticated_client.patch(
        f"/api/projects/{project['id']}",
        json={"slideshow": {"transition": {"effect": "push", "duration_ms": 600}}},
    )
    assert partial_response.status_code == 422

    detail = await authenticated_client.get(f"/api/projects/{project['id']}")
    assert detail.json()["slideshow"] == DEFAULT_SLIDESHOW


async def test_project_slideshow_should_reject_invalid_numbers_on_create(authenticated_client: AsyncClient) -> None:
    """字符串数字、越界停留时间和未知字段都不能写入项目。"""

    workspace_id = await _create_workspace(authenticated_client, "放映非法空间")

    invalid_cases = [
        {
            "transition": {"effect": "fade", "duration_ms": "400"},
            "advance": {"mode": "manual", "delay_ms": 5000},
            "loop": False,
            "auto_start": False,
        },
        {
            "transition": {"effect": "fade", "duration_ms": 400},
            "advance": {"mode": "timer", "delay_ms": 500},
            "loop": False,
            "auto_start": False,
        },
        {
            "transition": {"effect": "wipe", "duration_ms": 400},
            "advance": {"mode": "manual", "delay_ms": 5000},
            "loop": False,
            "auto_start": False,
        },
        {
            "transition": {"effect": "fade", "duration_ms": 400},
            "advance": {"mode": "manual", "delay_ms": 5000, "media_timeout_ms": 999, "timeline_timeout_ms": 300000},
            "loop": False,
            "auto_start": False,
        },
    ]
    for payload in invalid_cases:
        response = await authenticated_client.post(
            "/api/projects",
            json={
                "workspace_id": workspace_id,
                "name": "放映非法项目",
                "status": "active",
                "slideshow": payload,
            },
        )
        assert response.status_code == 422, response.text


async def test_applying_workspace_style_should_not_change_slideshow(authenticated_client: AsyncClient) -> None:
    """应用样式只覆盖展示配置，不得隐式改写项目放映设置。"""

    workspace_id = await _create_workspace(authenticated_client, "放映样式空间")
    project = await _create_project(authenticated_client, workspace_id, "放映样式项目", slideshow=TIMER_SLIDESHOW)

    style_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/styles",
        json={
            "key": "slideshow-style",
            "name": "放映隔离样式",
            "configuration": {"presentation": {"page_width": 1600, "page_height": 900}},
        },
    )
    assert style_response.status_code == 200, style_response.text
    style_id = style_response.json()["id"]

    applied = await authenticated_client.patch(
        f"/api/projects/{project['id']}",
        json={"configuration": {"mode": "style", "style_id": style_id}},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["page_width"] == 1600
    assert applied.json()["slideshow"] == TIMER_SLIDESHOW
