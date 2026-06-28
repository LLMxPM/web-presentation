"""文件功能：验证项目建议引用内容资源接口的保存、校验与工作空间迁移行为。"""

from httpx import AsyncClient


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回主键。"""

    response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _create_project(authenticated_client: AsyncClient, workspace_id: int, name: str) -> int:
    """创建测试项目并返回主键。"""

    response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _create_text_asset(
    authenticated_client: AsyncClient,
    workspace_id: int,
    name: str,
    *,
    asset_type: str = "image",
    original_name: str | None = None,
) -> dict:
    """创建文本型资源并返回接口载荷。"""

    file_name = original_name or f"{name}.svg"
    content = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 16 16\"><rect width=\"16\" height=\"16\"/></svg>"
    if asset_type == "mermaid":
        file_name = original_name or f"{name}.mmd"
        content = "flowchart TD\n  A[开始] --> B[结束]"
    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": asset_type,
            "name": name,
            "original_name": file_name,
            "description": f"{name} 描述",
            "content": content,
            "tags": ["测试"],
        },
    )
    assert response.status_code == 200
    return response.json()


async def _upload_font_asset(authenticated_client: AsyncClient, workspace_id: int, name: str) -> dict:
    """上传字体资源并返回接口载荷。"""

    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (f"{name}.woff2", b"fake-font", "font/woff2")},
        data={"asset_type": "font", "tags": "[]", "name": name},
    )
    assert response.status_code == 200
    return response.json()


async def test_project_suggested_reference_assets_should_save_content_assets_in_order(
    authenticated_client: AsyncClient,
) -> None:
    """建议引用资源应只返回精简字段，并按用户选择顺序去重保存。"""

    workspace_id = await _create_workspace(authenticated_client, "建议资源空间")
    project_id = await _create_project(authenticated_client, workspace_id, "建议资源项目")
    hero_asset = await _create_text_asset(authenticated_client, workspace_id, "hero_image")
    flow_asset = await _create_text_asset(authenticated_client, workspace_id, "process_flow", asset_type="mermaid")

    save_response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-reference-assets",
        json={"asset_ids": [flow_asset["id"], hero_asset["id"], flow_asset["id"]]},
    )

    assert save_response.status_code == 200
    items = save_response.json()["items"]
    assert [item["id"] for item in items] == [flow_asset["id"], hero_asset["id"]]
    assert set(items[0]) == {
        "id",
        "name",
        "original_name",
        "description",
        "asset_type",
        "content_editable",
        "approx_aspect_ratio",
        "approx_aspect_ratio_value",
        "aspect_ratio_source",
    }
    assert items[0]["approx_aspect_ratio"] is None
    assert items[0]["approx_aspect_ratio_value"] is None
    assert items[0]["aspect_ratio_source"] is None
    assert items[1]["approx_aspect_ratio"] == "1:1"
    assert items[1]["approx_aspect_ratio_value"] == 1.0
    assert items[1]["aspect_ratio_source"] == "auto"
    assert "url" not in items[0]
    assert "tags" not in items[0]

    get_response = await authenticated_client.get(f"/api/projects/{project_id}/suggested-reference-assets")
    assert get_response.status_code == 200
    assert [item["id"] for item in get_response.json()["items"]] == [flow_asset["id"], hero_asset["id"]]


async def test_project_suggested_reference_assets_should_reject_non_content_or_invalid_assets(
    authenticated_client: AsyncClient,
) -> None:
    """建议引用资源应拒绝图标、字体、归档、历史和跨工作空间资源。"""

    workspace_id = await _create_workspace(authenticated_client, "建议资源校验空间")
    other_workspace_id = await _create_workspace(authenticated_client, "其他建议资源空间")
    project_id = await _create_project(authenticated_client, workspace_id, "建议资源校验项目")
    image_asset = await _create_text_asset(authenticated_client, workspace_id, "valid_image")
    history_source_asset = await _create_text_asset(authenticated_client, workspace_id, "history_image")
    icon_asset = await _create_text_asset(authenticated_client, workspace_id, "brand_icon", asset_type="icon")
    font_asset = await _upload_font_asset(authenticated_client, workspace_id, "brand_font")
    other_asset = await _create_text_asset(authenticated_client, other_workspace_id, "other_image")

    for asset in (icon_asset, font_asset, other_asset):
        response = await authenticated_client.put(
            f"/api/projects/{project_id}/suggested-reference-assets",
            json={"asset_ids": [asset["id"]]},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "PROJECT_SUGGESTED_ASSET_INVALID"

    archive_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{image_asset['id']}/archive",
        json={"archive_reason": "测试归档"},
    )
    assert archive_response.status_code == 200
    archived_response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-reference-assets",
        json={"asset_ids": [image_asset["id"]]},
    )
    assert archived_response.status_code == 400
    assert archived_response.json()["code"] == "PROJECT_SUGGESTED_ASSET_INVALID"

    update_response = await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/assets/{history_source_asset['id']}/content",
        json={
            "content": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 16 16\"><circle cx=\"8\" cy=\"8\" r=\"4\"/></svg>",
            "change_note": "生成历史",
        },
    )
    assert update_response.status_code == 200
    history_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"history_only": True, "status": "archived"},
    )
    assert history_response.status_code == 200
    history_asset_id = history_response.json()["items"][0]["id"]
    history_save_response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-reference-assets",
        json={"asset_ids": [history_asset_id]},
    )
    assert history_save_response.status_code == 400
    assert history_save_response.json()["code"] == "PROJECT_SUGGESTED_ASSET_INVALID"


async def test_project_suggested_reference_assets_should_clear_when_project_moves_workspace(
    authenticated_client: AsyncClient,
) -> None:
    """项目迁移工作空间时应清空旧工作空间建议引用资源。"""

    workspace_id = await _create_workspace(authenticated_client, "迁移前空间")
    target_workspace_id = await _create_workspace(authenticated_client, "迁移后空间")
    project_id = await _create_project(authenticated_client, workspace_id, "迁移建议资源项目")
    image_asset = await _create_text_asset(authenticated_client, workspace_id, "move_image")

    save_response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-reference-assets",
        json={"asset_ids": [image_asset["id"]]},
    )
    assert save_response.status_code == 200
    assert len(save_response.json()["items"]) == 1

    move_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"workspace_id": target_workspace_id},
    )
    assert move_response.status_code == 200

    get_response = await authenticated_client.get(f"/api/projects/{project_id}/suggested-reference-assets")
    assert get_response.status_code == 200
    assert get_response.json()["items"] == []
