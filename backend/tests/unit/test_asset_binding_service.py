"""文件功能：验证资源引用绑定服务的参考快照复用、owner 绑定重建、释放清理与删除保护。"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.asset import WorkspaceAsset
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.asset_binding_service import (
    HISTORY_KIND_REFERENCE_SNAPSHOT,
    OWNER_KIND_PAGE_VERSION,
    OWNER_KIND_PREVIEW_ARTIFACT,
    AssetBindingService,
)


async def _create_workspace(session: AsyncSession, suffix: str) -> Workspace:
    """创建测试用户与工作空间并返回工作空间。"""

    user = User(
        username=f"binding_{suffix}",
        password_hash="hash",
        display_name="Binding User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    session.add(user)
    await session.flush()
    workspace = Workspace(code=f"ws-binding-{suffix}", name="Binding Space", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
    session.add(workspace)
    await session.flush()
    return workspace


def _build_root_asset(workspace_id: int, *, name: str, file_hash: str) -> WorkspaceAsset:
    """构造 active 根资源记录。"""

    return WorkspaceAsset(
        workspace_id=workspace_id,
        name=name,
        file_name=f"{file_hash}.glb",
        original_name=f"{name}.glb",
        file_size=128,
        file_hash=file_hash,
        content_type="model/gltf-binary",
        asset_type="model3d",
        tags=[],
        status=RecordStatus.ACTIVE.value,
    )


@pytest.mark.asyncio
async def test_reference_snapshot_reuse_and_hash_switch(app_session: AsyncSession) -> None:
    """同文件版本复用同一参考快照；替换后按新哈希建立新快照。"""

    workspace = await _create_workspace(app_session, "snapshot")
    asset = _build_root_asset(workspace.id, name="product", file_hash="a" * 64)
    app_session.add(asset)
    await app_session.flush()
    service = AssetBindingService(app_session)

    first = await service.ensure_reference_snapshot(workspace.id, asset)
    second = await service.ensure_reference_snapshot(workspace.id, asset)
    assert first.id == second.id
    assert first.status == RecordStatus.ARCHIVED.value
    assert first.history_kind == HISTORY_KIND_REFERENCE_SNAPSHOT
    assert first.source_asset_id == asset.id
    assert first.file_name == asset.file_name

    asset.file_hash = "b" * 64
    asset.file_name = "b" * 64 + ".glb"
    await app_session.flush()
    third = await service.ensure_reference_snapshot(workspace.id, asset)
    assert third.id != first.id
    assert third.file_hash == "b" * 64


@pytest.mark.asyncio
async def test_replace_owner_bindings_rebuilds_and_maps(app_session: AsyncSession) -> None:
    """owner 绑定按最新资源版本整体重建，映射随哈希变化且不留重复。"""

    workspace = await _create_workspace(app_session, "owner")
    asset = _build_root_asset(workspace.id, name="product", file_hash="c" * 64)
    app_session.add(asset)
    await app_session.flush()
    service = AssetBindingService(app_session)

    await service.replace_owner_bindings(
        workspace_id=workspace.id,
        owner_kind=OWNER_KIND_PAGE_VERSION,
        owner_key="101",
        assets=[asset],
    )
    binding_map = await service.owner_binding_hash_map(OWNER_KIND_PAGE_VERSION, "101")
    assert binding_map == {"product": "c" * 64}

    asset.file_hash = "d" * 64
    await app_session.flush()
    await service.replace_owner_bindings(
        workspace_id=workspace.id,
        owner_kind=OWNER_KIND_PAGE_VERSION,
        owner_key="101",
        assets=[asset],
    )
    bindings = await service.list_owner_bindings(OWNER_KIND_PAGE_VERSION, "101")
    assert len(bindings) == 1
    assert bindings[0].file_hash == "d" * 64
    assert bindings[0].snapshot_asset_id != 0


@pytest.mark.asyncio
async def test_release_owner_is_idempotent_and_expired_cleanup(app_session: AsyncSession) -> None:
    """释放 owner 幂等；过期清理只删除到期临时持有，永久持有没有 expires_at。"""

    workspace = await _create_workspace(app_session, "release")
    asset = _build_root_asset(workspace.id, name="product", file_hash="e" * 64)
    app_session.add(asset)
    await app_session.flush()
    service = AssetBindingService(app_session)

    await service.replace_owner_bindings(
        workspace_id=workspace.id,
        owner_kind=OWNER_KIND_PAGE_VERSION,
        owner_key="201",
        assets=[asset],
    )
    await service.replace_owner_bindings(
        workspace_id=workspace.id,
        owner_kind=OWNER_KIND_PREVIEW_ARTIFACT,
        owner_key="artifact-expired",
        assets=[asset],
        expires_at=utc_now() - timedelta(minutes=5),
    )
    await service.replace_owner_bindings(
        workspace_id=workspace.id,
        owner_kind=OWNER_KIND_PREVIEW_ARTIFACT,
        owner_key="artifact-active",
        assets=[asset],
        expires_at=utc_now() + timedelta(minutes=30),
    )

    released = await service.release_expired()
    assert released == 1
    assert await service.list_owner_bindings(OWNER_KIND_PREVIEW_ARTIFACT, "artifact-expired") == []
    assert len(await service.list_owner_bindings(OWNER_KIND_PREVIEW_ARTIFACT, "artifact-active")) == 1
    assert len(await service.list_owner_bindings(OWNER_KIND_PAGE_VERSION, "201")) == 1

    assert await service.release_owner(OWNER_KIND_PAGE_VERSION, "201") == 1
    assert await service.release_owner(OWNER_KIND_PAGE_VERSION, "201") == 0


@pytest.mark.asyncio
async def test_protected_snapshot_asset_ids_and_invalid_owner_kind(app_session: AsyncSession) -> None:
    """被持有的快照记录参与删除保护查询；未知 owner 种类被拒绝。"""

    workspace = await _create_workspace(app_session, "protect")
    asset = _build_root_asset(workspace.id, name="product", file_hash="f" * 64)
    app_session.add(asset)
    await app_session.flush()
    service = AssetBindingService(app_session)

    snapshot = await service.ensure_reference_snapshot(workspace.id, asset)
    await service.replace_owner_bindings(
        workspace_id=workspace.id,
        owner_kind=OWNER_KIND_PAGE_VERSION,
        owner_key="301",
        assets=[asset],
    )
    assert await service.protected_snapshot_asset_ids([snapshot.id, asset.id]) == {snapshot.id}
    assert await service.protected_snapshot_asset_ids([]) == set()

    with pytest.raises(AppException) as error:
        await service.replace_owner_bindings(
            workspace_id=workspace.id,
            owner_kind="unknown_kind",
            owner_key="1",
            assets=[asset],
        )
    assert error.value.code == "ASSET_BINDING_OWNER_INVALID"
