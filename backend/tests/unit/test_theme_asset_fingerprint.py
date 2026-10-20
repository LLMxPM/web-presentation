"""文件功能：回归项目/组件检查与截图的主题文件身份，确保字体与 Logo 同名替换使缓存失效。"""
import pytest

from app.models.asset import WorkspaceAsset
from app.models.font import WorkspaceFontConfig, WorkspaceFontFamily
from app.models.workspace import Project, Workspace
from app.models.workspace_theme import WorkspaceTheme
from app.services.code_check_fingerprint import CodeCheckFingerprintBuilder


@pytest.mark.parametrize("for_component", [False, True])
@pytest.mark.parametrize("target", ["font", "logo", "invert", "unused", "favicon"])
async def test_theme_file_replacement_changes_only_relevant_render_identity(app_session, for_component, target):
    """文件名和配置不变时，字体/Logo 内容变化失效缓存；无关资源与 favicon 字节不影响画布身份。"""
    session = app_session
    workspace = Workspace(code="theme-identity", name="主题文件指纹", default_theme_key="identity")
    session.add(workspace)
    await session.flush()
    assets = {name: WorkspaceAsset(
        workspace_id=workspace.id, name=name, file_name=name + ".bin", original_name=name + ".bin",
        file_size=1, file_hash="a" * 64, asset_type="font" if name == "font" else "image",
    ) for name in ("font", "logo", "invert", "unused", "favicon")}
    session.add_all(assets.values())
    family = WorkspaceFontFamily(workspace_id=workspace.id, name="Identity Font")
    session.add(family)
    await session.flush()
    session.add(WorkspaceFontConfig(
        workspace_id=workspace.id, family_id=family.id, asset_id=assets["font"].id,
        asset_name="font", font_format="woff2", font_weight="400", font_style="normal", font_display="swap",
    ))
    session.add(WorkspaceTheme(
        workspace_id=workspace.id, key="identity", name="Identity",
        logo_asset_id=assets["logo"].id, invert_logo_asset_id=assets["invert"].id,
        project_icon_name="favicon", body_font_family_id=family.id,
        heading_font_label="platform-sans", body_font_label="Identity Font", code_font_label="platform-mono",
        palette={"text": {"primary": "#111111", "secondary": "#222222", "invert": "#ffffff"},
                 "background": {"default": "#ffffff", "invert": "#111111"},
                 "border": {"default": "#aaaaaa", "subtle": "#bbbbbb"},
                 "link": {"default": "#111111", "hover": "#222222", "visited": "#333333"}, "accent": ["#123456"]},
    ))
    project = Project(workspace_id=workspace.id, code="identity-project", name="Identity", theme_key="identity", theme_config_yaml="{}")
    session.add(project)
    await session.commit()

    async def fingerprint():
        """调用项目和组件实际共用的主题输入指纹，覆盖截图的同一条计算路径。"""
        return await CodeCheckFingerprintBuilder(session)._build_theme_style_hash(
            workspace_id=workspace.id, project_id=None if for_component else project.id, for_component=for_component,
        )

    original = await fingerprint()
    assets[target].file_hash = "b" * 64
    await session.commit()
    changed = await fingerprint()
    assert (changed != original) is (target in {"font", "logo", "invert"})
