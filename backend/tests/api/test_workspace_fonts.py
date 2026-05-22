"""文件功能：验证工作空间字体配置、预览字体下发与字体资产保护逻辑。"""

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.asset import WorkspaceAsset
from app.models.font import WorkspaceFontConfig
from app.models.workspace_theme import WorkspaceTheme
from app.core.time_utils import utc_now


async def _create_home_route(
    authenticated_client: AsyncClient,
    *,
    workspace_id: int,
    project_id: int,
    page_content: str = "<template><div>font preview</div></template>",
) -> int:
    """创建最小首页页面与 /home 路由，满足项目预览入口校验。"""

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": "字体预览首页",
            "page_content": page_content,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert page_response.status_code == 200

    route_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page_response.json()["id"],
                }
            ]
        },
    )
    assert route_response.status_code == 200
    return int(page_response.json()["id"])


async def test_workspace_font_config_should_only_accept_font_assets(
    authenticated_client: AsyncClient,
) -> None:
    """只有 asset_type=font 的资源才允许注册为字体配置。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体配置空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("logo.svg", b"<svg><rect width='10' height='10'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    asset_id = upload_response.json()["id"]

    create_font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_id,
            "font_family": "非法图标字体",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )

    assert create_font_response.status_code == 400
    assert create_font_response.json()["code"] == "FONT_ASSET_REQUIRED"


async def test_workspace_font_config_should_reject_duplicate_font_face_signature(
    authenticated_client: AsyncClient,
) -> None:
    """同一工作空间内 font-family、font-weight 和 font-style 完全相同时应拒绝重复注册。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体面去重空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    uploaded_asset_ids: list[int] = []
    for file_name in ["BrandSans-Regular.woff2", "BrandSans-RegularCopy.woff2", "BrandSans-Bold.woff2"]:
        upload_response = await authenticated_client.post(
            f"/api/workspaces/{workspace_id}/assets/upload",
            files={"file": (file_name, f"{file_name}-data".encode(), "font/woff2")},
            data={"asset_type": "font", "tags": "[]"},
        )
        assert upload_response.status_code == 200
        uploaded_asset_ids.append(upload_response.json()["id"])

    regular_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": uploaded_asset_ids[0],
            "font_family": "Brand Sans",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert regular_response.status_code == 200

    duplicate_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": uploaded_asset_ids[1],
            "font_family": " brand sans ",
            "font_weight": "400",
            "font_style": "NORMAL",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["code"] == "FONT_CONFIG_DUPLICATE_FACE"

    bold_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": uploaded_asset_ids[2],
            "font_family": "Brand Sans",
            "font_weight": "700",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert bold_response.status_code == 200

    update_to_duplicate_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/fonts/{bold_response.json()['id']}",
        json={"font_weight": "400"},
    )
    assert update_to_duplicate_response.status_code == 409
    assert update_to_duplicate_response.json()["code"] == "FONT_CONFIG_DUPLICATE_FACE"


