"""文件功能：验证项目模板包 schema 3 携带放映配置、1/2/3 兼容导入与导出导入再导出等价。"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any, Callable

from httpx import AsyncClient

PROJECT_SLIDESHOW = {
    "transition": {"effect": "push", "duration_ms": 800},
    "advance": {"mode": "timer", "delay_ms": 6500, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
    "loop": True,
    "auto_start": False,
}

DEFAULT_SLIDESHOW = {
    "transition": {"effect": "fade", "duration_ms": 400},
    "advance": {"mode": "manual", "delay_ms": 5000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
    "loop": False,
    "auto_start": False,
}


async def _create_workspace(client: AsyncClient, name: str) -> int:
    """创建工作空间并返回主键。"""

    response = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _create_source_project(client: AsyncClient, workspace_id: int) -> int:
    """创建带放映配置、两级路由与逐页覆盖的源项目。"""

    project_response = await client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "放映模板项目",
            "status": "active",
            "slideshow": PROJECT_SLIDESHOW,
        },
    )
    assert project_response.status_code == 200, project_response.text
    project_id = project_response.json()["id"]

    page_ids: list[int] = []
    for title in ("模板封面", "模板章节"):
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

    route_response = await client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "cover",
                    "order": 0,
                    "page_id": page_ids[0],
                    "transition": {"effect": "none", "duration_ms": 0},
                    "advance": {"mode": "manual", "delay_ms": 2000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
                },
                {
                    "route_type": "group",
                    "route": "chapter",
                    "order": 1,
                    "group_title": "章节",
                    "children": [
                        {
                            "route": "intro",
                            "order": 0,
                            "page_id": page_ids[1],
                            "advance": {"mode": "timer", "delay_ms": 12000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
                        }
                    ],
                },
            ]
        },
    )
    assert route_response.status_code == 200, route_response.text
    return project_id


async def _export_package(client: AsyncClient, project_id: int) -> bytes:
    """导出项目模板包并返回 ZIP 字节。"""

    response = await client.post(
        f"/api/projects/{project_id}/template-package/export",
        json={"metadata": {"slug": "slideshow-demo", "name": "放映模板"}, "refresh_screenshots": False},
    )
    assert response.status_code == 200, response.text
    return response.content


async def _import_package(client: AsyncClient, workspace_id: int, archive_content: bytes) -> dict[str, Any]:
    """导入模板包并返回导入结果。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/template-packages/import",
        files={"archive": ("project-template.zip", archive_content, "application/zip")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _rewrite_zip_json(archive_content: bytes, target_name: str, rewrite: Callable[[Any], Any]) -> bytes:
    """重写 ZIP 内指定 JSON 文件，保留其它条目不变。"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(archive_content)) as source_archive:
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target_archive:
            for item in source_archive.infolist():
                content = source_archive.read(item.filename)
                if item.filename == target_name:
                    payload = json.loads(content.decode("utf-8"))
                    content = json.dumps(rewrite(payload), ensure_ascii=False).encode("utf-8")
                target_archive.writestr(item, content)
    return buffer.getvalue()


async def test_template_package_schema3_should_roundtrip_slideshow_and_route_overrides(
    authenticated_client: AsyncClient,
) -> None:
    """schema 3 模板包导出导入后保留项目默认与路由原始覆盖，并再次导出等价。"""

    source_workspace_id = await _create_workspace(authenticated_client, "放映模板源空间")
    target_workspace_id = await _create_workspace(authenticated_client, "放映模板目标空间")
    project_id = await _create_source_project(authenticated_client, source_workspace_id)
    archive_content = await _export_package(authenticated_client, project_id)

    with zipfile.ZipFile(io.BytesIO(archive_content)) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["schema_version"] == 4
        project_payload = json.loads(archive.read("project/project.json").decode("utf-8"))
        assert project_payload["slideshow"] == PROJECT_SLIDESHOW
        routes_payload = json.loads(archive.read("project/routes.json").decode("utf-8"))

    routes_by_name = {item["route"]: item for item in routes_payload["routes"]}
    assert routes_by_name["cover"]["transition"] == {"effect": "none", "duration_ms": 0}
    assert routes_by_name["cover"]["advance"] == {"mode": "manual", "delay_ms": 2000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000}
    assert routes_by_name["chapter"]["children"][0]["advance"] == {"mode": "timer", "delay_ms": 12000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000}
    assert routes_by_name["chapter"]["children"][0]["transition"] is None
    assert "effective_slideshow" not in routes_by_name["cover"]

    imported = await _import_package(authenticated_client, target_workspace_id, archive_content)
    imported_project_id = int(imported["project_id"])

    project_response = await authenticated_client.get(f"/api/projects/{imported_project_id}")
    assert project_response.status_code == 200
    assert project_response.json()["slideshow"] == PROJECT_SLIDESHOW

    tree_response = await authenticated_client.get(f"/api/projects/{imported_project_id}/routes")
    assert tree_response.status_code == 200
    tree = tree_response.json()
    cover = next(item for item in tree["routes"] if item["route"] == "cover")
    chapter = next(item for item in tree["routes"] if item["route"] == "chapter")
    intro = chapter["children"][0]
    assert cover["transition"] == {"effect": "none", "duration_ms": 0}
    assert cover["advance"] == {"mode": "manual", "delay_ms": 2000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000}
    assert intro["transition"] is None
    assert intro["advance"] == {"mode": "timer", "delay_ms": 12000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000}
    assert intro["effective_slideshow"] == {
        "transition": {"effect": "push", "duration_ms": 800},
        "advance": {"mode": "timer", "delay_ms": 12000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
    }

    # 再次导出：项目默认与路由覆盖必须与原包语义等价。
    re_exported = await _export_package(authenticated_client, imported_project_id)
    with zipfile.ZipFile(io.BytesIO(re_exported)) as archive:
        project_payload = json.loads(archive.read("project/project.json").decode("utf-8"))
        routes_payload = json.loads(archive.read("project/routes.json").decode("utf-8"))
    assert project_payload["slideshow"] == PROJECT_SLIDESHOW
    re_routes = {item["route"]: item for item in routes_payload["routes"]}
    assert re_routes["cover"]["transition"] == {"effect": "none", "duration_ms": 0}
    assert re_routes["cover"]["advance"] == {"mode": "manual", "delay_ms": 2000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000}
    assert re_routes["chapter"]["children"][0]["advance"] == {"mode": "timer", "delay_ms": 12000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000}


async def test_legacy_template_package_without_slideshow_should_import_with_defaults(
    authenticated_client: AsyncClient,
) -> None:
    """schema 1/2 旧包缺少 slideshow 时按默认完整值导入，不阻断历史模板。"""

    source_workspace_id = await _create_workspace(authenticated_client, "旧包放映源空间")
    target_workspace_id = await _create_workspace(authenticated_client, "旧包放映目标空间")
    project_id = await _create_source_project(authenticated_client, source_workspace_id)
    archive_content = await _export_package(authenticated_client, project_id)

    for schema_version in (1, 2):
        legacy_archive = _rewrite_zip_json(
            archive_content,
            "manifest.json",
            lambda manifest, version=schema_version: {**manifest, "schema_version": version},
        )
        legacy_archive = _rewrite_zip_json(
            legacy_archive,
            "project/project.json",
            lambda project: {key: value for key, value in project.items() if key != "slideshow"},
        )
        legacy_archive = _rewrite_zip_json(
            legacy_archive,
            "project/routes.json",
            lambda routes: {
                "routes": [
                    {
                        **route,
                        **({"transition": None, "advance": None} if route.get("route_type") != "group" else {}),
                        "children": [
                            {**child, "transition": None, "advance": None}
                            for child in route.get("children", [])
                        ],
                    }
                    for route in routes["routes"]
                ]
            },
        )

        imported = await _import_package(authenticated_client, target_workspace_id, legacy_archive)
        imported_project_id = int(imported["project_id"])
        project_response = await authenticated_client.get(f"/api/projects/{imported_project_id}")
        assert project_response.json()["slideshow"] == DEFAULT_SLIDESHOW

        tree_response = await authenticated_client.get(f"/api/projects/{imported_project_id}/routes")
        tree = tree_response.json()
        cover = next(item for item in tree["routes"] if item["route"] == "cover")
        assert cover["transition"] is None
        assert cover["advance"] is None
        assert cover["effective_slideshow"] == {
            "transition": {"effect": "fade", "duration_ms": 400},
            "advance": {"mode": "manual", "delay_ms": 5000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
        }


async def test_schema3_template_package_without_slideshow_should_be_rejected(
    authenticated_client: AsyncClient,
) -> None:
    """schema 3 新包缺少完整放映配置时预检不通过，导入被拒绝。"""

    source_workspace_id = await _create_workspace(authenticated_client, "缺配置源空间")
    target_workspace_id = await _create_workspace(authenticated_client, "缺配置目标空间")
    project_id = await _create_source_project(authenticated_client, source_workspace_id)
    archive_content = await _export_package(authenticated_client, project_id)

    broken_archive = _rewrite_zip_json(
        archive_content,
        "project/project.json",
        lambda project: {key: value for key, value in project.items() if key != "slideshow"},
    )

    validate_response = await authenticated_client.post(
        f"/api/workspaces/{target_workspace_id}/template-packages/import/validate",
        files={"archive": ("project-template.zip", broken_archive, "application/zip")},
    )
    assert validate_response.status_code == 200
    validation = validate_response.json()
    assert validation["valid"] is False
    assert any("slideshow" in error for error in validation["errors"])

    import_response = await authenticated_client.post(
        f"/api/workspaces/{target_workspace_id}/template-packages/import",
        files={"archive": ("project-template.zip", broken_archive, "application/zip")},
    )
    assert import_response.status_code == 400
    assert import_response.json()["code"] == "PROJECT_TEMPLATE_IMPORT_INVALID"
