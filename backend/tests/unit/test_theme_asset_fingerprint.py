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


PALETTE = {
    "text": {"primary": "#111111", "secondary": "#222222", "invert": "#ffffff"},
    "background": {"default": "#ffffff", "invert": "#111111"},
    "border": {"default": "#aaaaaa", "subtle": "#bbbbbb"},
    "link": {"default": "#111111", "hover": "#222222", "visited": "#333333"},
    "accent": ["#123456"],
}


async def test_unreferenced_workspace_font_should_not_enter_render_identity(app_session) -> None:
    """注册但未使用的字体不进身份；只有主题绑定或源码显式声明的字体族才可能改变画面。"""

    session = app_session
    workspace = Workspace(code="font-ref", name="字体引用指纹", default_theme_key="ref")
    session.add(workspace)
    await session.flush()
    assets = {name: WorkspaceAsset(
        workspace_id=workspace.id, name=name, file_name=name + ".bin", original_name=name + ".bin",
        file_size=1, file_hash="a" * 64, asset_type="font",
    ) for name in ("bound.woff2", "idle.woff2")}
    session.add_all(assets.values())
    families: dict[str, WorkspaceFontFamily] = {}
    for asset_name, family_name in (("bound.woff2", "Bound Font"), ("idle.woff2", "Idle Font")):
        family = WorkspaceFontFamily(workspace_id=workspace.id, name=family_name)
        session.add(family)
        await session.flush()
        families[asset_name] = family
        session.add(WorkspaceFontConfig(
            workspace_id=workspace.id, family_id=family.id, asset_id=assets[asset_name].id,
            asset_name=asset_name, font_format="woff2", font_weight="400", font_style="normal",
            font_display="swap",
        ))
    session.add(WorkspaceTheme(
        workspace_id=workspace.id, key="ref", name="Ref",
        body_font_family_id=families["bound.woff2"].id,
        heading_font_label="platform-sans", body_font_label="Bound Font", code_font_label="platform-mono",
        palette=PALETTE,
    ))
    project = Project(
        workspace_id=workspace.id, code="font-ref-project", name="FontRef",
        theme_key="ref", theme_config_yaml="{}",
    )
    session.add(project)
    await session.commit()
    builder = CodeCheckFingerprintBuilder(session)

    async def fingerprint(**kwargs) -> str:
        """按可选的源码字体声明复算主题输入指纹。"""

        return await builder._build_theme_style_hash(
            workspace_id=workspace.id, project_id=project.id, for_component=False, **kwargs,
        )

    baseline = await fingerprint()
    assets["idle.woff2"].file_hash = "b" * 64
    await session.commit()
    # 字体包不会下发未引用的族，替换文件内容不得让截图判为过期。
    assert await fingerprint() == baseline
    # 源码显式声明后该族才真正进入渲染输入。
    declared = await fingerprint(declared_font_asset_names=["idle.woff2"])
    assert declared != baseline
    assets["idle.woff2"].file_hash = "c" * 64
    await session.commit()
    assert await fingerprint(declared_font_asset_names=["idle.woff2"]) != declared