async def test_preview_artifact_config_bundle_should_include_resolved_workspace_fonts(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """预览 artifact 配置包应根据主题库引用写入实际字体配置。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "预览字体空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    source_han_asset = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("SourceHanSansSC-VF.otf.woff2", b"font-data-1", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert source_han_asset.status_code == 200
    source_han_asset_id = source_han_asset.json()["id"]

    source_code_asset = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("SourceCodePro-Regular.ttf.woff2", b"font-data-2", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert source_code_asset.status_code == 200
    source_code_asset_id = source_code_asset.json()["id"]

    create_font_responses = [
        await authenticated_client.post(
            f"/api/workspaces/{workspace_id}/fonts",
            json={
                "asset_id": source_han_asset_id,
                "font_family": "思源黑体",
                "font_weight": "100 900",
                "font_style": "normal",
                "font_display": "swap",
                "status": "active",
            },
        ),
        await authenticated_client.post(
            f"/api/workspaces/{workspace_id}/fonts",
            json={
                "asset_id": source_code_asset_id,
                "font_family": "SourceCodePro",
                "font_weight": "400",
                "font_style": "normal",
                "font_display": "swap",
                "status": "active",
            },
        ),
    ]
    assert all(response.status_code == 200 for response in create_font_responses)

    themes_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/themes")
    assert themes_response.status_code == 200
    theme_id = themes_response.json()["items"][0]["id"]

    update_theme_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/themes/{theme_id}",
        json={
            "heading_font_id": create_font_responses[0].json()["id"],
            "body_font_id": create_font_responses[0].json()["id"],
            "code_font_id": create_font_responses[1].json()["id"],
        },
    )
    assert update_theme_response.status_code == 200

    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "预览字体项目",
            "status": "active",
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    await _create_home_route(authenticated_client, workspace_id=workspace_id, project_id=project_id)

    slider_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("slider.svg", b"<svg><path d='slider-fonts-1'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert slider_upload_response.status_code == 200

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )
    assert preview_response.status_code == 200
    artifact_id = preview_response.json()["artifact_id"]

    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    config_bundle = config_bundle_response.json()

    fonts_bundle = config_bundle["fonts"]["items"]
    assert fonts_bundle["SourceHanSansSC-VF"]["font_family"] == "思源黑体"
    assert fonts_bundle["SourceHanSansSC-VF"]["font_weight"] == "100 900"
    assert fonts_bundle["SourceCodePro-Regular"]["font_family"] == "SourceCodePro"


async def test_preview_artifact_config_bundle_should_include_declared_non_theme_font(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """页面源码显式声明的非主题字体应进入预览 artifact 字体包。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "页面声明字体空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    font_asset_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("BrandSerif.woff2", b"font-data-brand", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert font_asset_response.status_code == 200
    font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": font_asset_response.json()["id"],
            "font_family": "Brand Serif",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert font_response.status_code == 200

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "页面声明字体项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    await _create_home_route(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        page_content="""
<script setup lang="ts">
import { useAssetFontFamily } from '@runtime-kit/public/composables/assets/useAsset'
const titleFont = useAssetFontFamily('BrandSerif')
</script>
<template><h1 :style="{ fontFamily: titleFont }">Brand</h1></template>
        """.strip(),
    )

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )
    assert preview_response.status_code == 200
    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{preview_response.json()['artifact_id']}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200

    fonts_bundle = config_bundle_response.json()["fonts"]["items"]
    assert fonts_bundle["BrandSerif"]["font_family"] == "Brand Serif"


async def test_preview_artifact_config_bundle_should_include_component_declared_font(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """页面依赖组件中声明的非主题字体应沿组件闭包进入项目字体包。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件声明字体空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    font_asset_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("ComponentDisplay.woff2", b"font-data-component", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert font_asset_response.status_code == 200
    font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": font_asset_response.json()["id"],
            "font_family": "Component Display",
            "font_weight": "700",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert font_response.status_code == 200

    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "字体标题组件",
            "import_name": "FontTitleComponent",
            "content": """
<script setup lang="ts">
import { resolveAssetFontFamily } from '@runtime-kit/public/utils/fonts'
const componentFont = resolveAssetFontFamily('ComponentDisplay')
</script>
<template><strong :style="{ fontFamily: componentFont }">Component</strong></template>
            """.strip(),
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200
    publish_response = await authenticated_client.post(
        f"/api/components/{component_response.json()['id']}/publish",
        json={"change_note": "发布字体组件"},
    )
    assert publish_response.status_code == 200
    component = publish_response.json()

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "组件声明字体项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    await _create_home_route(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        page_content=f"""
<script setup lang="ts">
import FontTitle from '@workspace-components/{component['code']}/v/1'
</script>
<template><FontTitle /></template>
        """.strip(),
    )

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )
    assert preview_response.status_code == 200
    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{preview_response.json()['artifact_id']}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200

    fonts_bundle = config_bundle_response.json()["fonts"]["items"]
    assert fonts_bundle["ComponentDisplay"]["font_family"] == "Component Display"


async def test_preview_artifact_should_fail_when_declared_font_is_not_registered(
    authenticated_client: AsyncClient,
) -> None:
    """源码声明未注册字体资源时，应拒绝创建 artifact 并返回明确错误。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "缺失声明字体空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "缺失声明字体项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    await _create_home_route(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        page_content="""
<script setup lang="ts">
import { useAssetFontFamily } from '@runtime-kit/public/composables/assets/useAsset'
const missingFont = useAssetFontFamily('MissingDisplay')
</script>
<template><h1 :style="{ fontFamily: missingFont }">Missing</h1></template>
        """.strip(),
    )

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )

    assert preview_response.status_code == 409
    assert preview_response.json()["code"] == "FONT_ASSET_NOT_REGISTERED"


async def test_registered_font_asset_should_sync_font_config_name_and_still_block_delete_when_theme_still_references_it(
    authenticated_client: AsyncClient,
) -> None:
    """字体资产改逻辑名后应同步字体配置，但主题引用未解除前仍不允许删除。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体保护空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("ThemeFont.woff2", b"font-data-3", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    asset_payload = upload_response.json()
    asset_id = asset_payload["id"]

    font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_id,
            "font_family": "ThemeFontFamily",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert font_response.status_code == 200
    font_id = font_response.json()["id"]

    themes_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/themes")
    assert themes_response.status_code == 200
    theme_id = themes_response.json()["items"][0]["id"]

    update_theme_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/themes/{theme_id}",
        json={
            "heading_font_id": font_id,
            "body_font_id": font_id,
            "code_font_id": font_id,
        },
    )
    assert update_theme_response.status_code == 200

    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "字体保护项目",
            "status": "active",
        },
    )
    assert project_response.status_code == 200

    rename_response = await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}",
        json={"name": "ThemeFontRenamed"},
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "ThemeFontRenamed"

    list_fonts_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/fonts")
    assert list_fonts_response.status_code == 200
    assert list_fonts_response.json()["items"][0]["asset_name"] == "ThemeFontRenamed"

    delete_font_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/fonts/{font_id}"
    )
    assert delete_font_response.status_code == 409
    assert delete_font_response.json()["code"] == "FONT_CONFIG_IN_USE"

    delete_asset_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}"
    )
    assert delete_asset_response.status_code == 409
    assert delete_asset_response.json()["code"] == "FONT_ASSET_DELETE_FORBIDDEN"


async def test_delete_workspace_font_should_cleanup_soft_deleted_theme_reference(
    authenticated_client: AsyncClient,
) -> None:
    """软删除主题仍保留字体外键时，删除字体应清理历史主题并成功。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "软删除主题字体保护空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("SoftDeletedThemeFont.woff2", b"font-data-soft-theme", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    asset_id = upload_response.json()["id"]

    font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_id,
            "font_family": "SoftDeletedThemeFont",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert font_response.status_code == 200
    font_id = font_response.json()["id"]

    themes_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/themes")
    assert themes_response.status_code == 200
    theme_id = themes_response.json()["items"][0]["id"]

    update_theme_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/themes/{theme_id}",
        json={"heading_font_id": font_id},
    )
    assert update_theme_response.status_code == 200

    session_factory = get_session_factory()
    async with session_factory() as session:
        theme = await session.get(WorkspaceTheme, theme_id)
        assert theme is not None
        theme.deleted_at = utc_now()
        await session.commit()

    delete_font_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/fonts/{font_id}"
    )
    assert delete_font_response.status_code == 200

    session_factory = get_session_factory()
    async with session_factory() as session:
        assert await session.get(WorkspaceTheme, theme_id) is None
        assert await session.get(WorkspaceFontConfig, font_id) is None


