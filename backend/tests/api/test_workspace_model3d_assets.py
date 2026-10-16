"""文件功能：验证三维资源（model3d）的上传、替换基线、覆盖拦截与受保护交付行为。"""

from __future__ import annotations

import io
import json
import struct
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from starlette.datastructures import UploadFile

from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.models.asset import WorkspaceAsset
from app.models.enums import RecordStatus
from app.services.asset_service import AssetService

_JSON_CHUNK_TYPE = 0x4E4F534A
_BIN_CHUNK_TYPE = 0x004E4942


def _pad4(data: bytes, pad: bytes = b"\x00") -> bytes:
    """按 4 字节对齐填充。"""

    if len(data) % 4:
        data = data + pad * (4 - len(data) % 4)
    return data


def _build_glb(json_doc: dict, bin_chunk: bytes | None = None) -> bytes:
    """构造测试用 GLB 字节。"""

    json_bytes = _pad4(json.dumps(json_doc).encode("utf-8"), b" ")
    chunks = struct.pack("<II", len(json_bytes), _JSON_CHUNK_TYPE) + json_bytes
    if bin_chunk is not None:
        bin_bytes = _pad4(bin_chunk)
        chunks += struct.pack("<II", len(bin_bytes), _BIN_CHUNK_TYPE) + bin_bytes
    return b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks


