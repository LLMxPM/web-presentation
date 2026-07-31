"""文件功能：验证工作空间字体配置、预览字体下发与字体资产保护逻辑。"""

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.asset import WorkspaceAsset
from app.models.font import WorkspaceFontConfig, WorkspaceFontFamily
from app.models.workspace_theme import WorkspaceTheme
from app.core.time_utils import utc_now

CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA = '{"props":{"height":{"type":"number","label":"高度","default":320}}}'


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
            "family_name": "非法图标字体",
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
            "family_name": "Brand Sans",
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
            "family_name": " brand sans ",
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
            "family_name": "Brand Sans",
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
                "family_name": "思源黑体",
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
                "family_name": "SourceCodePro",
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
            "heading_font_family_id": create_font_responses[0].json()["family_id"],
            "body_font_family_id": create_font_responses[0].json()["family_id"],
            "code_font_family_id": create_font_responses[1].json()["family_id"],
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
            "family_name": "Brand Serif",
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
import { useAssetFontFamily } from '@runtime-kit/public/composables/assets/useAssetFontFamily.v1'
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
            "family_name": "Component Display",
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
import { resolveAssetFontFamily } from '@runtime-kit/public/utils/fonts.v1'
const componentFont = resolveAssetFontFamily('ComponentDisplay')
</script>
<template><strong :style="{ fontFamily: componentFont }">Component</strong></template>
            """.strip(),
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
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
import { useAssetFontFamily } from '@runtime-kit/public/composables/assets/useAssetFontFamily.v1'
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
            "family_name": "ThemeFontFamily",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert font_response.status_code == 200
    font_id = font_response.json()["id"]
    family_id = font_response.json()["family_id"]

    themes_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/themes")
    assert themes_response.status_code == 200
    theme_id = themes_response.json()["items"][0]["id"]

    update_theme_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/themes/{theme_id}",
        json={
            "heading_font_family_id": family_id,
            "body_font_family_id": family_id,
            "code_font_family_id": family_id,
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
            "family_name": "SoftDeletedThemeFont",
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
        json={"heading_font_family_id": font_response.json()["family_id"]},
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
            "family_name": "DeleteWithAsset",
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
            "family_name": "ExplicitThemeFont",
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
        json={"heading_font_family_id": font_response.json()["family_id"]},
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
            "family_name": "RegisteredFont",
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
import { useAssetFontFamily } from '@runtime-kit/public/composables/assets/useAssetFontFamily.v1'
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
            "family_name": "SummaryFontFamily",
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
                "family_name": font_family,
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
            "family_name": "思源黑体",
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
            "family_name": "思源黑体",
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
            "heading_font_family_id": create_font_response.json()["family_id"],
            "body_font_family_id": create_font_response.json()["family_id"],
            "code_font_family_id": create_font_response.json()["family_id"],
        },
    )
    assert update_theme_response.status_code == 200

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "历史字体配置项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    await _create_home_route(authenticated_client, workspace_id=workspace_id, project_id=project_id)

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )
    assert preview_response.status_code == 409
    assert preview_response.json()["code"] == "FONT_ASSET_NAME_MISMATCH"
    assert "SourceHanSansSC-VF.otf.woff2" in preview_response.json()["message"]


async def _upload_font_asset(client: AsyncClient, workspace_id: int, file_name: str) -> dict:
    """上传字体文件并返回资产载荷。"""

    upload_response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (file_name, f"{file_name}-data".encode(), "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    return upload_response.json()


async def _register_font_face(
    client: AsyncClient,
    workspace_id: int,
    *,
    file_name: str,
    family_name: str,
    font_weight: str = "400",
    font_style: str = "normal",
    status: str = "active",
) -> dict:
    """上传并注册一个字体文件，返回字体配置响应载荷。"""

    asset_payload = await _upload_font_asset(client, workspace_id, file_name)
    create_response = await client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_payload["id"],
            "family_name": family_name,
            "font_weight": font_weight,
            "font_style": font_style,
            "font_display": "swap",
            "status": status,
        },
    )
    assert create_response.status_code == 200
    return create_response.json()


async def test_font_family_should_merge_same_name_and_list_nested_faces(
    authenticated_client: AsyncClient,
) -> None:
    """同名（trim + 忽略大小写）字体族应归并，字体族列表应内嵌全部字体文件。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体族归并空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    regular = await _register_font_face(
        authenticated_client,
        workspace_id,
        file_name="MergeSans-Regular.woff2",
        family_name="Merge Sans",
        font_weight="400",
    )
    bold = await _register_font_face(
        authenticated_client,
        workspace_id,
        file_name="MergeSans-Bold.woff2",
        family_name=" merge sans ",
        font_weight="700",
    )
    assert regular["family_id"] == bold["family_id"]
    assert regular["font_family"] == "Merge Sans"
    assert bold["font_family"] == "Merge Sans"

    families_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/font-families"
    )
    assert families_response.status_code == 200
    families_payload = families_response.json()
    assert families_payload["total"] == 1
    family_item = families_payload["items"][0]
    assert family_item["name"] == "Merge Sans"
    assert [face["font_weight"] for face in family_item["faces"]] == ["400", "700"]
    assert all(face["asset_url"] for face in family_item["faces"])


