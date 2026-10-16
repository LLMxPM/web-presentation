"""文件功能：验证三维引用收集器的组件闭包递归、资源类型过滤与动态引用标记。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import WorkspaceAsset
from app.models.component_component_dependency import ComponentVersionComponentDependency
from app.models.component_resource import ComponentVersionComponentResource
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.model3d_reference_collector import Model3dReferenceCollector


async def _create_workspace(session: AsyncSession, suffix: str) -> Workspace:
    """创建测试用户与工作空间。"""

    user = User(
        username=f"collector_{suffix}",
        password_hash="hash",
        display_name="Collector User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    session.add(user)
    await session.flush()
    workspace = Workspace(code=f"ws-collector-{suffix}", name="Collector Space", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
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
        version_label="20261016-000000",
        file_type="vue",
        content="<template><div>c</div></template>",
    )
    session.add(version)
    await session.flush()
    return version


@pytest.mark.asyncio
async def test_collector_should_walk_component_closure_and_flag_dynamic_model(app_session: AsyncSession) -> None:
    """收集器应递归依赖组件版本的资源索引，命中 model3d 根资源并标记动态 AssetModel 引用。"""

    workspace = await _create_workspace(app_session, "closure")
    model_asset = _build_asset(workspace.id, name="shared_model", asset_type="model3d", file_hash="a" * 64)
    icon_asset = _build_asset(workspace.id, name="shared_icon", asset_type="icon", file_hash="b" * 64)
    app_session.add_all([model_asset, icon_asset])
    await app_session.flush()

    # 依赖组件版本（下层）引用 model3d 与 icon。
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

    # 宿主组件版本（上层）依赖下层组件，且自身存在动态 AssetModel 引用。
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

    collection = await Model3dReferenceCollector(app_session).collect_for_component_version(
        workspace_id=workspace.id,
        component_version_id=host_version.id,
        static_resource_items=[("AssetModel", "__DYNAMIC__"), ("AssetImage", "cover_image")],
    )

    assert collection.dynamic_unresolved is True
    assert [asset.name for asset in collection.assets] == ["shared_model"]
    assert collection.assets[0].file_hash == "a" * 64


@pytest.mark.asyncio
async def test_collector_should_ignore_archived_and_non_model_assets(app_session: AsyncSession) -> None:
    """已归档资源与非三维资源不进入绑定集合；重复引用按名称去重。"""

    workspace = await _create_workspace(app_session, "filter")
    archived_model = _build_asset(workspace.id, name="retired_model", asset_type="model3d", file_hash="c" * 64)
    archived_model.status = RecordStatus.ARCHIVED.value
    active_model = _build_asset(workspace.id, name="active_model", asset_type="model3d", file_hash="d" * 64)
    app_session.add_all([archived_model, active_model])
    await app_session.flush()

    version = await _create_component_version(app_session, workspace.id, code="P_Plain", name="普通")
    collection = await Model3dReferenceCollector(app_session).collect_for_component_version(
        workspace_id=workspace.id,
        component_version_id=version.id,
        static_resource_items=[
            ("AssetModel", "retired_model"),
            ("AssetModel", "active_model"),
            ("AssetModel", "missing_model"),
            ("AssetModel", "active_model"),
        ],
    )

    assert collection.dynamic_unresolved is False
    assert [asset.name for asset in collection.assets] == ["active_model"]


@pytest.mark.asyncio
async def test_collector_should_resolve_owner_bindings_to_live_asset_tokens(app_session: AsyncSession) -> None:
    """绑定名集合应解析为当前实时文件身份；替换、归档与无绑定各有明确 token。"""

    from app.services.asset_binding_service import AssetBindingService

    workspace = await _create_workspace(app_session, "tokens")
    asset = _build_asset(workspace.id, name="live_model", asset_type="model3d", file_hash="e" * 64)
    app_session.add(asset)
    await app_session.flush()
    collector = Model3dReferenceCollector(app_session)

    async def tokens() -> list[str]:
        return await collector.list_owner_live_asset_tokens(
            workspace_id=workspace.id,
            owner_kind="component_version",
            owner_key="42",
        )

    # 无绑定 owner 返回空摘要，不猜测任何资源身份。
    assert await tokens() == []

    await AssetBindingService(app_session).replace_owner_bindings(
        workspace_id=workspace.id,
        owner_kind="component_version",
        owner_key="42",
        assets=[asset],
    )
    assert await tokens() == [f"live_model:{'e' * 64}"]

    # 资源替换后绑定名解析到新文件身份，实时摘要随替换变化。
    asset.file_hash = "f" * 64
    await app_session.flush()
    assert await tokens() == [f"live_model:{'f' * 64}"]

    # 资源归档后不再解析为可渲染文件，旧摘要不得冒充当前身份。
    asset.status = RecordStatus.ARCHIVED.value
    await app_session.flush()
    assert await tokens() == ["live_model:missing"]
