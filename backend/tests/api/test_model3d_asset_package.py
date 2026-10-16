"""文件功能：验证三维资源（model3d）资源包导出导入的字节一致、摘要重解析与篡改拒绝。"""

from __future__ import annotations

import hashlib
import io
import json
import struct
import zipfile

from httpx import AsyncClient

_GLB_JSON_CHUNK_TYPE = 0x4E4F534A
_GLB_BIN_CHUNK_TYPE = 0x004E4942


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
        "asset": {"version": "2.0", "generator": "model3d-asset-package-test"},
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


async def _upload_model3d(client: AsyncClient, workspace_id: int, *, name: str = "product") -> dict:
    """上传三维资源并返回接口响应。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (f"{name}.glb", _valid_glb(), "model/gltf-binary")},
        data={"asset_type": "model3d", "tags": "[]", "name": name},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _import_package(client: AsyncClient, workspace_id: int, archive_content: bytes) -> dict:
    """导入资源包并返回导入结果。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/import-package",
        files={"archive": ("workspace-assets.zip", archive_content, "application/zip")},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_model3d_asset_package_roundtrip_should_preserve_bytes_and_reparse(
    authenticated_client: AsyncClient,
) -> None:
    """三维资源经资源包往返后字节一致，元数据以平台解析结果为准。"""

    source_workspace_id = await _create_workspace(authenticated_client, "三维资源包源空间")
    target_workspace_id = await _create_workspace(authenticated_client, "三维资源包目标空间")
    payload = _valid_glb()
    asset = await _upload_model3d(authenticated_client, source_workspace_id)

    export_response = await authenticated_client.post(
        f"/api/workspaces/{source_workspace_id}/assets/export-package",
        json={"asset_ids": [asset["id"]]},
    )
    assert export_response.status_code == 200, export_response.text
    with zipfile.ZipFile(io.BytesIO(export_response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        exported_entry = manifest["assets"][0]
        assert exported_entry["name"] == "product"
        assert exported_entry["asset_type"] == "model3d"
        assert exported_entry["file_hash"] == asset["file_hash"]
        asset_json = json.loads(
            archive.read(f"assets/{exported_entry['entry_key']}/asset.json").decode("utf-8")
        )
        assert asset_json["content_type"] == "model/gltf-binary"
        assert asset_json["analysis_metadata"]["kind"] == "model3d"
        assert asset_json["analysis_metadata"]["model3d"]["validation_profile"] == "model3d-glb-v1"
        assert archive.read(f"assets/{exported_entry['entry_key']}/product.glb") == payload

    import_payload = await _import_package(authenticated_client, target_workspace_id, export_response.content)
    assert import_payload["imported_count"] == 1
    assert import_payload["failed_count"] == 0
    assert import_payload["assets"][0]["action"] == "create"

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
    analysis = imported_asset["analysis_metadata"]
    assert analysis["kind"] == "model3d"
    assert analysis["model3d"]["scene_count"] == 1
    assert analysis["model3d"]["validation_profile"] == "model3d-glb-v1"

    file_response = await authenticated_client.get(
        f"/api/workspaces/{target_workspace_id}/assets/{imported_asset['id']}/file"
    )
    assert file_response.status_code == 200
    assert file_response.content == payload
    assert file_response.headers["etag"] == f'"{asset["file_hash"]}"'


async def test_model3d_asset_package_import_should_reparse_forged_summary_and_reject_broken_bytes(
    authenticated_client: AsyncClient,
) -> None:
    """资源包内伪造的分析摘要必须被重解析覆盖；字节或 hash 不一致的资源整体拒绝。"""

    source_workspace_id = await _create_workspace(authenticated_client, "三维资源包校验源空间")
    asset = await _upload_model3d(authenticated_client, source_workspace_id)
    export_response = await authenticated_client.post(
        f"/api/workspaces/{source_workspace_id}/assets/export-package",
        json={"asset_ids": [asset["id"]]},
    )
    assert export_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(export_response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    entry_key = manifest["assets"][0]["entry_key"]
    asset_json_path = f"assets/{entry_key}/asset.json"
    asset_file_path = f"assets/{entry_key}/product.glb"

    # 场景一：伪造 analysis_metadata 导入成功但被平台解析器覆盖。
    forged_workspace_id = await _create_workspace(authenticated_client, "三维资源包伪造摘要空间")
    forged_archive = _rewrite_zip_json(
        export_response.content,
        asset_json_path,
        lambda metadata: {
            **metadata,
            "analysis_metadata": {
                "schema_version": 1,
                "kind": "model3d",
                "model3d": {"format": "glb", "scene_count": 999},
                "forged": True,
            },
        },
    )
    forged_payload = await _import_package(authenticated_client, forged_workspace_id, forged_archive)
    assert forged_payload["imported_count"] == 1
    list_response = await authenticated_client.get(
        f"/api/workspaces/{forged_workspace_id}/assets",
        params={"asset_type": "model3d"},
    )
    forged_asset = list_response.json()["items"][0]
    assert forged_asset["analysis_metadata"]["model3d"]["scene_count"] == 1
    assert "forged" not in forged_asset["analysis_metadata"]

    # 场景二：字节被替换但 hash 声明不变，单项导入失败并报 hash 不一致。
    mismatch_workspace_id = await _create_workspace(authenticated_client, "三维资源包字节篡改空间")
    mismatch_archive = _rewrite_zip_binary(export_response.content, asset_file_path, b"broken-model3d")
    mismatch_payload = await _import_package(authenticated_client, mismatch_workspace_id, mismatch_archive)
    assert mismatch_payload["imported_count"] == 0
    assert mismatch_payload["failed_count"] == 1
    assert mismatch_payload["failures"][0]["code"] == "ASSET_PACKAGE_HASH_MISMATCH"

    # 场景三：字节与 file_hash 同步伪造，仍必须被 GLB 解析校验拒绝。
    broken_workspace_id = await _create_workspace(authenticated_client, "三维资源包损坏字节空间")
    broken_bytes = b"broken-model3d"
    broken_hash = hashlib.sha256(broken_bytes).hexdigest()
    bad_archive = _rewrite_zip_binary(export_response.content, asset_file_path, broken_bytes)
    bad_archive = _rewrite_zip_json(
        bad_archive,
        asset_json_path,
        lambda metadata: {**metadata, "file_hash": broken_hash, "file_size": len(broken_bytes)},
    )
    bad_payload = await _import_package(authenticated_client, broken_workspace_id, bad_archive)
    assert bad_payload["imported_count"] == 0
    assert bad_payload["failed_count"] == 1
    assert bad_payload["failures"][0]["code"] == "MODEL3D_FORMAT_INVALID"

    # 三个目标空间都不残留未被校验通过的资源。
    for workspace_id in (forged_workspace_id, mismatch_workspace_id, broken_workspace_id):
        list_response = await authenticated_client.get(
            f"/api/workspaces/{workspace_id}/assets",
            params={"asset_type": "model3d"},
        )
        total = list_response.json()["total"]
        assert total == (1 if workspace_id == forged_workspace_id else 0)