async def test_font_family_rename_should_enforce_workspace_unique_name(
    authenticated_client: AsyncClient,
) -> None:
    """字体族重命名应生效，与已有族名（忽略大小写）冲突时应拒绝。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体族重命名空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    alpha = await _register_font_face(
        authenticated_client,
        workspace_id,
        file_name="RenameAlpha.woff2",
        family_name="Rename Alpha",
    )
    await _register_font_face(
        authenticated_client,
        workspace_id,
        file_name="RenameBeta.woff2",
        family_name="Rename Beta",
    )

    rename_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/font-families/{alpha['family_id']}",
        json={"name": "Rename Alpha Pro"},
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "Rename Alpha Pro"

    fonts_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/fonts",
        params={"keyword": "RenameAlpha"},
    )
    assert fonts_response.status_code == 200
    assert fonts_response.json()["items"][0]["font_family"] == "Rename Alpha Pro"

    duplicate_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/font-families/{alpha['family_id']}",
        json={"name": " rename beta "},
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["code"] == "FONT_FAMILY_DUPLICATE_NAME"


async def test_font_family_delete_should_reject_non_empty_and_cascade_on_last_face_delete(
    authenticated_client: AsyncClient,
) -> None:
    """非空字体族不允许直接删除；删掉最后一个字体文件后空族应级联清理。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体族级联删除空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    face = await _register_font_face(
        authenticated_client,
        workspace_id,
        file_name="CascadeSans.woff2",
        family_name="Cascade Sans",
    )

    delete_family_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/font-families/{face['family_id']}"
    )
    assert delete_family_response.status_code == 409
    assert delete_family_response.json()["code"] == "FONT_FAMILY_NOT_EMPTY"

    delete_face_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/fonts/{face['id']}"
    )
    assert delete_face_response.status_code == 200

    session_factory = get_session_factory()
    async with session_factory() as session:
        assert await session.get(WorkspaceFontFamily, face["family_id"]) is None