def _valid_glb(marker: float = 0.0) -> bytes:
    """构造最小合法 GLB；marker 用于生成不同哈希。"""

    positions = struct.pack("<9f", marker, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    gltf = {
        "asset": {"version": "2.0", "generator": "model3d-api-test"},
        "buffers": [{"byteLength": len(positions)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(positions)}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    return _build_glb(gltf, positions)


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回主键。"""

    response = await authenticated_client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200
    return response.json()["id"]


async def _upload_model3d(authenticated_client: AsyncClient, workspace_id: int, *, name: str = "product", payload: bytes | None = None) -> dict:
    """上传三维资源并返回接口响应。"""

    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (f"{name}.glb", payload or _valid_glb(), "model/gltf-binary")},
        data={"asset_type": "model3d", "tags": "[]", "name": name},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_model3d_upload_produces_summary_and_protected_delivery(
    authenticated_client: AsyncClient,
) -> None:
    """上传三维资源后应返回 model3d 摘要，并通过受保护链路交付原始字节。"""

    workspace_id = await _create_workspace(authenticated_client, "三维资源交付空间")
    payload = _valid_glb()
    asset = await _upload_model3d(authenticated_client, workspace_id, payload=payload)

    assert asset["asset_type"] == "model3d"
    assert asset["asset_role"] == "content"
    assert asset["render_type"] == "model3d"
    assert asset["content_type"] == "model/gltf-binary"
    assert asset["content_editable"] is False
    analysis = asset["analysis_metadata"]
    assert analysis["kind"] == "model3d"
    assert analysis["model3d"]["format"] == "glb"
    assert analysis["model3d"]["scene_count"] == 1
    assert analysis["model3d"]["validation_profile"] == "model3d-glb-v1"

    # 列表按类型筛选可命中。
    list_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets", params={"asset_type": "model3d"}
    )
    assert list_response.status_code == 200
    assert [item["name"] for item in list_response.json()["items"]] == ["product"]

    # 原始下载字节与上传一致，并支持 ETag/304 与 Range。
    file_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file"
    )
    assert file_response.status_code == 200
    assert file_response.content == payload
    assert file_response.headers["content-type"].startswith("model/gltf-binary")
    assert file_response.headers["etag"] == f'"{asset["file_hash"]}"'

    not_modified = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file",
        headers={"If-None-Match": file_response.headers["etag"]},
    )
    assert not_modified.status_code == 304

    partial = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file",
        headers={"Range": "bytes=0-3"},
    )
    assert partial.status_code == 206
    assert partial.content == b"glTF"

    # 预览 artifact 的 P 票据只读当前 manifest 成员。
    preview_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/preview-artifact"
    )
    assert preview_response.status_code == 200
    preview_url = preview_response.json()["preview_url"]
    token = parse_qs(urlparse(preview_url).query)["token"][0]
    artifact_id = preview_response.json()["artifact_id"]
    asset_read = await authenticated_client.get(
        f"/preview/artifacts/{artifact_id}/assets/{asset['file_hash']}",
        params={"token": token},
    )
    assert asset_read.status_code == 200
    assert asset_read.content == payload
    # manifest 外 hash 被拒绝。
    outside_hash = await authenticated_client.get(
        f"/preview/artifacts/{artifact_id}/assets/{'0' * 64}",
        params={"token": token},
    )
    assert outside_hash.status_code in {403, 404}


async def test_model3d_upload_rejects_invalid_bytes_without_side_effects(
    authenticated_client: AsyncClient,
) -> None:
    """非法 GLB 被拒绝且不产生资源记录。"""

    workspace_id = await _create_workspace(authenticated_client, "三维资源拒绝空间")
    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("broken.glb", b"not-a-glb-at-all", "model/gltf-binary")},
        data={"asset_type": "model3d", "tags": "[]"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "MODEL3D_FORMAT_INVALID"

    list_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets", params={"asset_type": "model3d"}
    )
    assert list_response.json()["total"] == 0


async def test_model3d_upload_must_use_replace_flow_instead_of_overwrite(
    authenticated_client: AsyncClient,
) -> None:
    """对已有三维资源的通用覆盖上传返回明确冲突并指向按 ID 替换。"""

    workspace_id = await _create_workspace(authenticated_client, "三维资源覆盖拦截空间")
    asset = await _upload_model3d(authenticated_client, workspace_id)

    overwrite_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("product.glb", _valid_glb(1.0), "model/gltf-binary")},
        data={"asset_type": "model3d", "tags": "[]", "name": "product", "overwrite": "true"},
    )
    assert overwrite_response.status_code == 409
    assert overwrite_response.json()["code"] == "MODEL3D_OVERWRITE_REQUIRES_REPLACE"

    # 其他类型上传同名也不算可覆盖目标。
    cross_type_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("product.png", b"fake-png", "image/png")},
        data={"asset_type": "image", "tags": "[]", "name": "product", "overwrite": "true"},
    )
    assert cross_type_response.status_code == 409
    assert cross_type_response.json()["code"] == "MODEL3D_OVERWRITE_REQUIRES_REPLACE"

    # 当前记录保持原文件。
    current = await authenticated_client.get(f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file")
    assert current.content == _valid_glb()


async def test_model3d_replace_requires_baseline_and_creates_history(
    authenticated_client: AsyncClient,
) -> None:
    """三维替换缺基线返回 422；基线不匹配返回 409；成功替换生成历史副本。"""

    workspace_id = await _create_workspace(authenticated_client, "三维资源替换空间")
    asset = await _upload_model3d(authenticated_client, workspace_id)
    next_payload = _valid_glb(2.0)

    missing_baseline = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/replace",
        files={"file": ("product.glb", next_payload, "model/gltf-binary")},
    )
    assert missing_baseline.status_code == 422
    assert missing_baseline.json()["code"] == "MODEL3D_REPLACE_BASELINE_REQUIRED"

    stale_baseline = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/replace",
        files={"file": ("product.glb", next_payload, "model/gltf-binary")},
        data={"expected_file_hash": "f" * 64},
    )
    assert stale_baseline.status_code == 409
    assert stale_baseline.json()["code"] == "ASSET_VERSION_CONFLICT"
    unchanged = await authenticated_client.get(f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file")
    assert unchanged.content == _valid_glb()

    replaced = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/replace",
        files={"file": ("product.glb", next_payload, "model/gltf-binary")},
        data={"expected_file_hash": asset["file_hash"]},
    )
    assert replaced.status_code == 200, replaced.text
    updated = replaced.json()
    assert updated["file_hash"] != asset["file_hash"]
    assert updated["name"] == "product"
    assert updated["analysis_metadata"]["kind"] == "model3d"

    current = await authenticated_client.get(f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file")
    assert current.content == next_payload

    # 历史副本保留旧文件指针。
    async with get_session_factory()() as session:
        history_count = await session.scalar(
            select(func.count())
            .select_from(WorkspaceAsset)
            .where(WorkspaceAsset.source_asset_id == asset["id"])
            .where(WorkspaceAsset.file_hash == asset["file_hash"])
        )
    assert history_count == 1

    # 旧基线再次提交必须失败，不能按旧视图覆盖新文件。
    repeated = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/replace",
        files={"file": ("product.glb", _valid_glb(3.0), "model/gltf-binary")},
        data={"expected_file_hash": asset["file_hash"]},
    )
    assert repeated.status_code == 409
    assert repeated.json()["code"] == "ASSET_VERSION_CONFLICT"


async def test_non_model3d_replace_keeps_legacy_call_compatibility(
    authenticated_client: AsyncClient,
) -> None:
    """其他资源类型不携带基线时保持旧调用行为。"""

    workspace_id = await _create_workspace(authenticated_client, "普通资源替换兼容空间")
    upload = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"fake-png", "image/png")},
        data={"asset_type": "image", "tags": "[]", "name": "cover"},
    )
    assert upload.status_code == 200
    asset = upload.json()

    replaced = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/replace",
        files={"file": ("cover.png", b"fake-png-v2", "image/png")},
    )
    assert replaced.status_code == 200
    assert replaced.json()["file_hash"] != asset["file_hash"]


async def test_model3d_replace_cas_rejects_when_row_changed_before_commit(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """条件更新在提交前发现基线已被并发改写时整体回滚，不产生历史或指针变更。"""

    workspace_id = await _create_workspace(authenticated_client, "三维资源并发空间")
    asset = await _upload_model3d(authenticated_client, workspace_id)

    async with get_session_factory()() as session:
        service = AssetService(session)
        original_snapshot = service._create_history_snapshot

        async def sabotaged_snapshot(target: WorkspaceAsset, *, reason: str | None = None) -> WorkspaceAsset:
            """模拟并发写入者在条件更新前已改写基线。"""

            history = await original_snapshot(target, reason=reason)
            await session.execute(
                WorkspaceAsset.__table__.update()
                .where(WorkspaceAsset.id == target.id)
                .values(file_hash="e" * 64, file_name="concurrent-writer.bin")
            )
            return history

        monkeypatch.setattr(service, "_create_history_snapshot", sabotaged_snapshot)
        upload = UploadFile(io.BytesIO(_valid_glb(9.0)), filename="product.glb", size=len(_valid_glb(9.0)))
        with pytest.raises(AppException) as exc_info:
            await service.replace_asset_file(
                workspace_id,
                asset["id"],
                upload,
                expected_file_hash=asset["file_hash"],
            )
        assert exc_info.value.code == "ASSET_VERSION_CONFLICT"
        assert exc_info.value.status_code == 409

    # 回滚后当前记录仍是原文件，且未残留本次历史副本。
    async with get_session_factory()() as session:
        current = await session.scalar(select(WorkspaceAsset).where(WorkspaceAsset.id == asset["id"]))
        assert current is not None
        assert current.file_hash == asset["file_hash"]
        assert current.status == RecordStatus.ACTIVE.value
        history_count = await session.scalar(
            select(func.count()).select_from(WorkspaceAsset).where(WorkspaceAsset.source_asset_id == asset["id"])
        )
    assert history_count == 0
