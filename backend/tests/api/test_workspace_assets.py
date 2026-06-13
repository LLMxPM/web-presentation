"""文件功能：验证工作空间静态资源描述字段的上传、列表、导入导出与更新行为。"""

import io
import json
import zipfile

from httpx import AsyncClient

from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.workspace_theme import WorkspaceTheme
from app.services.project_artifact_builder import ProjectArtifactBuilder


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回主键。"""

    response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def test_asset_upload_should_default_description_to_null(
    authenticated_client: AsyncClient,
) -> None:
    """上传资源未传 description 时，应返回空描述。"""

    workspace_id = await _create_workspace(authenticated_client, "资源描述默认值空间")

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"fake-png", "image/png")},
        data={"asset_type": "image", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    assert upload_response.json()["description"] is None
    assert upload_response.json()["asset_role"] == "content"
    assert upload_response.json()["render_type"] == "image"
    assert upload_response.json()["content_type"] == "image/png"


async def test_video_asset_upload_should_be_manageable_and_manifest_renderable(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """视频资源应支持上传、列表筛选，并在 artifact manifest 中输出 video 渲染类型。"""

    workspace_id = await _create_workspace(authenticated_client, "视频资源空间")

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("demo-video.mp4", b"fake-mp4-video", "video/mp4")},
        data={"asset_type": "video", "tags": '["演示"]', "name": "demo_video"},
    )
    assert upload_response.status_code == 200
    payload = upload_response.json()
    assert payload["asset_type"] == "video"
    assert payload["asset_role"] == "content"
    assert payload["render_type"] == "video"
    assert payload["content_type"] == "video/mp4"
    assert payload["content_editable"] is False

    list_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"asset_type": "video"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["name"] == "demo_video"

    async with get_session_factory()() as session:
        asset_mapping, asset_metadata = await ProjectArtifactBuilder(session).build_workspace_asset_snapshot(workspace_id)
    assert asset_mapping["demo_video"] == payload["file_hash"]
    assert asset_metadata["demo_video"]["render_type"] == "video"

    preview_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{payload['id']}/preview-artifact",
    )
    assert preview_response.status_code == 200

    config_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{preview_response.json()['artifact_id']}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_response.status_code == 200
    asset_preview = config_response.json()["asset_preview"]
    assert asset_preview["name"] == "demo_video"
    assert asset_preview["render_type"] == "video"


async def test_asset_list_should_include_uploaded_description(
    authenticated_client: AsyncClient,
) -> None:
    """上传时传入的描述应能在列表接口中读回。"""

    workspace_id = await _create_workspace(authenticated_client, "资源描述列表空间")

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("poster.png", b"fake-poster", "image/png")},
        data={
            "asset_type": "image",
            "tags": "[]",
            "description": "首页海报插图",
        },
    )
    assert upload_response.status_code == 200
    assert upload_response.json()["description"] == "首页海报插图"

    list_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"asset_type": "image"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["description"] == "首页海报插图"


async def test_asset_list_should_page_keyword_and_tag_filter(
    authenticated_client: AsyncClient,
) -> None:
    """资源列表应按后端分页返回，并支持关键词和标签组合筛选。"""

    workspace_id = await _create_workspace(authenticated_client, "资源分页筛选空间")

    cases = [
        ("hero_alpha", "hero_alpha.svg", "首页 Hero 主视觉 A", ["封面"]),
        ("hero_beta", "hero_beta.svg", "首页 Hero 主视觉 B", ["封面"]),
        ("chart_delta", "chart_delta.svg", "数据图表", ["图表"]),
    ]
    for name, original_name, description, tags in cases:
        response = await authenticated_client.post(
            f"/api/workspaces/{workspace_id}/assets/content",
            json={
                "asset_type": "image",
                "name": name,
                "original_name": original_name,
                "description": description,
                "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16"/></svg>',
                "tags": tags,
            },
        )
        assert response.status_code == 200

    first_page_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={
            "keyword": "Hero",
            "tag": "封面",
            "page": 1,
            "page_size": 1,
            "sort_by": "name",
            "sort_order": "asc",
        },
    )
    assert first_page_response.status_code == 200
    first_page_payload = first_page_response.json()
    assert first_page_payload["total"] == 2
    assert first_page_payload["page"] == 1
    assert first_page_payload["page_size"] == 1
    assert [item["name"] for item in first_page_payload["items"]] == ["hero_alpha"]

    second_page_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={
            "keyword": "Hero",
            "tag": "封面",
            "page": 2,
            "page_size": 1,
            "sort_by": "name",
            "sort_order": "asc",
        },
    )
    assert second_page_response.status_code == 200
    assert [item["name"] for item in second_page_response.json()["items"]] == ["hero_beta"]


async def test_asset_tags_should_filter_by_asset_type(
    authenticated_client: AsyncClient,
) -> None:
    """标签汇总接口应按资源类型返回当前类型可用标签。"""

    workspace_id = await _create_workspace(authenticated_client, "资源标签类型筛选空间")
    cases = [
        ("icon", "brand_icon", "brand_icon.svg", ["品牌", "通用"]),
        ("image", "hero_image", "hero_image.svg", ["封面", "通用"]),
    ]
    for asset_type, name, original_name, tags in cases:
        response = await authenticated_client.post(
            f"/api/workspaces/{workspace_id}/assets/content",
            json={
                "asset_type": asset_type,
                "name": name,
                "original_name": original_name,
                "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16"/></svg>',
                "tags": tags,
            },
        )
        assert response.status_code == 200

    icon_tags_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/tags",
        params={"asset_type": "icon"},
    )
    assert icon_tags_response.status_code == 200
    assert icon_tags_response.json() == ["品牌", "通用"]

    image_tags_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/tags",
        params={"asset_type": "image"},
    )
    assert image_tags_response.status_code == 200
    assert image_tags_response.json() == ["封面", "通用"]


async def test_asset_list_and_tags_should_support_excluding_font_type(
    authenticated_client: AsyncClient,
) -> None:
    """资源管理页全部视图可通过排除字体类型读取非字体资源。"""

    workspace_id = await _create_workspace(authenticated_client, "资源排除字体空间")

    image_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"fake-png", "image/png")},
        data={"asset_type": "image", "tags": '["封面"]'},
    )
    assert image_response.status_code == 200

    font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("brand.woff2", b"fake-font", "font/woff2")},
        data={"asset_type": "font", "tags": '["字体"]'},
    )
    assert font_response.status_code == 200

    list_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"exclude_asset_type": "font"},
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["asset_type"] == "image"

    tags_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/tags",
        params={"exclude_asset_type": "font"},
    )
    assert tags_response.status_code == 200
    assert tags_response.json() == ["封面"]


async def test_asset_tags_should_follow_asset_status_scope(
    authenticated_client: AsyncClient,
) -> None:
    """标签汇总与标签筛选应跟随资源状态范围，避免启用视图展示归档标签。"""

    workspace_id = await _create_workspace(authenticated_client, "资源标签状态范围空间")
    cases = [
        ("active_cover", ["启用标签"]),
        ("archived_cover", ["归档标签"]),
    ]
    created_assets: dict[str, dict] = {}
    for name, tags in cases:
        response = await authenticated_client.post(
            f"/api/workspaces/{workspace_id}/assets/content",
            json={
                "asset_type": "image",
                "name": name,
                "original_name": f"{name}.svg",
                "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16"/></svg>',
                "tags": tags,
            },
        )
        assert response.status_code == 200
        created_assets[name] = response.json()

    archive_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{created_assets['archived_cover']['id']}/archive",
        json={"archive_reason": "测试标签范围"},
    )
    assert archive_response.status_code == 200

    active_tags_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/tags",
        params={"asset_type": "image"},
    )
    assert active_tags_response.status_code == 200
    assert active_tags_response.json() == ["启用标签"]

    archived_tags_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/tags",
        params={"asset_type": "image", "status": "archived"},
    )
    assert archived_tags_response.status_code == 200
    assert archived_tags_response.json() == ["归档标签"]

    active_list_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"asset_type": "image", "tag": "归档标签"},
    )
    assert active_list_response.status_code == 200
    assert active_list_response.json()["total"] == 0

    archived_list_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"asset_type": "image", "status": "archived", "tag": "归档标签"},
    )
    assert archived_list_response.status_code == 200
    assert archived_list_response.json()["total"] == 1
    assert archived_list_response.json()["items"][0]["name"] == "archived_cover"


async def test_asset_update_should_persist_and_normalize_description(
    authenticated_client: AsyncClient,
) -> None:
    """更新资源描述时，应保存非空描述并把空白内容归一化为空值。"""

    workspace_id = await _create_workspace(authenticated_client, "资源描述更新空间")

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("logo.svg", b"<svg><path d='M0 0'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    asset_id = upload_response.json()["id"]

    update_response = await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}",
        json={"description": "  品牌主 Logo，用于页眉与封面。  "},
    )
    assert update_response.status_code == 200
    assert update_response.json()["description"] == "品牌主 Logo，用于页眉与封面。"

    list_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"asset_type": "icon"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["description"] == "品牌主 Logo，用于页眉与封面。"

    clear_response = await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}",
        json={"description": "   "},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["description"] is None


async def test_asset_upload_should_reject_removed_illustration_type(
    authenticated_client: AsyncClient,
) -> None:
    """旧 illustration 类型已移除，上传时应直接被接口拒绝。"""

    workspace_id = await _create_workspace(authenticated_client, "旧插图类型拒绝空间")

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"fake-png", "image/png")},
        data={"asset_type": "illustration", "tags": "[]"},
    )

    assert upload_response.status_code == 422


async def test_asset_upload_same_name_should_require_overwrite_confirmation(
    authenticated_client: AsyncClient,
) -> None:
    """同名资源默认不直接覆盖，应返回明确冲突码供前端提示用户。"""

    workspace_id = await _create_workspace(authenticated_client, "资源同名冲突空间")

    first_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"old-png", "image/png")},
        data={"asset_type": "image", "tags": '["封面"]'},
    )
    assert first_response.status_code == 200

    conflict_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"new-png", "image/png")},
        data={"asset_type": "image", "tags": "[]"},
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["code"] == "ASSET_NAME_CONFLICT"


async def test_asset_upload_same_name_should_overwrite_existing_asset(
    authenticated_client: AsyncClient,
) -> None:
    """确认覆盖后，应复用原资源记录并替换文件内容信息。"""

    workspace_id = await _create_workspace(authenticated_client, "资源同名覆盖空间")

    first_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"old-png", "image/png")},
        data={"asset_type": "image", "tags": '["封面"]', "description": "旧资源描述"},
    )
    assert first_response.status_code == 200
    first_payload = first_response.json()

    overwrite_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"new-png", "image/png")},
        data={"asset_type": "image", "tags": "[]", "overwrite": "true"},
    )
    assert overwrite_response.status_code == 200
    overwrite_payload = overwrite_response.json()
    assert overwrite_payload["id"] == first_payload["id"]
    assert overwrite_payload["name"] == "cover"
    assert overwrite_payload["file_hash"] != first_payload["file_hash"]
    assert overwrite_payload["file_size"] == len(b"new-png")
    assert overwrite_payload["tags"] == ["封面"]
    assert overwrite_payload["description"] == "旧资源描述"

    list_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"asset_type": "image"},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1


async def test_asset_upload_same_original_name_should_overwrite_renamed_asset(
    authenticated_client: AsyncClient,
) -> None:
    """即使资源 name 被改过，同文件名上传也应提示并覆盖原文件资源。"""

    workspace_id = await _create_workspace(authenticated_client, "资源同文件名覆盖空间")

    first_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"old-png", "image/png")},
        data={"asset_type": "image", "tags": '["封面"]'},
    )
    assert first_response.status_code == 200
    asset_id = first_response.json()["id"]

    rename_response = await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}",
        json={"name": "home-cover"},
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["original_name"] == "cover.png"

    conflict_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"new-png", "image/png")},
        data={"asset_type": "image", "tags": "[]"},
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["code"] == "ASSET_NAME_CONFLICT"

    overwrite_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"new-png", "image/png")},
        data={"asset_type": "image", "tags": "[]", "overwrite": "true"},
    )
    assert overwrite_response.status_code == 200
    overwrite_payload = overwrite_response.json()
    assert overwrite_payload["id"] == asset_id
    assert overwrite_payload["name"] == "home-cover"
    assert overwrite_payload["file_size"] == len(b"new-png")

    list_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"asset_type": "image"},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1


async def test_asset_replace_file_should_target_current_asset_by_id(
    authenticated_client: AsyncClient,
) -> None:
    """替换资源文件时，应按资源 ID 更新当前记录并保留逻辑名、标签和描述。"""

    workspace_id = await _create_workspace(authenticated_client, "资源定向替换空间")

    first_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"old-png", "image/png")},
        data={"asset_type": "image", "tags": '["封面"]', "description": "首页封面"},
    )
    assert first_response.status_code == 200
    first_payload = first_response.json()

    other_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("sidebar.png", b"other-png", "image/png")},
        data={"asset_type": "image", "tags": "[]"},
    )
    assert other_response.status_code == 200

    replace_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{first_payload['id']}/replace",
        files={"file": ("cover-v2.webp", b"new-webp", "image/webp")},
    )
    assert replace_response.status_code == 200
    replace_payload = replace_response.json()
    assert replace_payload["id"] == first_payload["id"]
    assert replace_payload["name"] == "cover"
    assert replace_payload["original_name"] == "cover-v2.webp"
    assert replace_payload["file_hash"] != first_payload["file_hash"]
    assert replace_payload["file_size"] == len(b"new-webp")
    assert replace_payload["tags"] == ["封面"]
    assert replace_payload["description"] == "首页封面"

    list_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"asset_type": "image"},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 2


async def test_asset_replace_file_should_reject_wrong_type(
    authenticated_client: AsyncClient,
) -> None:
    """替换文件仍需遵守当前资源类型的扩展名校验。"""

    workspace_id = await _create_workspace(authenticated_client, "资源替换类型校验空间")

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"old-png", "image/png")},
        data={"asset_type": "image", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    asset_id = upload_response.json()["id"]

    replace_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}/replace",
        files={"file": ("font.ttf", b"font-data", "font/ttf")},
    )
    assert replace_response.status_code == 400
    assert replace_response.json()["code"] == "ASSET_FILE_TYPE_UNSUPPORTED"


async def test_asset_content_write_should_create_history_snapshot(authenticated_client: AsyncClient) -> None:
    """文本资源写入前应自动生成 archived 历史副本，并且默认列表不展示历史副本。"""

    workspace_id = await _create_workspace(authenticated_client, "资源内容历史空间")
    create_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "icon",
            "name": "brand_icon",
            "original_name": "brand_icon.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M1 1"/></svg>',
            "tags": ["品牌"],
        },
    )
    assert create_response.status_code == 200
    asset_id = create_response.json()["id"]

    update_response = await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}/content",
        json={
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2"/></svg>',
            "change_note": "测试写入",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["file_hash"] != create_response.json()["file_hash"]

    active_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"asset_type": "icon"},
    )
    assert active_response.status_code == 200
    assert [item["id"] for item in active_response.json()["items"]] == [asset_id]

    history_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"status": "archived", "include_history": "true"},
    )
    assert history_response.status_code == 200
    history_items = [item for item in history_response.json()["items"] if item["source_asset_id"] == asset_id]
    assert len(history_items) == 1
    assert history_items[0]["history_kind"] == "write_snapshot"

    history_content_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/{history_items[0]['id']}/content",
    )
    assert history_content_response.status_code == 200
    assert "M1 1" in history_content_response.json()["content"]


async def test_svg_image_content_should_be_editable_and_keep_image_render_type(
    authenticated_client: AsyncClient,
) -> None:
    """SVG 图片应作为 image 内容资源创建和写回，不进入图标分析链路。"""

    workspace_id = await _create_workspace(authenticated_client, "SVG 图片内容空间")
    create_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "image",
            "name": "hero_illustration",
            "original_name": "hero_illustration.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540"><rect width="960" height="540" fill="#eef2ff"/></svg>',
            "description": "封面主视觉插画",
            "tags": ["封面", "插画"],
        },
    )
    assert create_response.status_code == 200
    created_payload = create_response.json()
    asset_id = created_payload["id"]
    assert created_payload["asset_type"] == "image"
    assert created_payload["asset_role"] == "content"
    assert created_payload["render_type"] == "image"
    assert created_payload["content_type"] == "image/svg+xml"
    assert created_payload["content_editable"] is True
    assert created_payload["analysis_metadata"] is None

    content_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}/content",
    )
    assert content_response.status_code == 200
    assert "eef2ff" in content_response.json()["content"]

    next_content = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540"><rect width="960" height="540" fill="#f8fafc"/></svg>'
    preview_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}/content/preview",
        json={"content": next_content},
    )
    assert preview_response.status_code == 200
    assert preview_response.json()["changed"] is True
    assert "eef2ff" in preview_response.json()["unified_diff"]
    assert "f8fafc" in preview_response.json()["unified_diff"]

    update_response = await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}/content",
        json={"content": next_content, "change_note": "更新 SVG 图片"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["render_type"] == "image"
    assert update_response.json()["file_hash"] != created_payload["file_hash"]

    history_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"status": "archived", "include_history": "true"},
    )
    assert history_response.status_code == 200
    history_items = [item for item in history_response.json()["items"] if item["source_asset_id"] == asset_id]
    assert len(history_items) == 1
    assert history_items[0]["asset_type"] == "image"
    assert history_items[0]["render_type"] == "image"


async def test_asset_preview_artifact_should_expose_runtime_asset_config(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """文本资源、SVG 图片和 SVG 图标应能创建 Runtime 资源预览 artifact。"""

    workspace_id = await _create_workspace(authenticated_client, "资源预览空间")
    cases = [
        {
            "asset_type": "icon",
            "name": "preview_icon",
            "original_name": "preview_icon.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M1 1"/></svg>',
        },
        {
            "asset_type": "image",
            "name": "preview_illustration",
            "original_name": "preview_illustration.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540"><rect width="960" height="540"/></svg>',
        },
        {
            "asset_type": "mermaid",
            "name": "preview_flow",
            "original_name": "preview_flow.mmd",
            "content": "flowchart TD\n  A[开始] --> B[结束]",
        },
    ]

    for item in cases:
        create_response = await authenticated_client.post(
            f"/api/workspaces/{workspace_id}/assets/content",
            json={**item, "tags": []},
        )
        assert create_response.status_code == 200
        asset_payload = create_response.json()

        preview_response = await authenticated_client.post(
            f"/api/workspaces/{workspace_id}/assets/{asset_payload['id']}/preview-artifact",
        )
        assert preview_response.status_code == 200
        preview_payload = preview_response.json()
        assert preview_payload["preview_kind"] == "asset"
        assert preview_payload["entry_descriptor"] == {"entry_type": "asset_host"}
        assert preview_payload["asset_id"] == asset_payload["id"]
        assert preview_payload["asset_name"] == item["name"]

        manifest_response = await authenticated_client.get(
            f"/internal/runtime/preview-artifacts/{preview_payload['artifact_id']}/manifest",
            headers=runtime_service_headers,
        )
        assert manifest_response.status_code == 200
        manifest = manifest_response.json()
        assert manifest["preview_kind"] == "asset"
        assert manifest["owner_scope"]["scope_type"] == "workspace_asset"
        assert manifest["owner_scope"]["asset_id"] == str(asset_payload["id"])
        assert manifest["entry_descriptor"] == {"entry_type": "asset_host"}
        assert manifest["assets"][item["name"]] == asset_payload["file_hash"]
        assert manifest["asset_metadata"][item["name"]]["render_type"] == item["asset_type"]

        config_response = await authenticated_client.get(
            f"/internal/runtime/preview-artifacts/{preview_payload['artifact_id']}/config-bundle",
            headers=runtime_service_headers,
        )
        assert config_response.status_code == 200
        asset_preview = config_response.json()["asset_preview"]
        assert asset_preview["asset_id"] == asset_payload["id"]
        assert asset_preview["name"] == item["name"]
        assert asset_preview["render_type"] == item["asset_type"]
        assert asset_preview["file_hash"] == asset_payload["file_hash"]


async def test_asset_archive_and_delete_rules_should_preserve_references(authenticated_client: AsyncClient) -> None:
    """删除必须先归档且无引用；归档资源仍能通过默认 manifest 解析引用。"""

    workspace_id = await _create_workspace(authenticated_client, "资源归档删除空间")
    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "资源引用项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("logo.png", b"logo-png", "image/png")},
        data={"asset_type": "image", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    asset_id = upload_response.json()["id"]

    active_delete_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}",
    )
    assert active_delete_response.status_code == 409
    assert active_delete_response.json()["code"] == "ASSET_DELETE_REQUIRES_ARCHIVE"

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": "引用资源页面",
            "page_content": '<template><AssetImage name="logo" /></template>',
            "file_type": "vue",
            "status": "active",
        },
    )
    assert page_response.status_code == 200

    archive_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}/archive",
        json={"archive_reason": "测试归档"},
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "archived"

    delete_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}",
    )
    assert delete_response.status_code == 409
    assert delete_response.json()["code"] == "ASSET_DELETE_FORBIDDEN"

    async with get_session_factory()() as session:
        asset_mapping, _ = await ProjectArtifactBuilder(session).build_workspace_asset_snapshot(workspace_id)
    assert asset_mapping["logo"] == upload_response.json()["file_hash"]


async def test_asset_batch_archive_and_delete_should_follow_status_rules(authenticated_client: AsyncClient) -> None:
    """批量操作应只允许 active 普通资源归档，archived/history 资源删除。"""

    workspace_id = await _create_workspace(authenticated_client, "资源批量管理空间")
    first_asset = await _create_svg_asset(authenticated_client, workspace_id, "batch_icon_first")
    second_asset = await _create_svg_asset(authenticated_client, workspace_id, "batch_icon_second")
    history_source = await _create_svg_asset(authenticated_client, workspace_id, "batch_icon_history")

    archive_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/batch-archive",
        json={"asset_ids": [first_asset["id"], second_asset["id"]], "archive_reason": "批量整理"},
    )
    assert archive_response.status_code == 200
    archive_payload = archive_response.json()
    assert archive_payload["succeeded_count"] == 2
    assert archive_payload["failed_count"] == 0
    assert archive_payload["asset_ids"] == [first_asset["id"], second_asset["id"]]

    archive_again_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/batch-archive",
        json={"asset_ids": [first_asset["id"]]},
    )
    assert archive_again_response.status_code == 200
    assert archive_again_response.json()["succeeded_count"] == 0
    assert archive_again_response.json()["failures"][0]["code"] == "ASSET_ARCHIVE_REQUIRES_ACTIVE"

    active_delete_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/batch-delete",
        json={"asset_ids": [history_source["id"]]},
    )
    assert active_delete_response.status_code == 200
    assert active_delete_response.json()["succeeded_count"] == 0
    assert active_delete_response.json()["failures"][0]["code"] == "ASSET_DELETE_REQUIRES_ARCHIVE"

    update_response = await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/assets/{history_source['id']}/content",
        json={
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M3 3"/></svg>',
            "change_note": "生成历史",
        },
    )
    assert update_response.status_code == 200
    history_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"status": "archived", "history_only": "true"},
    )
    assert history_response.status_code == 200
    history_id = history_response.json()["items"][0]["id"]

    delete_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/batch-delete",
        json={"asset_ids": [first_asset["id"], second_asset["id"], history_id]},
    )
    assert delete_response.status_code == 200
    delete_payload = delete_response.json()
    assert delete_payload["succeeded_count"] == 3
    assert delete_payload["failed_count"] == 0
    assert delete_payload["asset_ids"] == [first_asset["id"], second_asset["id"], history_id]


async def test_asset_batch_delete_should_succeed_after_theme_hard_delete(
    authenticated_client: AsyncClient,
) -> None:
    """主题硬删除后不应残留资源外键，关联资源仍可批量删除。"""

    workspace_id = await _create_workspace(authenticated_client, "资源主题外键阻断空间")
    project_icon = await _create_svg_asset(authenticated_client, workspace_id, "theme_fk_icon")
    theme_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/themes",
        json={
            "key": "fk-theme",
            "name": "外键主题",
            "project_icon_asset_id": project_icon["id"],
            "palette": _theme_palette(),
        },
    )
    assert theme_response.status_code == 200

    delete_theme_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/themes/{theme_response.json()['id']}",
    )
    assert delete_theme_response.status_code == 200

    archive_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{project_icon['id']}/archive",
        json={"archive_reason": "准备删除"},
    )
    assert archive_response.status_code == 200

    delete_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/batch-delete",
        json={"asset_ids": [project_icon["id"]]},
    )
    assert delete_response.status_code == 200
    payload = delete_response.json()
    assert payload["succeeded_count"] == 1
    assert payload["failed_count"] == 0
    assert payload["asset_ids"] == [project_icon["id"]]


async def test_asset_batch_delete_should_cleanup_legacy_soft_deleted_theme_fk(
    authenticated_client: AsyncClient,
) -> None:
    """旧软删除主题残留资源外键时，批量删除应先清理旧主题记录。"""

    workspace_id = await _create_workspace(authenticated_client, "资源旧主题外键清理空间")
    project_icon = await _create_svg_asset(authenticated_client, workspace_id, "legacy_theme_fk_icon")
    theme_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/themes",
        json={
            "key": "legacy-fk-theme",
            "name": "旧外键主题",
            "project_icon_asset_id": project_icon["id"],
            "palette": _theme_palette(),
        },
    )
    assert theme_response.status_code == 200
    theme_id = theme_response.json()["id"]

    async with get_session_factory()() as session:
        theme = await session.get(WorkspaceTheme, theme_id)
        assert theme is not None
        theme.deleted_at = utc_now()
        await session.commit()

    archive_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{project_icon['id']}/archive",
        json={"archive_reason": "验证旧软删除主题清理"},
    )
    assert archive_response.status_code == 200

    delete_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/batch-delete",
        json={"asset_ids": [project_icon["id"]]},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["succeeded_count"] == 1

    async with get_session_factory()() as session:
        assert await session.get(WorkspaceTheme, theme_id) is None


async def test_asset_package_export_and_import_should_preserve_metadata(
    authenticated_client: AsyncClient,
) -> None:
    """资源离线包应携带文件、标签、描述等元数据，并可导入到新工作空间。"""

    source_workspace_id = await _create_workspace(authenticated_client, "资源包源空间")
    target_workspace_id = await _create_workspace(authenticated_client, "资源包目标空间")
    create_response = await authenticated_client.post(
        f"/api/workspaces/{source_workspace_id}/assets/content",
        json={
            "asset_type": "image",
            "name": "资源包封面",
            "original_name": "package_hero.svg",
            "description": "资源包封面图",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16"/></svg>',
            "tags": ["封面", "可复用"],
        },
    )
    assert create_response.status_code == 200
    source_asset = create_response.json()

    export_response = await authenticated_client.post(
        f"/api/workspaces/{source_workspace_id}/assets/export-package",
        json={"asset_ids": [source_asset["id"]]},
    )
    assert export_response.status_code == 200
    assert export_response.headers["content-type"] == "application/zip"
    assert "filename*=UTF-8''" in export_response.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(export_response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["package_kind"] == "workspace-assets"
        exported_asset = manifest["assets"][0]
        assert exported_asset["name"] == "资源包封面"
        assert exported_asset["description"] == "资源包封面图"
        assert exported_asset["tags"] == ["封面", "可复用"]
        asset_json = json.loads(archive.read(f"assets/{exported_asset['entry_key']}/asset.json").decode("utf-8"))
        assert asset_json["asset_type"] == "image"

    import_response = await authenticated_client.post(
        f"/api/workspaces/{target_workspace_id}/assets/import-package",
        files={"archive": ("workspace-assets.zip", export_response.content, "application/zip")},
    )
    assert import_response.status_code == 200
    import_payload = import_response.json()
    assert import_payload["imported_count"] == 1
    assert import_payload["failed_count"] == 0
    assert import_payload["assets"][0]["action"] == "create"

    list_response = await authenticated_client.get(
        f"/api/workspaces/{target_workspace_id}/assets",
        params={"asset_type": "image"},
    )
    assert list_response.status_code == 200
    imported_asset = list_response.json()["items"][0]
    assert imported_asset["name"] == "资源包封面"
    assert imported_asset["description"] == "资源包封面图"
    assert imported_asset["tags"] == ["封面", "可复用"]
    assert imported_asset["file_hash"] == source_asset["file_hash"]


async def test_asset_content_validation_should_reject_unsafe_svg(authenticated_client: AsyncClient) -> None:
    """SVG 内容生成应拒绝脚本、事件属性、foreignObject 和远程引用。"""

    workspace_id = await _create_workspace(authenticated_client, "资源安全空间")
    cases = [
        ("icon", "unsafe_icon", "unsafe_icon.svg"),
        ("image", "unsafe_image", "unsafe_image.svg"),
    ]

    for asset_type, name, original_name in cases:
        response = await authenticated_client.post(
            f"/api/workspaces/{workspace_id}/assets/content",
            json={
                "asset_type": asset_type,
                "name": name,
                "original_name": original_name,
                "content": '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                "tags": [],
            },
        )
        assert response.status_code == 400
        assert response.json()["code"] == "SVG_CONTENT_UNSAFE"


async def test_bitmap_image_content_create_should_fail(authenticated_client: AsyncClient) -> None:
    """位图 image 不能通过文本内容接口生成。"""

    workspace_id = await _create_workspace(authenticated_client, "位图图片拒绝空间")
    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "image",
            "name": "bitmap_image",
            "original_name": "bitmap_image.png",
            "content": "not-svg",
            "tags": [],
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "IMAGE_BITMAP_EDIT_UNSUPPORTED"


async def _create_svg_asset(authenticated_client: AsyncClient, workspace_id: int, name: str) -> dict:
    """创建可编辑 SVG 图标资源，供资源 API 测试复用。"""

    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "icon",
            "name": name,
            "original_name": f"{name}.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M1 1"/></svg>',
            "tags": [],
        },
    )
    assert response.status_code == 200
    return response.json()


def _theme_palette() -> dict:
    """构造主题接口所需的最小色板。"""

    return {
        "text": {"primary": "#111111", "secondary": "#333333", "invert": "#ffffff"},
        "background": {"default": "#ffffff", "invert": "#111111"},
        "border": {"default": "#d1d5db", "subtle": "#e5e7eb"},
        "link": {"default": "#2563eb", "hover": "#1d4ed8", "visited": "#7c3aed"},
        "accent": ["#2563eb"],
    }
