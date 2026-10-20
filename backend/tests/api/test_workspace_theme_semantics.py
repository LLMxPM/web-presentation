"""文件功能：验证工作空间主题图片槽位清空、字体真值表与引用校验语义。"""

from httpx import AsyncClient
import pytest


def _theme_palette() -> dict:
    return {
        "text": {"primary": "#20364D", "secondary": "#627487", "invert": "#FFFFFF"},
        "background": {"default": "#FFFFFF", "invert": "#173B5C"},
        "border": {"default": "#D8E2EC", "subtle": "#EDF2F6"},
        "link": {"default": "#1B6CA8", "hover": "#0F4C81", "visited": "#5E6CB5"},
        "accent": ["#2D7BB8", "#159A8C"],
    }


async def _create_test_workspace(client: AsyncClient, name: str) -> int:
    res = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert res.status_code == 200
    return res.json()["id"]


async def _create_icon_asset(client: AsyncClient, workspace_id: int, name: str) -> int:
    res = await client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "icon",
            "name": name,
            "original_name": f"{name}.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M1 1"/></svg>',
            "tags": [],
        },
    )
    assert res.status_code == 200
    return res.json()["id"]


async def _create_image_asset(client: AsyncClient, workspace_id: int, name: str) -> int:
    res = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (f"{name}.png", b"fake-png-content", "image/png")},
        data={"asset_type": "image", "tags": "[]", "name": name},
    )
    assert res.status_code == 200
    return res.json()["id"]


async def _create_font_family_with_face(client: AsyncClient, workspace_id: int, family_name: str) -> int:
    font_name = f"{family_name.lower()}_font"
    font_res = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (f"{font_name}.woff2", b"font-content", "font/woff2")},
        data={"asset_type": "font", "tags": "[]", "name": font_name},
    )
    assert font_res.status_code == 200
    asset_id = font_res.json()["id"]

    reg_res = await client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_id,
            "family_name": family_name,
            "font_format": "woff2",
            "font_weight": "400",
            "font_style": "normal",
        },
    )
    assert reg_res.status_code == 200
    return reg_res.json()["family_id"]


async def test_theme_image_slots_omitted_null_and_replace(authenticated_client: AsyncClient) -> None:
    """验证三个图片槽位在省略时保留、显式 null 时清空、非空时替换。"""
    ws_id = await _create_test_workspace(authenticated_client, "图片语义空间")
    icon1 = await _create_icon_asset(authenticated_client, ws_id, "logo_1")
    icon2 = await _create_icon_asset(authenticated_client, ws_id, "invert_logo_1")
    icon3 = await _create_icon_asset(authenticated_client, ws_id, "project_icon_1")

    # 1. 创建带图片绑定的主题
    create_res = await authenticated_client.post(
        f"/api/workspaces/{ws_id}/themes",
        json={
            "key": "img-theme",
            "name": "图片主题",
            "logo_asset_id": icon1,
            "invert_logo_asset_id": icon2,
            "project_icon_asset_id": icon3,
            "palette": _theme_palette(),
        },
    )
    assert create_res.status_code == 200
    theme_id = create_res.json()["id"]
    data = create_res.json()
    assert data["logo_asset_id"] == icon1
    assert data["invert_logo_asset_id"] == icon2
    assert data["project_icon_asset_id"] == icon3
    assert data["logo_asset"]["name"] == "logo_1"
    assert "logo: logo_1" in data["resolved_theme_config_yaml"]

    # 2. 省略图片字段时，必须保留原有绑定
    patch1 = await authenticated_client.patch(
        f"/api/workspaces/{ws_id}/themes/{theme_id}",
        json={"name": "新名称图片主题"},
    )
    assert patch1.status_code == 200
    d1 = patch1.json()
    assert d1["name"] == "新名称图片主题"
    assert d1["logo_asset_id"] == icon1
    assert d1["invert_logo_asset_id"] == icon2
    assert d1["project_icon_asset_id"] == icon3

    # 3. 显式传 null 清空所有图片槽位
    patch2 = await authenticated_client.patch(
        f"/api/workspaces/{ws_id}/themes/{theme_id}",
        json={
            "logo_asset_id": None,
            "invert_logo_asset_id": None,
            "project_icon_asset_id": None,
        },
    )
    assert patch2.status_code == 200
    d2 = patch2.json()
    assert d2["logo_asset_id"] is None
    assert d2["invert_logo_asset_id"] is None
    assert d2["project_icon_asset_id"] is None
    assert d2["logo_asset"] is None
    assert d2["project_icon_name"] is None
    assert "logo:" not in d2["resolved_theme_config_yaml"]
    assert "invertLogo:" not in d2["resolved_theme_config_yaml"]

    # 4. 再次绑定新资源
    new_icon = await _create_icon_asset(authenticated_client, ws_id, "new_logo")
    patch3 = await authenticated_client.patch(
        f"/api/workspaces/{ws_id}/themes/{theme_id}",
        json={"logo_asset_id": new_icon},
    )
    assert patch3.status_code == 200
    d3 = patch3.json()
    assert d3["logo_asset_id"] == new_icon
    assert d3["logo_asset"]["name"] == "new_logo"
    assert "logo: new_logo" in d3["resolved_theme_config_yaml"]