async def test_delete_workspace_font_with_asset_should_remove_config_asset_and_histories(
    authenticated_client: AsyncClient,
) -> None:
    """delete_asset=true 时应同时删除字体注册、当前资产和该资产历史记录。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体注册硬删空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("DeleteWithAsset.woff2", b"font-data-delete", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    asset_id = upload_response.json()["id"]

    replace_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset_id}/replace",
        files={"file": ("DeleteWithAssetV2.woff2", b"font-data-delete-v2", "font/woff2")},
    )
    assert replace_response.status_code == 200

    create_font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_id,
            "font_family": "DeleteWithAsset",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert create_font_response.status_code == 200
    font_id = create_font_response.json()["id"]

    delete_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/fonts/{font_id}",
        params={"delete_asset": "true"},
    )
    assert delete_response.status_code == 200

    session_factory = get_session_factory()
    async with session_factory() as session:
        assert await session.get(WorkspaceFontConfig, font_id) is None
        assert await session.get(WorkspaceAsset, asset_id) is None
        history_rows = (
            await session.execute(
                select(WorkspaceAsset)
                .where(WorkspaceAsset.workspace_id == workspace_id)
                .where(WorkspaceAsset.source_asset_id == asset_id)
            )
        ).scalars().all()
        assert history_rows == []


async def test_delete_workspace_font_with_asset_should_fail_when_theme_explicitly_references_font(
    authenticated_client: AsyncClient,
) -> None:
    """主题显式 font_id 仍引用字体注册时，delete_asset=true 也应整体失败。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体显式引用保护空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("ExplicitThemeFont.woff2", b"font-data-explicit", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    asset_id = upload_response.json()["id"]

    font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_id,
            "font_family": "ExplicitThemeFont",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert font_response.status_code == 200
    font_id = font_response.json()["id"]

    themes_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/themes")
    assert themes_response.status_code == 200
    theme_id = themes_response.json()["items"][0]["id"]
    update_theme_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/themes/{theme_id}",
        json={"heading_font_id": font_id},
    )
    assert update_theme_response.status_code == 200

    delete_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/fonts/{font_id}",
        params={"delete_asset": "true"},
    )
    assert delete_response.status_code == 409
    assert delete_response.json()["code"] == "FONT_CONFIG_IN_USE"

    session_factory = get_session_factory()
    async with session_factory() as session:
        assert await session.get(WorkspaceFontConfig, font_id) is not None
        assert await session.get(WorkspaceAsset, asset_id) is not None