async def test_font_face_move_to_new_family_should_cleanup_orphan_family(
    authenticated_client: AsyncClient,
) -> None:
    """修改 family_name 应把字体文件移入目标族，原族变空后应自动清理。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体文件移族空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    face = await _register_font_face(
        authenticated_client,
        workspace_id,
        file_name="MoveSans-Regular.woff2",
        family_name="Move Sans Old",
    )

    move_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/fonts/{face['id']}",
        json={"family_name": "Move Sans New"},
    )
    assert move_response.status_code == 200
    assert move_response.json()["font_family"] == "Move Sans New"
    assert move_response.json()["family_id"] != face["family_id"]

    session_factory = get_session_factory()
    async with session_factory() as session:
        assert await session.get(WorkspaceFontFamily, face["family_id"]) is None


async def test_font_face_declaration_fields_should_reject_invalid_values(
    authenticated_client: AsyncClient,
) -> None:
    """font-weight/font-style 非法值应拒绝写入，防止脏数据注入 Runtime @font-face。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体声明校验空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    asset_payload = await _upload_font_asset(authenticated_client, workspace_id, "InvalidDeclaration.woff2")

    invalid_weight_cases = ["900 100", "400; } body { color: red", "bold"]
    for invalid_weight in invalid_weight_cases:
        response = await authenticated_client.post(
            f"/api/workspaces/{workspace_id}/fonts",
            json={
                "asset_id": asset_payload["id"],
                "family_name": "Invalid Declaration",
                "font_weight": invalid_weight,
                "font_style": "normal",
                "font_display": "swap",
                "status": "active",
            },
        )
        assert response.status_code == 400, invalid_weight
        assert response.json()["code"] == "FONT_WEIGHT_INVALID"

    invalid_style_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_payload["id"],
            "family_name": "Invalid Declaration",
            "font_weight": "400",
            "font_style": "slanted",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert invalid_style_response.status_code == 400
    assert invalid_style_response.json()["code"] == "FONT_STYLE_INVALID"

    valid_range_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_payload["id"],
            "family_name": "Invalid Declaration",
            "font_weight": "100 900",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert valid_range_response.status_code == 200
    assert valid_range_response.json()["font_weight"] == "100 900"


async def test_preview_bundle_should_include_all_active_faces_of_theme_bound_family(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """主题绑定字体族后，预览字体包应下发该族全部 active 字体文件，archived 不下发。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "字体族整族下发空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    regular = await _register_font_face(
        authenticated_client,
        workspace_id,
        file_name="FamilySans-Regular.woff2",
        family_name="Family Sans",
        font_weight="400",
    )
    await _register_font_face(
        authenticated_client,
        workspace_id,
        file_name="FamilySans-Bold.woff2",
        family_name="Family Sans",
        font_weight="700",
    )
    await _register_font_face(
        authenticated_client,
        workspace_id,
        file_name="FamilySans-Light.woff2",
        family_name="Family Sans",
        font_weight="300",
        status="archived",
    )

    themes_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/themes")
    assert themes_response.status_code == 200
    theme_id = themes_response.json()["items"][0]["id"]
    update_theme_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/themes/{theme_id}",
        json={"heading_font_family_id": regular["family_id"]},
    )
    assert update_theme_response.status_code == 200
    theme_payload = update_theme_response.json()
    assert theme_payload["heading_font_family_id"] == regular["family_id"]
    assert theme_payload["heading_font_family"]["name"] == "Family Sans"

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "整族下发项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    await _create_home_route(authenticated_client, workspace_id=workspace_id, project_id=project_id)

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
    assert fonts_bundle["FamilySans-Regular"]["font_family"] == "Family Sans"
    assert fonts_bundle["FamilySans-Regular"]["font_weight"] == "400"
    assert fonts_bundle["FamilySans-Bold"]["font_family"] == "Family Sans"
    assert fonts_bundle["FamilySans-Bold"]["font_weight"] == "700"
    assert "FamilySans-Light" not in fonts_bundle


async def test_preview_bundle_should_include_whole_family_for_explicit_declaration(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """源码显式声明单个字体文件时，预览字体包应带出所属字体族全部 active 字体文件。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "显式声明整族空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    await _register_font_face(
        authenticated_client,
        workspace_id,
        file_name="DeclaredSerif-Regular.woff2",
        family_name="Declared Serif",
        font_weight="400",
    )
    await _register_font_face(
        authenticated_client,
        workspace_id,
        file_name="DeclaredSerif-Bold.woff2",
        family_name="Declared Serif",
        font_weight="700",
    )

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "显式声明整族项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    await _create_home_route(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        page_content="""
<script setup lang="ts">
import { useAssetFontFamily } from '@runtime-kit/public/composables/assets/useAssetFontFamily.v1'
const titleFont = useAssetFontFamily('DeclaredSerif-Regular')
</script>
<template><h1 :style="{ fontFamily: titleFont }">Declared</h1></template>
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
    assert fonts_bundle["DeclaredSerif-Regular"]["font_family"] == "Declared Serif"
    assert fonts_bundle["DeclaredSerif-Bold"]["font_family"] == "Declared Serif"
