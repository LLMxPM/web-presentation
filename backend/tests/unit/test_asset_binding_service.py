"""文件功能：验证资源占用绑定服务的当前资源解析、持有重建、释放清理与删除保护。"""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.asset import WorkspaceAsset
from app.models.asset_binding import AssetReferenceBinding
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.asset_binding_service import (
    OWNER_KIND_PREVIEW_ARTIFACT,
    OWNER_KIND_RELEASE,
    AssetBindingService,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


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


def _build_root_asset(workspace_id: int, *, name: str, file_hash: str, asset_type: str = "model3d") -> WorkspaceAsset:
    """构造 active 根资源记录。"""

    return WorkspaceAsset(
        workspace_id=workspace_id,
        name=name,
        file_name=f"{file_hash}.glb",
        original_name=f"{name}.glb",
        file_size=128,
        file_hash=file_hash,
        content_type="model/gltf-binary",
        asset_type=asset_type,
        tags=[],
        status=RecordStatus.ACTIVE.value,
    )


def _model3d_metadata(*names: str) -> dict[str, dict[str, object]]:
    """构造 manifest 形态的三维资源元信息。"""

    return {name: {"render_type": "model3d", "file_hash": "unused"} for name in names}


async def _list_bindings(session: AsyncSession, owner_kind: str, owner_key: str) -> list[AssetReferenceBinding]:
    """读取指定 owner 的绑定行，按资源名排序。"""

    rows = await session.scalars(
        select(AssetReferenceBinding)
        .where(AssetReferenceBinding.owner_kind == owner_kind)
        .where(AssetReferenceBinding.owner_key == str(owner_key))
        .order_by(AssetReferenceBinding.resource_name.asc())
    )
    return list(rows.all())


async def test_bind_owner_assets_resolves_current_and_skips_missing(app_session: AsyncSession) -> None:
    """绑定解析当前根资源并整体重建；缺失资源跳过，不阻断产物创建。"""

    workspace = await _create_workspace(app_session, "current")
    asset = _build_root_asset(workspace.id, name="product", file_hash="c" * 64)
    icon = _build_root_asset(workspace.id, name="hero", file_hash="9" * 64, asset_type="icon")
    app_session.add_all([asset, icon])
    await app_session.flush()
    service = AssetBindingService(app_session)

    bindings = await service.bind_owner_model3d_assets(
        workspace_id=workspace.id,
        owner_kind=OWNER_KIND_RELEASE,
        owner_key="301",
        asset_metadata={
            "product": {"render_type": "model3d", "file_hash": "unused"},
            "missing": {"render_type": "model3d", "file_hash": "unused"},
            "hero": {"render_type": "icon", "file_hash": "unused"},
        },
        expires_at=utc_now() + timedelta(minutes=30),
    )
    assert [(item.resource_name, item.asset_id, item.file_hash) for item in bindings] == [
        ("product", int(asset.id), "c" * 64)
    ]

    asset.file_hash = "d" * 64
    asset.file_name = "d" * 64 + ".glb"
    await app_session.flush()
    await service.bind_owner_model3d_assets(
        workspace_id=workspace.id,
        owner_kind=OWNER_KIND_RELEASE,
        owner_key="301",
        asset_metadata=_model3d_metadata("product"),
        expires_at=utc_now() + timedelta(minutes=30),
    )
    current = await _list_bindings(app_session, OWNER_KIND_RELEASE, "301")
    assert len(current) == 1
    assert current[0].asset_id == int(asset.id)
    assert current[0].file_hash == "d" * 64


async def test_expired_hold_release_and_owner_idempotent(app_session: AsyncSession) -> None:
    """过期清理只释放到期持有；显式释放幂等。"""

    workspace = await _create_workspace(app_session, "release")
    asset = _build_root_asset(workspace.id, name="product", file_hash="e" * 64)
    app_session.add(asset)
    await app_session.flush()
    service = AssetBindingService(app_session)
    metadata = _model3d_metadata("product")

    await service.bind_owner_model3d_assets(
        workspace_id=workspace.id,
        owner_kind=OWNER_KIND_PREVIEW_ARTIFACT,
        owner_key="artifact-expired",
        asset_metadata=metadata,
        expires_at=utc_now() - timedelta(minutes=5),
    )
    await service.bind_owner_model3d_assets(
        workspace_id=workspace.id,
        owner_kind=OWNER_KIND_PREVIEW_ARTIFACT,
        owner_key="artifact-active",
        asset_metadata=metadata,
        expires_at=utc_now() + timedelta(minutes=30),
    )
    await service.bind_owner_model3d_assets(
        workspace_id=workspace.id,
        owner_kind=OWNER_KIND_RELEASE,
        owner_key="401",
        asset_metadata=metadata,
        expires_at=utc_now() + timedelta(hours=2),
    )

    released = await service.release_expired()
    assert released == 1
    assert await _list_bindings(app_session, OWNER_KIND_PREVIEW_ARTIFACT, "artifact-expired") == []
    assert len(await _list_bindings(app_session, OWNER_KIND_PREVIEW_ARTIFACT, "artifact-active")) == 1
    assert len(await _list_bindings(app_session, OWNER_KIND_RELEASE, "401")) == 1

    assert await service.release_owner(OWNER_KIND_RELEASE, "401") == 1
    assert await service.release_owner(OWNER_KIND_RELEASE, "401") == 0


async def test_protected_asset_ids_and_invalid_owner_kind(app_session: AsyncSession) -> None:
    """被持有的根资源参与删除保护查询；未知 owner 种类被拒绝。"""

    workspace = await _create_workspace(app_session, "protect")
    asset = _build_root_asset(workspace.id, name="product", file_hash="f" * 64)
    app_session.add(asset)
    await app_session.flush()
    service = AssetBindingService(app_session)

    await service.bind_owner_model3d_assets(
        workspace_id=workspace.id,
        owner_kind=OWNER_KIND_PREVIEW_ARTIFACT,
        owner_key="501",
        asset_metadata=_model3d_metadata("product"),
        expires_at=utc_now() + timedelta(minutes=30),
    )
    assert await service.protected_asset_ids([int(asset.id), 99999]) == {int(asset.id)}
    assert await service.protected_asset_ids([]) == set()

    # 已过期但尚未被对账清理的持有不得继续提供删除保护。
    expired_asset = _build_root_asset(workspace.id, name="expired-product", file_hash="0" * 64)
    app_session.add(expired_asset)
    await app_session.flush()
    await service.bind_owner_model3d_assets(
        workspace_id=workspace.id,
        owner_kind=OWNER_KIND_PREVIEW_ARTIFACT,
        owner_key="502",
        asset_metadata=_model3d_metadata("expired-product"),
        expires_at=utc_now() - timedelta(minutes=5),
    )
    assert await service.protected_asset_ids([int(expired_asset.id)]) == set()

    with pytest.raises(AppException) as error:
        await service.bind_owner_model3d_assets(
            workspace_id=workspace.id,
            owner_kind="unknown_kind",
            owner_key="1",
            asset_metadata=_model3d_metadata("product"),
            expires_at=utc_now() + timedelta(minutes=30),
        )
    assert error.value.code == "ASSET_BINDING_OWNER_INVALID"


async def test_preview_artifact_helper_defaults_ttl_and_commits(app_session: AsyncSession) -> None:
    """预览 artifact 持有入口按默认 TTL 建立并立即提交。"""

    workspace = await _create_workspace(app_session, "preview")
    asset = _build_root_asset(workspace.id, name="product", file_hash="1" * 64)
    app_session.add(asset)
    await app_session.flush()

    await AssetBindingService(app_session).bind_preview_artifact_model3d_assets(
        workspace_id=workspace.id,
        artifact_id="rt_binding_test",
        asset_metadata=_model3d_metadata("product"),
    )
    bindings = await _list_bindings(app_session, OWNER_KIND_PREVIEW_ARTIFACT, "rt_binding_test")
    assert len(bindings) == 1
    assert bindings[0].asset_id == int(asset.id)
    assert bindings[0].expires_at > utc_now()


async def test_bind_resolves_within_target_workspace_only(app_session: AsyncSession) -> None:
    """同名资源只解析目标工作空间记录，不借其他工作空间完成持有。"""

    target = await _create_workspace(app_session, "target-manifest")
    other = await _create_workspace(app_session, "other-manifest")
    app_session.add(_build_root_asset(other.id, name="product", file_hash="a" * 64))
    await app_session.flush()

    bindings = await AssetBindingService(app_session).bind_owner_model3d_assets(
        workspace_id=target.id,
        owner_kind=OWNER_KIND_PREVIEW_ARTIFACT,
        owner_key="other-manifest",
        asset_metadata=_model3d_metadata("product"),
        expires_at=utc_now() + timedelta(minutes=30),
    )
    assert bindings == []
