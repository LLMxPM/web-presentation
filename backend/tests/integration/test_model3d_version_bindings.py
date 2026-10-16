"""文件功能：验证三维资源版本绑定：页面/组件版本冻结、资源版本更新版本与历史预览还原。"""

from __future__ import annotations

import json
import struct

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.asset import WorkspaceAsset
from app.models.asset_binding import AssetReferenceBinding
from app.models.page_version import PageVersion

_JSON_CHUNK_TYPE = 0x4E4F534A


def _pad4(data: bytes, pad: bytes = b"\x00") -> bytes:
    """按 4 字节对齐填充。"""

    if len(data) % 4:
        data = data + pad * (4 - len(data) % 4)
    return data


def _valid_glb(marker: float = 0.0) -> bytes:
    """构造最小合法 GLB；marker 用于生成不同哈希。"""

    positions = struct.pack("<9f", marker, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    gltf = {
        "asset": {"version": "2.0", "generator": "binding-test"},
        "buffers": [{"byteLength": len(positions)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(positions)}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    json_bytes = _pad4(json.dumps(gltf).encode("utf-8"), b" ")
    chunks = struct.pack("<II", len(json_bytes), _JSON_CHUNK_TYPE) + json_bytes
    bin_bytes = _pad4(positions)
    chunks += struct.pack("<II", len(bin_bytes), 0x004E4942) + bin_bytes
    return b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks


async def _create_workspace(client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回 ID。"""

    response = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200
    return int(response.json()["id"])


async def _create_project(client: AsyncClient, workspace_id: int, name: str) -> int:
    """创建测试项目并返回 ID。"""

    response = await client.post("/api/projects", json={"workspace_id": workspace_id, "name": name, "status": "active"})
    assert response.status_code == 200
    return int(response.json()["id"])


async def _upload_model3d(client: AsyncClient, workspace_id: int, *, name: str = "product", marker: float = 0.0) -> dict:
    """上传三维资源并返回接口载荷。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (f"{name}.glb", _valid_glb(marker), "model/gltf-binary")},
        data={"asset_type": "model3d", "tags": "[]", "name": name},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _replace_model3d(client: AsyncClient, workspace_id: int, asset: dict, *, marker: float) -> dict:
    """按 ID 替换三维资源并返回新载荷。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/replace",
        files={"file": ("product.glb", _valid_glb(marker), "model/gltf-binary")},
        data={"expected_file_hash": asset["file_hash"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _load_page_version_id(page_id: int, version_no: int) -> int:
    """读取页面版本的数据库主键。"""

    async with get_session_factory()() as session:
        version_id = await session.scalar(
            select(PageVersion.id)
            .where(PageVersion.page_id == page_id)
            .where(PageVersion.version_no == version_no)
        )
    assert version_id is not None
    return int(version_id)


async def _binding_rows(owner_kind: str, owner_key: str) -> list[AssetReferenceBinding]:
    """读取指定 owner 的绑定记录。"""

    async with get_session_factory()() as session:
        rows = (
            (
                await session.execute(
                    select(AssetReferenceBinding)
                    .where(AssetReferenceBinding.owner_kind == owner_kind)
                    .where(AssetReferenceBinding.owner_key == owner_key)
                )
            )
            .scalars()
            .all()
        )
    return list(rows)


async def _load_manifest(client: AsyncClient, artifact_id: str, runtime_service_headers) -> dict:
    """读取预览 artifact manifest。"""

    response = await client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
        headers=runtime_service_headers(artifact_id),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_page_version_binding_freezes_and_refreshes_on_asset_replace(
    authenticated_client: AsyncClient,
    runtime_service_headers,
) -> None:
    """页面保存冻结三维资源身份；资源替换后相同源码保存生成“资源版本更新”版本；历史预览还原旧文件。"""

    workspace_id = await _create_workspace(authenticated_client, "三维绑定页面空间")
    project_id = await _create_project(authenticated_client, workspace_id, "三维绑定页面项目")
    asset = await _upload_model3d(authenticated_client, workspace_id)
    page_content = '<template><div class="p-8"><AssetModel name="product" class="w-full h-80" /></div></template>'

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": page_content,
            "file_type": "vue",
            "title": "三维绑定页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200, page_response.text
    page_id = int(page_response.json()["id"])

    first_version_id = await _load_page_version_id(page_id, 1)
    first_bindings = await _binding_rows("page_version", str(first_version_id))
    assert len(first_bindings) == 1
    assert first_bindings[0].resource_name == "product"
    assert first_bindings[0].file_hash == asset["file_hash"]
    assert first_bindings[0].expires_at is None

    async with get_session_factory()() as session:
        snapshot = await session.get(WorkspaceAsset, first_bindings[0].snapshot_asset_id)
    assert snapshot is not None
    assert snapshot.history_kind == "reference_snapshot"
    assert snapshot.status == "archived"
    assert snapshot.file_name.startswith(asset["file_hash"])

    # 源码与备注均未变化：保存应短路，不生成新版本。
    same_response = await authenticated_client.patch(f"/api/pages/{page_id}", json={"page_content": page_content})
    assert same_response.status_code == 200
    versions_response = await authenticated_client.get(f"/api/pages/{page_id}/versions")
    assert versions_response.status_code == 200
    assert len(versions_response.json()) == 1

    # 替换资源后，相同源码保存必须生成注明“资源版本更新”的新版本并重新绑定。
    replaced = await _replace_model3d(authenticated_client, workspace_id, asset, marker=2.0)
    assert replaced["file_hash"] != asset["file_hash"]
    refresh_response = await authenticated_client.patch(f"/api/pages/{page_id}", json={"page_content": page_content})
    assert refresh_response.status_code == 200
    versions_response = await authenticated_client.get(f"/api/pages/{page_id}/versions")
    versions = versions_response.json()
    assert len(versions) == 2
    assert versions[0]["version_no"] == 2
    assert versions[0]["change_note"] == "资源版本更新"

    second_version_id = await _load_page_version_id(page_id, 2)
    second_bindings = await _binding_rows("page_version", str(second_version_id))
    assert len(second_bindings) == 1
    assert second_bindings[0].file_hash == replaced["file_hash"]

    # 历史版本预览必须使用冻结的旧文件；替换后的新哈希不得混入。
    history_preview = await authenticated_client.post(f"/api/pages/{page_id}/versions/1/preview-artifact")
    assert history_preview.status_code == 200, history_preview.text
    history_manifest = await _load_manifest(authenticated_client, history_preview.json()["artifact_id"], runtime_service_headers)
    assert history_manifest["assets"]["product"] == asset["file_hash"]
    assert history_manifest["asset_binding"]["mode"] == "frozen"
    assert history_manifest["asset_binding"]["frozen_names"] == ["product"]

    # 最新版本的绑定已更新为替换后的文件。
    latest_preview = await authenticated_client.post(f"/api/pages/{page_id}/versions/2/preview-artifact")
    assert latest_preview.status_code == 200
    latest_manifest = await _load_manifest(authenticated_client, latest_preview.json()["artifact_id"], runtime_service_headers)
    assert latest_manifest["assets"]["product"] == replaced["file_hash"]


async def test_component_version_binding_freezes_history_preview(
    authenticated_client: AsyncClient,
    runtime_service_headers,
) -> None:
    """组件发布冻结三维资源身份，组件版本预览使用冻结文件而非替换后的当前文件。"""

    workspace_id = await _create_workspace(authenticated_client, "三维绑定组件空间")
    asset = await _upload_model3d(authenticated_client, workspace_id, name="gear")
    component_content = '<template><div class="p-4"><AssetModel name="gear" class="w-full h-64" /></div></template>'

    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "三维组件",
            "import_name": "ModelCard",
            "content": component_content,
            "preview_schema": '{"props":{"height":{"type":"number","label":"高度","default":320}}}',
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200, create_response.text
    component_id = int(create_response.json()["id"])

    publish_response = await authenticated_client.post(
        f"/api/components/{component_id}/publish",
        json={"change_note": "首次发布"},
    )
    assert publish_response.status_code == 200, publish_response.text

    from app.models.workspace_component_version import WorkspaceComponentVersion

    async with get_session_factory()() as session:
        component_version_id = await session.scalar(
            select(WorkspaceComponentVersion.id)
            .where(WorkspaceComponentVersion.component_id == component_id)
            .where(WorkspaceComponentVersion.version_no == 1)
        )
        assert component_version_id is not None
        version_bindings = list(
            (
                await session.execute(
                    select(AssetReferenceBinding)
                    .where(AssetReferenceBinding.owner_kind == "component_version")
                    .where(AssetReferenceBinding.owner_key == str(component_version_id))
                )
            )
            .scalars()
            .all()
        )
    assert len(version_bindings) == 1
    assert version_bindings[0].resource_name == "gear"
    assert version_bindings[0].file_hash == asset["file_hash"]

    replaced = await _replace_model3d(authenticated_client, workspace_id, asset, marker=3.0)
    assert replaced["file_hash"] != asset["file_hash"]

    preview_response = await authenticated_client.post(f"/api/components/{component_id}/versions/1/preview-artifact")
    assert preview_response.status_code == 200, preview_response.text
    manifest = await _load_manifest(authenticated_client, preview_response.json()["artifact_id"], runtime_service_headers)
    assert manifest["assets"]["gear"] == asset["file_hash"]
    assert manifest["asset_metadata"]["gear"]["file_hash"] == asset["file_hash"]


async def test_page_should_reject_dynamic_model_reference_at_save(
    authenticated_client: AsyncClient,
) -> None:
    """动态 AssetModel 资源名无法冻结：页面保存必须返回 MODEL3D_REFERENCE_UNRESOLVED。"""

    workspace_id = await _create_workspace(authenticated_client, "动态引用页面空间")
    project_id = await _create_project(authenticated_client, workspace_id, "动态引用页面项目")
    await _upload_model3d(authenticated_client, workspace_id)

    dynamic_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": '<template><div class="p-8"><AssetModel :name="dynamicModel" class="w-full h-80" /></div></template>',
            "file_type": "vue",
            "title": "动态引用页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert dynamic_response.status_code == 409, dynamic_response.text
    assert dynamic_response.json()["code"] == "MODEL3D_REFERENCE_UNRESOLVED"

    # 同一页面改用静态资源名后可以正常保存。
    static_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": '<template><div class="p-8"><AssetModel name="product" class="w-full h-80" /></div></template>',
            "file_type": "vue",
            "title": "静态引用页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert static_response.status_code == 200, static_response.text


async def test_component_publish_should_reject_dynamic_model_reference(
    authenticated_client: AsyncClient,
) -> None:
    """动态 AssetModel 资源名无法冻结：组件发布必须返回 MODEL3D_REFERENCE_UNRESOLVED。"""

    workspace_id = await _create_workspace(authenticated_client, "动态引用组件空间")
    await _upload_model3d(authenticated_client, workspace_id, name="gear")

    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "动态引用组件",
            "import_name": "DynamicModelCard",
            "content": '<template><div class="p-4"><AssetModel :name="gearName" class="w-full h-64" /></div></template>',
            "preview_schema": '{"props":{"height":{"type":"number","label":"高度","default":320}}}',
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200, component_response.text

    publish_response = await authenticated_client.post(
        f"/api/components/{component_response.json()['id']}/publish",
        json={"change_note": "动态引用发布"},
    )
    assert publish_response.status_code == 409, publish_response.text
    assert publish_response.json()["code"] == "MODEL3D_REFERENCE_UNRESOLVED"


async def test_render_snapshot_digest_should_follow_model3d_file_identity(
    authenticated_client: AsyncClient,
) -> None:
    """同一页面版本的渲染输入摘要必须随三维资源替换变化，旧 digest 不冒充当前输入。"""

    from app.services.rendering.snapshot_service import RenderSnapshotService

    workspace_id = await _create_workspace(authenticated_client, "渲染摘要空间")
    project_id = await _create_project(authenticated_client, workspace_id, "渲染摘要项目")
    asset = await _upload_model3d(authenticated_client, workspace_id)
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": '<template><div class="p-8"><AssetModel name="product" class="w-full h-80" /></div></template>',
            "file_type": "vue",
            "title": "渲染摘要页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200, page_response.text
    page_id = int(page_response.json()["id"])

    async def build_digest() -> str:
        async with get_session_factory()() as session:
            snapshot = await RenderSnapshotService(session).build_page_snapshot(
                page_id=page_id,
                artifact_id="artifact-render-digest",
                preview_token="preview-token",
                viewport={"width": 1920, "height": 1080},
                operation_options={},
                preview_url="http://runtime.local/preview",
            )
        return str(snapshot["input_digest"])

    first_digest = await build_digest()
    assert first_digest == await build_digest()

    replaced = await _replace_model3d(authenticated_client, workspace_id, asset, marker=2.0)
    assert replaced["file_hash"] != asset["file_hash"]
    assert await build_digest() != first_digest