async def test_unregistered_font_asset_endpoint_should_delete_only_unregistered_fonts(
    authenticated_client: AsyncClient,
) -> None:
    """未注册字体文件可硬删，已注册字体文件必须先删字体注册。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体文件硬删空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    unregistered_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("UnregisteredFont.woff2", b"font-data-unregistered", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert unregistered_upload_response.status_code == 200
    unregistered_asset_id = unregistered_upload_response.json()["id"]

    delete_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/font-assets/{unregistered_asset_id}"
    )
    assert delete_response.status_code == 200
    session_factory = get_session_factory()
    async with session_factory() as session:
        assert await session.get(WorkspaceAsset, unregistered_asset_id) is None

    registered_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("RegisteredFont.woff2", b"font-data-registered", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert registered_upload_response.status_code == 200
    registered_asset_id = registered_upload_response.json()["id"]
    font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": registered_asset_id,
            "font_family": "RegisteredFont",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert font_response.status_code == 200

    registered_delete_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/font-assets/{registered_asset_id}"
    )
    assert registered_delete_response.status_code == 409
    assert registered_delete_response.json()["code"] == "FONT_ASSET_REGISTERED"

    session_factory = get_session_factory()
    async with session_factory() as session:
        assert await session.get(WorkspaceAsset, registered_asset_id) is not None


async def test_unregistered_font_asset_delete_should_fail_when_source_still_declares_font(
    authenticated_client: AsyncClient,
) -> None:
    """页面源码显式声明字体资源名时，未注册字体文件硬删应返回 409。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体源码引用保护空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("DeclaredOnlyFont.woff2", b"font-data-declared-only", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    asset_id = upload_response.json()["id"]

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "title": "字体声明页面",
            "page_content": """
<script setup lang="ts">
import { useAssetFontFamily } from '@runtime-kit/public/composables/assets/useAsset'
const fontFamily = useAssetFontFamily('DeclaredOnlyFont')
</script>
<template><div :style="{ fontFamily }">Declared</div></template>
            """.strip(),
            "file_type": "vue",
            "status": "active",
        },
    )
    assert page_response.status_code == 200

    delete_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/font-assets/{asset_id}"
    )
    assert delete_response.status_code == 409
    assert delete_response.json()["code"] == "FONT_ASSET_DELETE_FORBIDDEN"


