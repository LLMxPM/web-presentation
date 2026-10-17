"""文件功能：验证三维资源替换语义：历史/组件预览与渲染摘要跟随当前文件，动态引用不再阻断保存发布。"""

from __future__ import annotations

import json
import struct

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.asset_binding import AssetReferenceBinding
from app.models.page import Page
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


async def _upload_image(client: AsyncClient, workspace_id: int, *, name: str = "hero", payload: bytes = b"fake-png-1") -> dict:
    """上传图片资源并返回接口载荷。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (f"{name}.png", payload, "image/png")},
        data={"asset_type": "image", "tags": "[]", "name": name},
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


async def _replace_image(client: AsyncClient, workspace_id: int, asset: dict, *, name: str, payload: bytes) -> dict:
    """按 ID 替换图片资源并返回新载荷。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/replace",
        files={"file": (f"{name}.png", payload, "image/png")},
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


async def _build_screenshot_config_hash(page_id: int) -> str:
    """按页面当前版本构建截图配置指纹。"""

    from app.services.page_screenshot_fingerprint_service import PageScreenshotFingerprintService

    async with get_session_factory()() as session:
        page = await session.get(Page, page_id)
        assert page is not None
        snapshot = await PageScreenshotFingerprintService(session).build_page_snapshot(page)
        return str(snapshot.config_hash)


async def test_page_version_preview_should_follow_replaced_model(
    authenticated_client: AsyncClient,
    runtime_service_headers,
) -> None:
    """页面预览跟随当前模型：替换后历史版本预览显示新文件，相同源码保存不再产生资源版本更新版本。"""

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

    # 源码与备注均未变化：保存短路，不生成新版本。
    same_response = await authenticated_client.patch(f"/api/pages/{page_id}", json={"page_content": page_content})
    assert same_response.status_code == 200
    versions_response = await authenticated_client.get(f"/api/pages/{page_id}/versions")
    assert versions_response.status_code == 200
    assert len(versions_response.json()) == 1

    # 替换资源后，相同源码保存同样不生成新版本：资源内容由当前解析负责，不冻结进版本。
    replaced = await _replace_model3d(authenticated_client, workspace_id, asset, marker=2.0)
    assert replaced["file_hash"] != asset["file_hash"]
    refresh_response = await authenticated_client.patch(f"/api/pages/{page_id}", json={"page_content": page_content})
    assert refresh_response.status_code == 200
    versions_response = await authenticated_client.get(f"/api/pages/{page_id}/versions")
    assert len(versions_response.json()) == 1

    # 历史版本预览按当前资源解析：manifest 使用替换后的哈希，且不再携带冻结扩展。
    history_preview = await authenticated_client.post(f"/api/pages/{page_id}/versions/1/preview-artifact")
    assert history_preview.status_code == 200, history_preview.text
    artifact_id = history_preview.json()["artifact_id"]
    history_manifest = await _load_manifest(authenticated_client, artifact_id, runtime_service_headers)
    assert history_manifest["assets"]["product"] == replaced["file_hash"]
    assert "asset_binding" not in history_manifest

    # 预览 artifact 的临时持有指向当前根资源并带到期时间，artifact 到期后由对账释放。
    bindings = await _binding_rows("preview_artifact", artifact_id)
    assert len(bindings) == 1
    assert bindings[0].resource_name == "product"
    assert bindings[0].asset_id == asset["id"]
    assert bindings[0].expires_at is not None


async def test_component_version_preview_should_follow_replaced_model(
    authenticated_client: AsyncClient,
    runtime_service_headers,
) -> None:
    """组件发布版本预览跟随当前模型，不再使用发布时冻结的文件。"""

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

    replaced = await _replace_model3d(authenticated_client, workspace_id, asset, marker=3.0)
    assert replaced["file_hash"] != asset["file_hash"]

    preview_response = await authenticated_client.post(f"/api/components/{component_id}/versions/1/preview-artifact")
    assert preview_response.status_code == 200, preview_response.text
    manifest = await _load_manifest(authenticated_client, preview_response.json()["artifact_id"], runtime_service_headers)
    assert manifest["assets"]["gear"] == replaced["file_hash"]
    assert manifest["asset_metadata"]["gear"]["file_hash"] == replaced["file_hash"]


async def test_dynamic_model_reference_should_save_and_publish(
    authenticated_client: AsyncClient,
) -> None:
    """动态 AssetModel 引用不再阻断保存与发布：资源身份在指纹层缺省，不冻结进版本。"""

    workspace_id = await _create_workspace(authenticated_client, "动态引用空间")
    project_id = await _create_project(authenticated_client, workspace_id, "动态引用项目")
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
    assert dynamic_response.status_code == 200, dynamic_response.text

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
    assert publish_response.status_code == 200, publish_response.text


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


async def test_screenshot_fingerprint_should_follow_image_replace(
    authenticated_client: AsyncClient,
) -> None:
    """截图指纹纳入所有引用资源身份：替换图片后 config hash 变化，旧截图不再被判为当前。"""

    workspace_id = await _create_workspace(authenticated_client, "截图指纹空间")
    project_id = await _create_project(authenticated_client, workspace_id, "截图指纹项目")
    hero = await _upload_image(authenticated_client, workspace_id)
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": '<template><div class="p-8"><AssetImage name="hero" class="w-full" /></div></template>',
            "file_type": "vue",
            "title": "截图指纹页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200, page_response.text
    page_id = int(page_response.json()["id"])

    first_hash = await _build_screenshot_config_hash(page_id)
    assert first_hash == await _build_screenshot_config_hash(page_id)

    replaced = await _replace_image(
        authenticated_client,
        workspace_id,
        hero,
        name="hero",
        payload=b"fake-png-2",
    )
    assert replaced["file_hash"] != hero["file_hash"]
    assert await _build_screenshot_config_hash(page_id) != first_hash
