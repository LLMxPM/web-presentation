"""文件功能：验证 External API v1 资产文件替换契约（版本基线、幂等、Scope 与工作空间隔离）。"""

from __future__ import annotations

import json
import struct
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import get_session_factory
from app.models.asset import WorkspaceAsset
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService

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
        "asset": {"version": "2.0", "generator": "external-replace-test"},
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


async def _create_external_actor(*, scopes: list[str]) -> tuple[str, int]:
    """创建携带 PAT 的外部用户与工作空间，返回令牌和工作空间 ID。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        username_suffix = uuid.uuid4().hex[:8]
        user = User(
            username=f"ext_replace_{username_suffix}",
            password_hash="hash",
            display_name="External Replace User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()
        workspace = Workspace(code=f"ws-ext-replace-{user.id}", name="External Replace Space", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
        session.add(workspace)
        await session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner", status=RecordStatus.ACTIVE.value))
        await session.flush()
        token_result = await ApiAccessTokenService(session).create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="External-Replace-PAT",
                workspace_ids=[workspace.id],
                scopes=scopes,
                expires_in_days=30,
            ),
        )
        token = token_result.token
        workspace_id = workspace.id
        await session.commit()
    return token, workspace_id


async def _external_upload_glb(client: AsyncClient, token: str, workspace_id: int, *, name: str = "product", payload: bytes | None = None) -> dict:
    """通过 External 上传接口创建三维资源。"""

    response = await client.post(
        "/api/v1/assets",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Workspace-ID": str(workspace_id),
            "Idempotency-Key": f"upload-{name}",
        },
        files={"file": (f"{name}.glb", payload or _valid_glb(), "model/gltf-binary")},
        data={"asset_type": "model3d", "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_external_replace_requires_baseline_and_replays_idempotently(client: AsyncClient) -> None:
    """External 替换必须携带基线与幂等键；同键同输入重放不生成第二份历史。"""

    token, workspace_id = await _create_external_actor(scopes=["asset:read", "asset:write", "workspace:read"])
    asset = await _external_upload_glb(client, token, workspace_id)
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(workspace_id)}

    next_payload = _valid_glb(2.0)

    # 缺少 Idempotency-Key：请求依赖拦截。
    missing_key = await client.post(
        f"/api/v1/assets/{asset['id']}/replace",
        headers=headers,
        files={"file": ("product.glb", next_payload, "model/gltf-binary")},
        data={"expected_file_hash": asset["file_hash"]},
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"

    # 缺少 expected_file_hash：请求校验 422。
    missing_baseline = await client.post(
        f"/api/v1/assets/{asset['id']}/replace",
        headers={**headers, "Idempotency-Key": "replace-missing-baseline"},
        files={"file": ("product.glb", next_payload, "model/gltf-binary")},
    )
    assert missing_baseline.status_code == 422

    # 基线不匹配：409，当前记录不变。
    wrong_baseline = await client.post(
        f"/api/v1/assets/{asset['id']}/replace",
        headers={**headers, "Idempotency-Key": "replace-wrong-baseline"},
        files={"file": ("product.glb", next_payload, "model/gltf-binary")},
        data={"expected_file_hash": "f" * 64},
    )
    assert wrong_baseline.status_code == 409
    assert wrong_baseline.json()["code"] == "ASSET_VERSION_CONFLICT"
    unchanged = await client.get(f"/api/v1/assets/{asset['id']}/file", headers=headers)
    assert unchanged.content == _valid_glb()

    # 正确基线的首次替换。
    first = await client.post(
        f"/api/v1/assets/{asset['id']}/replace",
        headers={**headers, "Idempotency-Key": "replace-ok"},
        files={"file": ("product.glb", next_payload, "model/gltf-binary")},
        data={"expected_file_hash": asset["file_hash"]},
    )
    assert first.status_code == 200, first.text
    updated = first.json()
    assert updated["file_hash"] != asset["file_hash"]
    assert updated["asset_type"] == "model3d"

    # 同键同输入重放：返回首次结果，且不生成第二份历史。
    replay = await client.post(
        f"/api/v1/assets/{asset['id']}/replace",
        headers={**headers, "Idempotency-Key": "replace-ok"},
        files={"file": ("product.glb", next_payload, "model/gltf-binary")},
        data={"expected_file_hash": asset["file_hash"]},
    )
    assert replay.status_code == 200
    assert replay.json()["file_hash"] == updated["file_hash"]

    async with get_session_factory()() as session:
        history_count = await session.scalar(
            select(func.count())
            .select_from(WorkspaceAsset)
            .where(WorkspaceAsset.source_asset_id == asset["id"])
        )
    assert history_count == 1


@pytest.mark.asyncio
async def test_external_replace_rejects_key_reuse_and_scope_and_workspace_violations(client: AsyncClient) -> None:
    """同键不同输入、缺少写 Scope 与跨工作空间访问均按契约拒绝。"""

    token, workspace_id = await _create_external_actor(scopes=["asset:read", "asset:write", "workspace:read"])
    asset = await _external_upload_glb(client, token, workspace_id, name="product-scope")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(workspace_id)}

    # 同键不同输入：409 幂等键复用冲突。
    first = await client.post(
        f"/api/v1/assets/{asset['id']}/replace",
        headers={**headers, "Idempotency-Key": "replace-fingerprint"},
        files={"file": ("product.glb", _valid_glb(3.0), "model/gltf-binary")},
        data={"expected_file_hash": asset["file_hash"]},
    )
    assert first.status_code == 200
    conflict = await client.post(
        f"/api/v1/assets/{asset['id']}/replace",
        headers={**headers, "Idempotency-Key": "replace-fingerprint"},
        files={"file": ("product.glb", _valid_glb(4.0), "model/gltf-binary")},
        data={"expected_file_hash": first.json()["file_hash"]},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD"

    # 缺少 asset:write：403 INSUFFICIENT_SCOPE。
    readonly_token, readonly_ws = await _create_external_actor(scopes=["asset:read", "workspace:read"])
    readonly_headers = {"Authorization": f"Bearer {readonly_token}", "X-Workspace-ID": str(readonly_ws)}
    assert readonly_ws != workspace_id
    forbidden = await client.post(
        f"/api/v1/assets/{asset['id']}/replace",
        headers={**readonly_headers, "Idempotency-Key": "readonly-replace"},
        files={"file": ("product.glb", _valid_glb(5.0), "model/gltf-binary")},
        data={"expected_file_hash": asset["file_hash"]},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "INSUFFICIENT_SCOPE"

    # 跨工作空间：另一空间的有写权限令牌不能替换不属于它的资源 -> 404。
    other_token, other_ws = await _create_external_actor(scopes=["asset:read", "asset:write", "workspace:read"])
    other_headers = {"Authorization": f"Bearer {other_token}", "X-Workspace-ID": str(other_ws)}
    assert other_ws != workspace_id
    cross = await client.post(
        f"/api/v1/assets/{asset['id']}/replace",
        headers={**other_headers, "Idempotency-Key": "cross-workspace"},
        files={"file": ("product.glb", _valid_glb(6.0), "model/gltf-binary")},
        data={"expected_file_hash": asset["file_hash"]},
    )
    assert cross.status_code == 404
    assert cross.json()["code"] == "ASSET_NOT_FOUND"

    # 原资源未被跨空间请求改动。
    untouched = await client.get(f"/api/v1/assets/{asset['id']}/file", headers=headers)
    assert untouched.status_code == 200


@pytest.mark.asyncio
async def test_external_replace_rejects_invalid_glb_and_keeps_current_record(client: AsyncClient) -> None:
    """非法 GLB 内容被拒绝，当前记录与历史均不变化。"""

    token, workspace_id = await _create_external_actor(scopes=["asset:read", "asset:write", "workspace:read"])
    asset = await _external_upload_glb(client, token, workspace_id, name="product-invalid")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(workspace_id)}

    invalid = await client.post(
        f"/api/v1/assets/{asset['id']}/replace",
        headers={**headers, "Idempotency-Key": "replace-invalid"},
        files={"file": ("product.glb", b"broken-glb-bytes", "model/gltf-binary")},
        data={"expected_file_hash": asset["file_hash"]},
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "MODEL3D_FORMAT_INVALID"

    current = await client.get(f"/api/v1/assets/{asset['id']}/file", headers=headers)
    assert current.content == _valid_glb()

    async with get_session_factory()() as session:
        history_count = await session.scalar(
            select(func.count())
            .select_from(WorkspaceAsset)
            .where(WorkspaceAsset.source_asset_id == asset["id"])
        )
    assert history_count == 0