async def test_asset_list_should_include_font_config_summary_after_registering_font(
    authenticated_client: AsyncClient,
) -> None:
    """字体注册后，资产列表接口应返回可序列化的 font_config 摘要。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体摘要空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("SummaryFont.woff2", b"font-data-4", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    asset_id = upload_response.json()["id"]

    create_font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_id,
            "font_family": "SummaryFontFamily",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert create_font_response.status_code == 200

    list_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets",
        params={"asset_type": "font"},
    )
    assert list_response.status_code == 200
    asset_payload = list_response.json()["items"][0]

    assert asset_payload["font_config"]["font_family"] == "SummaryFontFamily"
    assert asset_payload["font_config"]["asset_name"] == "SummaryFont"


async def test_workspace_font_list_should_page_keyword_and_status_filter(
    authenticated_client: AsyncClient,
) -> None:
    """字体配置列表应按后端分页返回，并支持关键词与状态筛选。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体分页筛选空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    font_cases = [
        ("AlphaFont.woff2", "Alpha Family", "active"),
        ("BetaFont.woff2", "Beta Family", "active"),
        ("GammaFont.woff2", "Gamma Family", "archived"),
    ]
    for file_name, font_family, status in font_cases:
        upload_response = await authenticated_client.post(
            f"/api/workspaces/{workspace_id}/assets/upload",
            files={"file": (file_name, f"{file_name}-data".encode(), "font/woff2")},
            data={"asset_type": "font", "tags": "[]"},
        )
        assert upload_response.status_code == 200

        create_font_response = await authenticated_client.post(
            f"/api/workspaces/{workspace_id}/fonts",
            json={
                "asset_id": upload_response.json()["id"],
                "font_family": font_family,
                "font_weight": "400",
                "font_style": "normal",
                "font_display": "swap",
                "status": status,
            },
        )
        assert create_font_response.status_code == 200

    first_page_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/fonts",
        params={
            "keyword": "Family",
            "status": "active",
            "page": 1,
            "page_size": 1,
            "sort_by": "font_family",
            "sort_order": "asc",
        },
    )
    assert first_page_response.status_code == 200
    first_page_payload = first_page_response.json()
    assert first_page_payload["total"] == 2
    assert first_page_payload["page"] == 1
    assert first_page_payload["page_size"] == 1
    assert [item["font_family"] for item in first_page_payload["items"]] == ["Alpha Family"]

    second_page_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/fonts",
        params={
            "keyword": "Family",
            "status": "active",
            "page": 2,
            "page_size": 1,
            "sort_by": "font_family",
            "sort_order": "asc",
        },
    )
    assert second_page_response.status_code == 200
    assert [item["font_family"] for item in second_page_response.json()["items"]] == ["Beta Family"]

    archived_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/fonts",
        params={"keyword": "GammaFont", "status": "archived"},
    )
    assert archived_response.status_code == 200
    archived_payload = archived_response.json()
    assert archived_payload["total"] == 1
    assert archived_payload["items"][0]["font_family"] == "Gamma Family"

    all_status_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/fonts",
        params={"status": ""},
    )
    assert all_status_response.status_code == 200
    assert all_status_response.json()["total"] == 3


async def test_preview_artifact_should_not_include_font_matched_only_by_workspace_theme_label(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """旧主题字体 label 仅作为 CSS fallback，不应自动匹配字体注册进入字体包。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "主题标签字体空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("SourceHanSansTheme.woff2", b"font-data-5", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    asset_id = upload_response.json()["id"]

    create_font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_id,
            "font_family": "思源黑体",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert create_font_response.status_code == 200

    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "主题标签字体项目",
            "status": "active",
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    await _create_home_route(authenticated_client, workspace_id=workspace_id, project_id=project_id)

    slider_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("slider.svg", b"<svg><path d='slider-fonts-2'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert slider_upload_response.status_code == 200

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )
    assert preview_response.status_code == 200
    artifact_id = preview_response.json()["artifact_id"]

    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    fonts_bundle = config_bundle_response.json()["fonts"]["items"]

    assert "SourceHanSansTheme" not in fonts_bundle


async def test_preview_artifact_should_fail_when_font_config_asset_name_is_stale(
    authenticated_client: AsyncClient,
) -> None:
    """当历史字体配置 asset_name 与资产表当前 name 不一致时，应显式报错而不是兜底兼容。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "历史字体配置兼容空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("SourceHanSansSC-VF.otf.woff2", b"font-data-legacy", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    asset_payload = upload_response.json()
    assert asset_payload["name"] == "SourceHanSansSC-VF"

    create_font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_payload["id"],
            "font_family": "思源黑体",
            "font_weight": "100 900",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert create_font_response.status_code == 200
    font_id = create_font_response.json()["id"]

    session_factory = get_session_factory()
    async with session_factory() as session:
        font_config = await session.get(WorkspaceFontConfig, font_id)
        assert font_config is not None
        font_config.asset_name = "SourceHanSansSC-VF.otf.woff2"
        await session.commit()

    themes_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/themes")
    assert themes_response.status_code == 200
    theme_id = themes_response.json()["items"][0]["id"]

    update_theme_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/themes/{theme_id}",
        json={
            "heading_font_id": font_id,
            "body_font_id": font_id,
            "code_font_id": font_id,
        },
    )
    assert update_theme_response.status_code == 409
    assert update_theme_response.json()["code"] == "FONT_ASSET_NAME_MISMATCH"
    assert "SourceHanSansSC-VF.otf.woff2" in update_theme_response.json()["message"]
