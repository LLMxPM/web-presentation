"""文件功能：验证资源身份解析器的页面/组件版本闭包遍历、动态引用跳过与实时身份 token。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import WorkspaceAsset
from app.models.component_component_dependency import ComponentVersionComponentDependency
from app.models.component_resource import ComponentVersionComponentResource
from app.models.enums import RecordStatus, UserRole
from app.models.page import Page
from app.models.page_component_dependency import PageVersionComponentDependency
from app.models.page_component_resource import PageVersionComponentResource
from app.models.page_version import PageVersion
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.owner_resource_token_resolver import OwnerResourceTokenResolver


async def _create_workspace(session: AsyncSession, suffix: str) -> Workspace:
    """创建测试用户与工作空间。"""

    user = User(
        username=f"resolver_{suffix}",
        password_hash="hash",
        display_name="Resolver User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    session.add(user)
    await session.flush()
    workspace = Workspace(code=f"ws-resolver-{suffix}", name="Resolver Space", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
    session.add(workspace)
    await session.flush()
    return workspace


def _build_asset(workspace_id: int, *, name: str, asset_type: str, file_hash: str) -> WorkspaceAsset:
    """构造 active 根资源记录。"""

    return WorkspaceAsset(
        workspace_id=workspace_id,
        name=name,
        file_name=f"{file_hash}.bin",
        original_name=f"{name}.glb" if asset_type == "model3d" else f"{name}.svg",
        file_size=64,
        file_hash=file_hash,
        content_type="model/gltf-binary" if asset_type == "model3d" else "image/svg+xml",
        asset_type=asset_type,
        tags=[],
        status=RecordStatus.ACTIVE.value,
    )


async def _create_component_version(
    session: AsyncSession,
    workspace_id: int,
    *,
    code: str,
    name: str,
) -> WorkspaceComponentVersion:
    """构造组件与组件版本记录。"""

    component = WorkspaceComponent(
        workspace_id=workspace_id,
        code=code,
        content="<template><div>c</div></template>",
        current_version_no=1,
        draft_base_version_no=1,
        file_type="vue",
        name=name,
        import_name=f"{code.title()}Component",
        status=RecordStatus.ACTIVE.value,
    )
    session.add(component)
    await session.flush()
    version = WorkspaceComponentVersion(
        component_id=component.id,
        version_no=1,
        version_label="20261017-000000",
        file_type="vue",
        content="<template><div>c</div></template>",
    )
    session.add(version)
    await session.flush()
    return version


async def _create_page_version(session: AsyncSession, workspace_id: int, *, code_suffix: str) -> PageVersion:
    """构造页面与页面版本记录。"""

    page = Page(
        code=f"page-resolver-{code_suffix}",
        page_content="<template><div>p</div></template>",
        current_version_no=1,
        file_type="vue",
        title=f"解析页面 {code_suffix}",
        status=RecordStatus.ACTIVE.value,
        workspace_id=workspace_id,
    )
    session.add(page)
    await session.flush()
    version = PageVersion(
        page_id=page.id,
        version_no=1,
        version_label="20261017-000000",
        file_type="vue",
        storage_type="snapshot",
        content="<template><div>p</div></template>",
    )
    session.add(version)
    await session.flush()
    return version


async def test_page_version_tokens_should_walk_component_closure(app_session: AsyncSession) -> None:
    """页面版本 token 覆盖自有资源与组件闭包资源；归档缺失与动态引用有明确处理。"""

    workspace = await _create_workspace(app_session, "closure")
    shared_model = _build_asset(workspace.id, name="shared_model", asset_type="model3d", file_hash="a" * 64)
    shared_icon = _build_asset(workspace.id, name="shared_icon", asset_type="icon", file_hash="b" * 64)
    page_cover = _build_asset(workspace.id, name="page_cover", asset_type="image", file_hash="c" * 64)
    archived_model = _build_asset(workspace.id, name="retired_model", asset_type="model3d", file_hash="d" * 64)
    archived_model.status = RecordStatus.ARCHIVED.value
    app_session.add_all([shared_model, shared_icon, page_cover, archived_model])
    await app_session.flush()

    dependency_version = await _create_component_version(app_session, workspace.id, code="P_Gear", name="齿轮")
    app_session.add_all(
        [
            ComponentVersionComponentResource(
                workspace_id=workspace.id,
                component_id=dependency_version.component_id,
                component_version_id=dependency_version.id,
                component_name="AssetModel",
                resource_name="shared_model",
            ),
            ComponentVersionComponentResource(
                workspace_id=workspace.id,
                component_id=dependency_version.component_id,
                component_version_id=dependency_version.id,
                component_name="Icon",
                resource_name="shared_icon",
            ),
        ]
    )
    host_version = await _create_component_version(app_session, workspace.id, code="P_Host", name="宿主")
    app_session.add(
        ComponentVersionComponentDependency(
            component_id=host_version.component_id,
            component_version_id=host_version.id,
            dependency_kind="workspace_component",
            dependency_component_id=dependency_version.component_id,
            dependency_component_version_id=dependency_version.id,
            dependency_component_code="p_gear",
            dependency_component_version_no=1,
        )
    )
    await app_session.flush()

    page_version = await _create_page_version(app_session, workspace.id, code_suffix="closure")
    app_session.add_all(
        [
            PageVersionComponentResource(
                project_id=None,
                page_id=page_version.page_id,
                page_version_id=page_version.id,
                component_name="AssetImage",
                resource_attr="name",
                resource_name="page_cover",
            ),
            PageVersionComponentResource(
                project_id=None,
                page_id=page_version.page_id,
                page_version_id=page_version.id,
                component_name="AssetModel",
                resource_attr="name",
                resource_name="retired_model",
            ),
            PageVersionComponentResource(
                project_id=None,
                page_id=page_version.page_id,
                page_version_id=page_version.id,
                component_name="AssetModel",
                resource_attr="name",
                resource_name="__DYNAMIC__",
            ),
        ]
    )
    app_session.add(
        PageVersionComponentDependency(
            page_id=page_version.page_id,
            page_version_id=page_version.id,
            dependency_kind="workspace_component",
            component_id=host_version.component_id,
            component_version_id=host_version.id,
            component_code="p_host",
            component_version_no=1,
        )
    )
    await app_session.flush()

    resolver = OwnerResourceTokenResolver(app_session)
    resolved = await resolver.resolve_page_version_tokens(
        workspace_id=workspace.id,
        page_version_id=page_version.id,
    )
    assert resolved.tokens == [
        f"asset:page_cover:{'c' * 64}",
        "asset:retired_model:missing",
        f"asset:shared_icon:{'b' * 64}",
        f"asset:shared_model:{'a' * 64}",
    ]
    assert resolved.has_model3d is True

    # 批量入口按 owner 各自解析；同一版本结果与单入口一致。
    bulk = await resolver.resolve_page_version_tokens_bulk(
        workspace_id=workspace.id,
        page_version_ids=[page_version.id],
    )
    assert bulk[int(page_version.id)].tokens == resolved.tokens


async def test_page_version_tokens_bulk_should_expand_shared_component_closure_per_owner(
    app_session: AsyncSession,
) -> None:
    """多个页面共享同一组件版本时，每个页面都展开其下游闭包，不因其他页面先行展开而漏 token。"""

    workspace = await _create_workspace(app_session, "shared-closure")
    downstream_model = _build_asset(
        workspace.id, name="downstream_model", asset_type="model3d", file_hash="2" * 64
    )
    host_icon = _build_asset(workspace.id, name="host_icon", asset_type="icon", file_hash="3" * 64)
    app_session.add_all([downstream_model, host_icon])
    await app_session.flush()

    downstream_version = await _create_component_version(
        app_session, workspace.id, code="P_Downstream", name="下游组件"
    )
    app_session.add(
        ComponentVersionComponentResource(
            workspace_id=workspace.id,
            component_id=downstream_version.component_id,
            component_version_id=downstream_version.id,
            component_name="AssetModel",
            resource_name="downstream_model",
        )
    )
    host_version = await _create_component_version(app_session, workspace.id, code="P_HostShared", name="共享宿主")
    app_session.add_all(
        [
            ComponentVersionComponentResource(
                workspace_id=workspace.id,
                component_id=host_version.component_id,
                component_version_id=host_version.id,
                component_name="Icon",
                resource_name="host_icon",
            ),
            ComponentVersionComponentDependency(
                component_id=host_version.component_id,
                component_version_id=host_version.id,
                dependency_kind="workspace_component",
                dependency_component_id=downstream_version.component_id,
                dependency_component_version_id=downstream_version.id,
                dependency_component_code="p_downstream",
                dependency_component_version_no=1,
            ),
        ]
    )
    await app_session.flush()

    page_a = await _create_page_version(app_session, workspace.id, code_suffix="shared-a")
    page_b = await _create_page_version(app_session, workspace.id, code_suffix="shared-b")
    # 页面 A 同时直接依赖宿主和下游组件；页面 B 只依赖宿主，必须仍能沿宿主闭包触达下游资源。
    app_session.add_all(
        [
            PageVersionComponentDependency(
                page_id=page_a.page_id,
                page_version_id=page_a.id,
                dependency_kind="workspace_component",
                component_id=host_version.component_id,
                component_version_id=host_version.id,
                component_code="p_host_shared",
                component_version_no=1,
            ),
            PageVersionComponentDependency(
                page_id=page_a.page_id,
                page_version_id=page_a.id,
                dependency_kind="workspace_component",
                component_id=downstream_version.component_id,
                component_version_id=downstream_version.id,
                component_code="p_downstream",
                component_version_no=1,
            ),
            PageVersionComponentDependency(
                page_id=page_b.page_id,
                page_version_id=page_b.id,
                dependency_kind="workspace_component",
                component_id=host_version.component_id,
                component_version_id=host_version.id,
                component_code="p_host_shared",
                component_version_no=1,
            ),
        ]
    )
    await app_session.flush()

    resolver = OwnerResourceTokenResolver(app_session)
    resolved = await resolver.resolve_page_version_tokens_bulk(
        workspace_id=workspace.id,
        page_version_ids=[page_a.id, page_b.id],
    )
    expected_tokens = [
        f"asset:downstream_model:{'2' * 64}",
        f"asset:host_icon:{'3' * 64}",
    ]
    assert resolved[int(page_a.id)].tokens == expected_tokens
    assert resolved[int(page_b.id)].tokens == expected_tokens
    assert resolved[int(page_b.id)].has_model3d is True


async def test_component_version_tokens_should_follow_replacement(app_session: AsyncSession) -> None:
    """组件版本 token 随资源替换与归档变化；无三维引用时不带三维标记。"""

    workspace = await _create_workspace(app_session, "component")
    model_asset = _build_asset(workspace.id, name="live_model", asset_type="model3d", file_hash="e" * 64)
    icon_asset = _build_asset(workspace.id, name="live_icon", asset_type="icon", file_hash="1" * 64)
    app_session.add_all([model_asset, icon_asset])
    await app_session.flush()

    model_version = await _create_component_version(app_session, workspace.id, code="P_Model", name="模型组件")
    app_session.add(
        ComponentVersionComponentResource(
            workspace_id=workspace.id,
            component_id=model_version.component_id,
            component_version_id=model_version.id,
            component_name="AssetModel",
            resource_name="live_model",
        )
    )
    icon_version = await _create_component_version(app_session, workspace.id, code="P_Icon", name="图标组件")
    app_session.add(
        ComponentVersionComponentResource(
            workspace_id=workspace.id,
            component_id=icon_version.component_id,
            component_version_id=icon_version.id,
            component_name="Icon",
            resource_name="live_icon",
        )
    )
    await app_session.flush()

    resolver = OwnerResourceTokenResolver(app_session)
    resolved = await resolver.resolve_component_version_tokens(
        workspace_id=workspace.id,
        component_version_id=model_version.id,
    )
    assert resolved.tokens == [f"asset:live_model:{'e' * 64}"]
    assert resolved.has_model3d is True

    # 资源替换后 token 解析到新文件身份，实时摘要随替换变化。
    model_asset.file_hash = "f" * 64
    await app_session.flush()
    resolved = await resolver.resolve_component_version_tokens(
        workspace_id=workspace.id,
        component_version_id=model_version.id,
    )
    assert resolved.tokens == [f"asset:live_model:{'f' * 64}"]

    # 资源归档后不再解析为可渲染文件，旧摘要不得冒充当前身份。
    model_asset.status = RecordStatus.ARCHIVED.value
    await app_session.flush()
    resolved = await resolver.resolve_component_version_tokens(
        workspace_id=workspace.id,
        component_version_id=model_version.id,
    )
    assert resolved.tokens == ["asset:live_model:missing"]
    assert resolved.has_model3d is False

    # 仅引用图片等非三维资源时 token 成立但不带三维标记。
    icon_resolved = await resolver.resolve_component_version_tokens(
        workspace_id=workspace.id,
        component_version_id=icon_version.id,
    )
    assert icon_resolved.tokens == [f"asset:live_icon:{'1' * 64}"]
    assert icon_resolved.has_model3d is False
