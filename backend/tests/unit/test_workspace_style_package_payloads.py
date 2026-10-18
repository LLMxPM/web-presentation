"""文件功能：验证样式离线包主题载荷归一化对 legacy 资源路径字段的处理。"""

from __future__ import annotations

from app.services.workspace_style_package_payloads import WorkspaceStylePackagePayloads


def test_normalize_theme_payload_should_ignore_legacy_paths_when_asset_names_present() -> None:
    """存在资源名时应丢弃同名 legacy 路径，保证与数据库回读载荷可比较。"""

    normalized = WorkspaceStylePackagePayloads.normalize_theme_payload(
        {
            "key": "brand",
            "name": "品牌主题",
            "logo_asset_name": "brand_logo",
            "logo_path": "brand_logo",
            "invert_logo_asset_name": "brand_invert_logo",
            "invert_logo_path": "brand_invert_logo",
            "project_icon_asset_name": "brand_icon",
            "project_icon_name": "brand_icon",
            "palette": _theme_palette(),
        }
    )

    assert normalized["logo_asset_name"] == "brand_logo"
    assert normalized["logo_path"] is None
    assert normalized["invert_logo_path"] is None
    assert normalized["project_icon_name"] is None


def test_normalize_theme_payload_should_keep_legacy_paths_without_asset_names() -> None:
    """仅维护 legacy 路径的旧主题载荷应保持原值，避免丢失兼容回退。"""

    normalized = WorkspaceStylePackagePayloads.normalize_theme_payload(
        {
            "key": "legacy",
            "name": "旧主题",
            "logo_path": "legacy/logo.svg",
            "invert_logo_path": "legacy/logo-invert.svg",
            "project_icon_name": "legacy/icon.svg",
            "palette": _theme_palette(),
        }
    )

    assert normalized["logo_path"] == "legacy/logo.svg"
    assert normalized["invert_logo_path"] == "legacy/logo-invert.svg"
    assert normalized["project_icon_name"] == "legacy/icon.svg"


def _theme_palette() -> dict:
    """构造主题载荷所需的最小色板。"""

    return {
        "text": {"primary": "#111111", "secondary": "#333333", "invert": "#ffffff"},
        "background": {"default": "#ffffff", "invert": "#111111"},
        "border": {"default": "#d1d5db", "subtle": "#e5e7eb"},
        "link": {"default": "#2563eb", "hover": "#1d4ed8", "visited": "#7c3aed"},
        "accent": ["#2563eb"],
    }