async def test_theme_font_slots_truth_table_and_conflicts(authenticated_client: AsyncClient) -> None:
    """验证三槽字体的真值表：预设切换、双非空互斥、非法预设与恢复默认。"""
    ws_id = await _create_test_workspace(authenticated_client, "字体真值表空间")
    family_id = await _create_font_family_with_face(authenticated_client, ws_id, "CustomSans")

    theme_res = await authenticated_client.post(
        f"/api/workspaces/{ws_id}/themes",
        json={
            "key": "font-test-theme",
            "name": "字体测试主题",
            "heading_font_family_id": family_id,
            "palette": _theme_palette(),
        },
    )
    assert theme_res.status_code == 200
    theme_id = theme_res.json()["id"]
    assert theme_res.json()["heading_font_label"] == "CustomSans"

    # 1. 切换为内置预设 system-ui
    p1 = await authenticated_client.patch(
        f"/api/workspaces/{ws_id}/themes/{theme_id}",
        json={"heading_font_preset": "system-ui"},
    )
    assert p1.status_code == 200
    assert p1.json()["heading_font_family_id"] is None
    assert p1.json()["heading_font_label"] == "system-ui"

    # 2. 双非空互斥冲突 (422)
    p2 = await authenticated_client.patch(
        f"/api/workspaces/{ws_id}/themes/{theme_id}",
        json={"heading_font_family_id": family_id, "heading_font_preset": "system-ui"},
    )
    assert p2.status_code == 422

    # 3. 槽位不支持的预设 (如标题传 monospace) (422)
    p3 = await authenticated_client.patch(
        f"/api/workspaces/{ws_id}/themes/{theme_id}",
        json={"heading_font_preset": "monospace"},
    )
    assert p3.status_code == 422

    # 4. 显式传 null 恢复平台默认
    p4 = await authenticated_client.patch(
        f"/api/workspaces/{ws_id}/themes/{theme_id}",
        json={"heading_font_preset": None},
    )
    assert p4.status_code == 200
    assert p4.json()["heading_font_family_id"] is None
    assert p4.json()["heading_font_label"] == "platform-sans"


async def test_theme_invalid_asset_references_rejected(authenticated_client: AsyncClient) -> None:
    """验证引用类型错误、跨空间引用及无 active face 的字体族均被拒绝。"""
    ws_id = await _create_test_workspace(authenticated_client, "无效引用空间")
    image_asset_id = await _create_image_asset(authenticated_client, ws_id, "normal_image")

    # 1. 项目图标仅支持 icon，传入 image 应拒绝 (400)
    res1 = await authenticated_client.post(
        f"/api/workspaces/{ws_id}/themes",
        json={
            "key": "invalid-icon-theme",
            "name": "错误图标主题",
            "project_icon_asset_id": image_asset_id,
            "palette": _theme_palette(),
        },
    )
    assert res1.status_code == 400
    assert res1.json()["code"] == "WORKSPACE_THEME_ASSET_INVALID"

    # 2. 引用不存在的资产 (400)
    res2 = await authenticated_client.post(
        f"/api/workspaces/{ws_id}/themes",
        json={
            "key": "missing-asset-theme",
            "name": "丢失资产主题",
            "logo_asset_id": 999999,
            "palette": _theme_palette(),
        },
    )
    assert res2.status_code == 400
    assert res2.json()["code"] == "WORKSPACE_THEME_ASSET_NOT_FOUND"

    # 3. 引用不存在的字体族 (400)
    res3 = await authenticated_client.post(
        f"/api/workspaces/{ws_id}/themes",
        json={
            "key": "missing-font-theme",
            "name": "丢失字体主题",
            "heading_font_family_id": 888888,
            "palette": _theme_palette(),
        },
    )
    assert res3.status_code == 400
    assert res3.json()["code"] == "WORKSPACE_THEME_FONT_NOT_FOUND"


async def test_theme_safe_read_when_referenced_asset_deleted(authenticated_client: AsyncClient) -> None:
    """验证当主题引用的资产失效/归档后，主题查询依然能安全读取而不崩溃，并允许清空修复。"""
    from app.db.session import get_session_factory
    from app.models.asset import WorkspaceAsset
    from sqlalchemy import update

    ws_id = await _create_test_workspace(authenticated_client, "坏引用容错空间")
    icon_id = await _create_icon_asset(authenticated_client, ws_id, "temporary_logo")

    theme_res = await authenticated_client.post(
        f"/api/workspaces/{ws_id}/themes",
        json={
            "key": "safe-read-theme",
            "name": "安全读取主题",
            "logo_asset_id": icon_id,
            "palette": _theme_palette(),
        },
    )
    assert theme_res.status_code == 200
    theme_id = theme_res.json()["id"]

    # 通过数据库底层直接将该资产置为 archived 状态，模拟存量坏数据
    session_factory = get_session_factory()
    async with session_factory() as session:
        await session.execute(
            update(WorkspaceAsset)
            .where(WorkspaceAsset.id == icon_id)
            .values(status="archived")
        )
        await session.commit()

    # 读取列表不报错
    list_res = await authenticated_client.get(f"/api/workspaces/{ws_id}/themes")
    assert list_res.status_code == 200

    # 读取详情不报错
    detail_res = await authenticated_client.get(f"/api/workspaces/{ws_id}/themes/{theme_id}")
    assert detail_res.status_code == 200

    # 允许清空修复
    fix_res = await authenticated_client.patch(
        f"/api/workspaces/{ws_id}/themes/{theme_id}",
        json={"logo_asset_id": None},
    )
    assert fix_res.status_code == 200
    assert fix_res.json()["logo_asset_id"] is None
