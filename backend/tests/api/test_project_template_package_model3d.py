"""文件功能：验证项目模板包携带三维资源（model3d）的导出导入往返与损坏包拒绝。"""

from __future__ import annotations

import hashlib
import io
import json
import struct
import zipfile

from httpx import AsyncClient

_GLB_JSON_CHUNK_TYPE = 0x4E4F534A
_GLB_BIN_CHUNK_TYPE = 0x004E4942

_MODEL_PAGE_CONTENT = '<template><AssetModel name="product" class="w-full h-80" /></template>'


def _pad_glb_chunk(data: bytes, pad: bytes = b"\x00") -> bytes:
    """按 4 字节对齐填充 GLB chunk。"""

    if len(data) % 4:
        data = data + pad * (4 - len(data) % 4)
    return data


def _build_glb(json_doc: dict, bin_chunk: bytes | None = None) -> bytes:
    """构造测试用 GLB 字节。"""

    json_bytes = _pad_glb_chunk(json.dumps(json_doc).encode("utf-8"), b" ")
    chunks = struct.pack("<II", len(json_bytes), _GLB_JSON_CHUNK_TYPE) + json_bytes
    if bin_chunk is not None:
        bin_bytes = _pad_glb_chunk(bin_chunk)
        chunks += struct.pack("<II", len(bin_bytes), _GLB_BIN_CHUNK_TYPE) + bin_bytes
    return b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks


def _valid_glb() -> bytes:
    """构造最小合法 GLB。"""

    positions = struct.pack("<9f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    gltf = {
        "asset": {"version": "2.0", "generator": "template-package-test"},
        "buffers": [{"byteLength": len(positions)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(positions)}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    return _build_glb(gltf, positions)


def _rewrite_zip_binary(archive_content: bytes, target_name: str, content: bytes) -> bytes:
    """重写 Zip 内指定文件的原始字节，保留其它条目不变。"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(archive_content)) as source_archive:
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target_archive:
            for item in source_archive.infolist():
                entry_content = content if item.filename == target_name else source_archive.read(item.filename)
                target_archive.writestr(item, entry_content)
    return buffer.getvalue()


def _rewrite_zip_json(archive_content: bytes, target_name: str, rewrite) -> bytes:
    """重写 Zip 内指定 JSON 文件，保留其它条目不变。"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(archive_content)) as source_archive:
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target_archive:
            for item in source_archive.infolist():
                content = source_archive.read(item.filename)
                if item.filename == target_name:
                    payload = json.loads(content.decode("utf-8"))
                    content = json.dumps(rewrite(payload), ensure_ascii=False).encode("utf-8")
                target_archive.writestr(item, content)
    return buffer.getvalue()


async def _create_workspace(client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回主键。"""

    response = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200
    return response.json()["id"]


async def _create_project_with_model_page(client: AsyncClient, workspace_id: int) -> tuple[int, int]:
    """创建项目和引用 AssetModel 的页面，返回项目与页面主键。"""

    project_response = await client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "三维模板项目", "status": "active"},
    )
    assert project_response.status_code == 200, project_response.text
    project_id = project_response.json()["id"]
    page_response = await client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": "产品展示页",
            "page_content": _MODEL_PAGE_CONTENT,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert page_response.status_code == 200, page_response.text
    return project_id, page_response.json()["id"]


async def _upload_model3d(client: AsyncClient, workspace_id: int) -> dict:
    """上传三维资源并返回接口响应。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("product.glb", _valid_glb(), "model/gltf-binary")},
        data={"asset_type": "model3d", "tags": "[]", "name": "product"},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _export_template_package(client: AsyncClient, project_id: int) -> bytes:
    """导出项目模板包并返回 ZIP 字节。"""

    response = await client.post(
        f"/api/projects/{project_id}/template-package/export",
        json={
            "metadata": {"slug": "model3d-demo", "name": "三维模板"},
            "refresh_screenshots": False,
        },
    )
    assert response.status_code == 200, response.text
    return response.content


async def test_project_template_package_model3d_roundtrip_should_preserve_model_assets(
    authenticated_client: AsyncClient,
) -> None:
    """含三维资源引用的项目模板包导入后应保留资源字节、摘要与新页面引用。"""

    source_workspace_id = await _create_workspace(authenticated_client, "三维模板源空间")
    target_workspace_id = await _create_workspace(authenticated_client, "三维模板目标空间")
    payload = _valid_glb()
    asset = await _upload_model3d(authenticated_client, source_workspace_id)
    assert asset["content_type"] == "model/gltf-binary"
    project_id, _ = await _create_project_with_model_page(authenticated_client, source_workspace_id)

    archive_content = await _export_template_package(authenticated_client, project_id)
    asset_json_path = f"assets/{asset['file_hash']}/asset.json"
    asset_file_path = f"assets/{asset['file_hash']}/product.glb"
    with zipfile.ZipFile(io.BytesIO(archive_content)) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["asset_count"] == 1
        exported_asset = manifest["assets"][0]
        assert exported_asset["name"] == "product"
        assert exported_asset["asset_type"] == "model3d"
        assert exported_asset["file_hash"] == asset["file_hash"]
        asset_json = json.loads(archive.read(asset_json_path).decode("utf-8"))
        assert asset_json["analysis_metadata"]["kind"] == "model3d"
        assert archive.read(asset_file_path) == payload

    import_response = await authenticated_client.post(
        f"/api/workspaces/{target_workspace_id}/template-packages/import",
        files={"archive": ("project-template.zip", archive_content, "application/zip")},
    )
    assert import_response.status_code == 200, import_response.text
    imported = import_response.json()
    imported_asset_summaries = [
        item for item in imported["assets"] if item["name"] == "product"
    ]
    assert len(imported_asset_summaries) == 1
    assert imported_asset_summaries[0]["asset_type"] == "model3d"
    assert imported_asset_summaries[0]["file_hash"] == asset["file_hash"]
    assert imported["page_ids"]

    # 新项目页面仍保留 AssetModel 静态引用。
    page_response = await authenticated_client.get(f"/api/pages/{imported['page_ids'][0]}")
    assert page_response.status_code == 200
    assert '<AssetModel name="product"' in page_response.json()["page_content"]

    # 资源按原字节与平台重解析摘要落入目标工作空间。
    list_response = await authenticated_client.get(
        f"/api/workspaces/{target_workspace_id}/assets",
        params={"asset_type": "model3d"},
    )
    assert list_response.status_code == 200
    imported_items = list_response.json()["items"]
    assert [item["name"] for item in imported_items] == ["product"]
    imported_asset = imported_items[0]
    assert imported_asset["file_hash"] == asset["file_hash"]
    assert imported_asset["content_type"] == "model/gltf-binary"
    assert imported_asset["analysis_metadata"]["model3d"]["scene_count"] == 1

    file_response = await authenticated_client.get(
        f"/api/workspaces/{target_workspace_id}/assets/{imported_asset['id']}/file"
    )
    assert file_response.status_code == 200
    assert file_response.content == payload


async def test_project_template_package_model3d_import_should_reject_broken_bytes(
    authenticated_client: AsyncClient,
) -> None:
    """模板包中字节损坏且 hash 同步伪造的三维资源必须在预检与导入阶段被拒绝。"""

    source_workspace_id = await _create_workspace(authenticated_client, "三维模板篡改源空间")
    target_workspace_id = await _create_workspace(authenticated_client, "三维模板篡改目标空间")
    asset = await _upload_model3d(authenticated_client, source_workspace_id)
    project_id, _ = await _create_project_with_model_page(authenticated_client, source_workspace_id)
    archive_content = await _export_template_package(authenticated_client, project_id)

    asset_json_path = f"assets/{asset['file_hash']}/asset.json"
    asset_file_path = f"assets/{asset['file_hash']}/product.glb"
    broken_bytes = b"broken-template-model3d"
    bad_archive = _rewrite_zip_binary(archive_content, asset_file_path, broken_bytes)
    bad_archive = _rewrite_zip_json(
        bad_archive,
        asset_json_path,
        lambda metadata: {
            **metadata,
            "file_hash": hashlib.sha256(broken_bytes).hexdigest(),
            "file_size": len(broken_bytes),
        },
    )

    validate_response = await authenticated_client.post(
        f"/api/workspaces/{target_workspace_id}/template-packages/import/validate",
        files={"archive": ("project-template.zip", bad_archive, "application/zip")},
    )
    assert validate_response.status_code == 200
    validation = validate_response.json()
    assert validation["valid"] is False
    assert any("GLB" in error for error in validation["errors"])

    import_response = await authenticated_client.post(
        f"/api/workspaces/{target_workspace_id}/template-packages/import",
        files={"archive": ("project-template.zip", bad_archive, "application/zip")},
    )
    assert import_response.status_code == 400
    assert import_response.json()["code"] == "PROJECT_TEMPLATE_IMPORT_INVALID"

    # 目标空间不残留被拒绝的资源或项目数据。
    list_response = await authenticated_client.get(
        f"/api/workspaces/{target_workspace_id}/assets",
        params={"asset_type": "model3d"},
    )
    assert list_response.json()["total"] == 0
    projects_response = await authenticated_client.get(
        "/api/projects",
        params={"workspace_id": target_workspace_id},
    )
    assert projects_response.json()["total"] == 0
