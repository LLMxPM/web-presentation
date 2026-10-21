"""文件功能：验证 GLB 解析服务的容器校验、结构校验、预算与摘要输出。"""

from __future__ import annotations

import base64
import json
import struct
import zlib

import pytest

from app.core.exceptions import AppException
from app.services.model3d_acceptance_policy import Model3dAcceptancePolicy
from app.services.model3d_glb_service import Model3dGlbService

_JSON_CHUNK_TYPE = 0x4E4F534A
_BIN_CHUNK_TYPE = 0x004E4942


def _pad4(data: bytes, pad: bytes = b"\x00") -> bytes:
    """按 4 字节对齐填充。"""

    if len(data) % 4:
        data = data + pad * (4 - len(data) % 4)
    return data


def _build_glb(json_doc: dict | None = None, bin_chunk: bytes | None = None, *, raw_json: bytes | None = None, bin_chunk_type: int = _BIN_CHUNK_TYPE) -> bytes:
    """构造测试用 GLB 字节。"""

    if raw_json is None:
        raw_json = json.dumps(json_doc or {}).encode("utf-8")
    json_bytes = _pad4(raw_json, b" ")
    chunks = struct.pack("<II", len(json_bytes), _JSON_CHUNK_TYPE) + json_bytes
    if bin_chunk is not None:
        bin_bytes = _pad4(bin_chunk)
        chunks += struct.pack("<II", len(bin_bytes), bin_chunk_type) + bin_bytes
    total = 12 + len(chunks)
    return b"glTF" + struct.pack("<II", 2, total) + chunks


def _png_bytes(width: int, height: int) -> bytes:
    """构造真实可解析的 PNG（RGBA 纯色）。"""

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\xff\x00\x00\xff" * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def _jpeg_bytes(width: int, height: int) -> bytes:
    """构造仅带 SOF0 头的最小 JPEG 字节（供尺寸探测）。"""

    sof = b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", height, width) + b"\x03" + b"\x01\x11\x00" * 3
    return b"\xff\xd8" + sof + b"\xff\xd9"


def _triangle_position_bytes() -> bytes:
    """三个顶点的位置数据（一个三角形）。"""

    return struct.pack("<9f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def _minimal_gltf(buffer_length: int) -> dict:
    """最小合法 glTF：单场景单节点单三角形。"""

    return {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": buffer_length}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": buffer_length}],
        "accessors": [
            {
                "bufferView": 0,
                "byteOffset": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [0.0, 0.0, 0.0],
                "max": [1.0, 1.0, 0.0],
            }
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }


def _assert_rejected(content: bytes, expected_code: str, *, policy: Model3dAcceptancePolicy | None = None) -> AppException:
    """断言内容被拒绝并返回异常对象。"""

    with pytest.raises(AppException) as exc_info:
        Model3dGlbService.analyze(content, policy=policy)
    assert exc_info.value.code == expected_code
    assert exc_info.value.status_code == 400
    assert len(exc_info.value.detail) <= 240
    return exc_info.value


def test_minimal_glb_produces_summary() -> None:
    """最小合法 GLB 通过校验并输出摘要。"""

    payload = _triangle_position_bytes()
    summary = Model3dGlbService.analyze(_build_glb(_minimal_gltf(len(payload)), payload))
    assert summary["format"] == "glb"
    assert summary["gltf_version"] == "2.0"
    assert summary["scene_count"] == 1
    assert summary["default_scene_index"] == 0
    assert summary["cameras"] == []
    assert summary["animations"] == []
    assert summary["extensions_required"] == []
    assert summary["validation_profile"] == "model3d-glb-v2"
    assert summary["warnings"] == []


def test_glb_with_camera_animation_and_embedded_texture() -> None:
    """相机、动画与内嵌 PNG 纹理会进入摘要且不触发预算错误。"""

    positions = _triangle_position_bytes()
    times = struct.pack("<2f", 0.0, 1.0)
    translations = struct.pack("<6f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    png = _png_bytes(2, 2)
    buffer = positions + times + translations + png
    view_specs = [
        (0, len(positions)),
        (len(positions), len(times)),
        (len(positions) + len(times), len(translations)),
        (len(positions) + len(times) + len(translations), len(png)),
    ]
    gltf = _minimal_gltf(len(buffer))
    gltf["bufferViews"] = [{"buffer": 0, "byteOffset": offset, "byteLength": length} for offset, length in view_specs]
    gltf["accessors"] = [
        gltf["accessors"][0],
        {"bufferView": 1, "componentType": 5126, "count": 2, "type": "SCALAR", "min": [0.0], "max": [1.0]},
        {"bufferView": 2, "componentType": 5126, "count": 2, "type": "VEC3"},
    ]
    gltf["cameras"] = [{"type": "perspective", "perspective": {"yfov": 0.7, "znear": 0.1}, "name": "MainCam"}]
    gltf["animations"] = [
        {
            "name": "Idle",
            "samplers": [{"input": 1, "output": 2}],
            "channels": [{"sampler": 0, "target": {"node": 0, "path": "translation"}}],
        }
    ]
    gltf["images"] = [{"bufferView": 3, "mimeType": "image/png"}]
    gltf["samplers"] = [{}]
    gltf["textures"] = [{"source": 0, "sampler": 0}]
    gltf["materials"] = [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}]
    gltf["meshes"][0]["primitives"][0]["material"] = 0

    summary = Model3dGlbService.analyze(_build_glb(gltf, buffer))
    assert summary["cameras"] == [{"index": 0, "name": "MainCam", "type": "perspective"}]
    [animation] = summary["animations"]
    assert animation["index"] == 0
    assert animation["name"] == "Idle"
    assert animation["channel_count"] == 1
    assert animation["duration_ms"] == 1000
    assert animation["target_paths"] == ["translation"]
    assert animation["supported"] is True
    assert animation["unsupported_reasons"] == []
    assert len(animation["signature"]) == 32
    assert summary["animation_analysis_version"] == 2


def test_data_uri_buffer_is_self_contained_and_valid() -> None:
    """buffer 使用 data URI 且长度一致时按自包含通过。"""

    positions = _triangle_position_bytes()
    encoded = "data:application/octet-stream;base64," + base64.b64encode(positions).decode("ascii")
    gltf = _minimal_gltf(len(positions))
    gltf["buffers"] = [{"byteLength": len(positions), "uri": encoded}]
    Model3dGlbService.analyze(_build_glb(gltf))


def test_rejects_bad_magic() -> None:
    """缺少 glTF magic 的字节被拒绝。"""

    _assert_rejected(b"XXXX" + b"\x00" * 20, "MODEL3D_FORMAT_INVALID")


def test_rejects_truncated_header() -> None:
    """长度不足 12 字节的文件被拒绝。"""

    _assert_rejected(b"glTF\x02\x00", "MODEL3D_FORMAT_INVALID")


def test_rejects_wrong_container_version() -> None:
    """非 2.0 二进制容器被拒绝。"""

    payload = _triangle_position_bytes()
    content = bytearray(_build_glb(_minimal_gltf(len(payload)), payload))
    struct.pack_into("<I", content, 4, 1)
    _assert_rejected(bytes(content), "MODEL3D_FORMAT_INVALID")


def test_rejects_total_length_mismatch() -> None:
    """声明总长度与实际不一致被拒绝。"""

    payload = _triangle_position_bytes()
    content = bytearray(_build_glb(_minimal_gltf(len(payload)), payload))
    struct.pack_into("<I", content, 8, len(content) + 4)
    _assert_rejected(bytes(content), "MODEL3D_FORMAT_INVALID")


def test_rejects_unaligned_chunk() -> None:
    """chunk 长度未按 4 字节对齐被拒绝。"""

    raw_json = b'{"asset":{"version":"2.0"}}'  # 27 字节，未对齐
    chunks = struct.pack("<II", len(raw_json), _JSON_CHUNK_TYPE) + raw_json
    content = b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks
    _assert_rejected(content, "MODEL3D_FORMAT_INVALID")


def test_rejects_missing_json_chunk() -> None:
    """第一个 chunk 不是 JSON 被拒绝。"""

    bin_bytes = _pad4(b"\x00\x00\x00\x00")
    chunks = struct.pack("<II", len(bin_bytes), _BIN_CHUNK_TYPE) + bin_bytes
    content = b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks
    _assert_rejected(content, "MODEL3D_FORMAT_INVALID")


def test_rejects_duplicate_json_chunk() -> None:
    """出现第二个 JSON chunk 被拒绝。"""

    json_bytes = _pad4(b'{"asset":{"version":"2.0"}}', b" ")
    chunks = struct.pack("<II", len(json_bytes), _JSON_CHUNK_TYPE) + json_bytes
    chunks += struct.pack("<II", len(json_bytes), _JSON_CHUNK_TYPE) + json_bytes
    content = b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks
    _assert_rejected(content, "MODEL3D_FORMAT_INVALID")


def test_rejects_json_chunk_over_budget() -> None:
    """JSON chunk 超过策略上限被拒绝。"""

    policy = Model3dAcceptancePolicy(max_json_chunk_bytes=4)
    _assert_rejected(_build_glb({"asset": {"version": "2.0"}}), "MODEL3D_LIMIT_EXCEEDED", policy=policy)


def test_rejects_json_nan_literal() -> None:
    """JSON 中出现 NaN 常量被拒绝。"""

    _assert_rejected(_build_glb(raw_json=b'{"asset":{"version":NaN}}'), "MODEL3D_FORMAT_INVALID")


def test_rejects_json_array_root() -> None:
    """JSON 顶层不是对象被拒绝。"""

    _assert_rejected(_build_glb(raw_json=b"[]"), "MODEL3D_FORMAT_INVALID")


def test_rejects_file_over_budget() -> None:
    """文件超过策略上限被拒绝。"""

    policy = Model3dAcceptancePolicy(max_file_bytes=8)
    _assert_rejected(_build_glb({"asset": {"version": "2.0"}}), "MODEL3D_LIMIT_EXCEEDED", policy=policy)


def test_rejects_unknown_required_extension() -> None:
    """未列入白名单的必需扩展被拒绝。"""

    gltf = {"asset": {"version": "2.0"}, "extensionsUsed": ["KHR_draco_mesh_compression"], "extensionsRequired": ["KHR_draco_mesh_compression"]}
    _assert_rejected(_build_glb(gltf), "MODEL3D_EXTENSION_UNSUPPORTED")


def test_allowlisted_required_extension_passes_and_optional_unknown_warns() -> None:
    """白名单必需扩展通过；未知可选扩展降级为 warning。"""

    gltf = {
        "asset": {"version": "2.0"},
        "extensionsUsed": ["KHR_materials_unlit", "KHR_texture_transform"],
        "extensionsRequired": ["KHR_materials_unlit"],
    }
    summary = Model3dGlbService.analyze(_build_glb(gltf))
    assert summary["extensions_required"] == ["KHR_materials_unlit"]
    assert any("KHR_texture_transform" in item for item in summary["warnings"])


def test_rejects_required_extension_missing_from_used() -> None:
    """extensionsRequired 未在 extensionsUsed 声明被拒绝。"""

    gltf = {"asset": {"version": "2.0"}, "extensionsRequired": ["KHR_materials_unlit"]}
    _assert_rejected(_build_glb(gltf), "MODEL3D_FORMAT_INVALID")


def test_rejects_external_buffer_uri() -> None:
    """buffer 引用外部文件被拒绝。"""

    gltf = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 4, "uri": "scene.bin"}]}
    _assert_rejected(_build_glb(gltf), "MODEL3D_EXTERNAL_URI_FORBIDDEN")


def test_rejects_second_buffer_without_uri() -> None:
    """只有 buffers[0] 可以省略 uri。"""

    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": 4}, {"byteLength": 4}],
    }
    _assert_rejected(_build_glb(gltf, b"\x00\x00\x00\x00"), "MODEL3D_FORMAT_INVALID")


def test_rejects_buffer_length_mismatch_with_bin() -> None:
    """buffers[0] 长度超出 BIN chunk 被拒绝。"""

    gltf = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 64}]}
    _assert_rejected(_build_glb(gltf, b"\x00" * 4), "MODEL3D_FORMAT_INVALID")


def test_rejects_view_out_of_range() -> None:
    """bufferView 范围越界被拒绝。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    gltf["bufferViews"] = [{"buffer": 0, "byteOffset": 8, "byteLength": len(payload)}]
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")


def test_rejects_accessor_alignment_violation() -> None:
    """accessor 偏移未按组件大小对齐被拒绝。"""

    payload = _triangle_position_bytes() * 2
    gltf = _minimal_gltf(len(payload))
    gltf["accessors"] = [{**gltf["accessors"][0], "byteOffset": 2}]
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")


def test_rejects_accessor_out_of_view() -> None:
    """accessor 数据范围超出 bufferView 被拒绝。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    gltf["accessors"] = [{**gltf["accessors"][0], "count": 6}]
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")


def test_rejects_node_cycle() -> None:
    """节点父子环被拒绝。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    gltf["nodes"] = [{"mesh": 0, "children": [1]}, {"children": [0]}]
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")


def test_rejects_node_matrix_with_trs() -> None:
    """matrix 与 TRS 同时声明被拒绝。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    gltf["nodes"] = [{"mesh": 0, "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], "translation": [0, 0, 0]}]
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")


def test_rejects_node_over_budget() -> None:
    """节点数量超过策略上限被拒绝。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    policy = Model3dAcceptancePolicy(max_nodes=0)
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_LIMIT_EXCEEDED", policy=policy)


def test_rejects_triangle_over_budget() -> None:
    """三角形数量超过策略上限被拒绝。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    policy = Model3dAcceptancePolicy(max_triangles=0)
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_LIMIT_EXCEEDED", policy=policy)


@pytest.mark.parametrize(
    "case",
    ["accessor_component_type", "accessor_type", "camera_type", "animation_target_path"],
)
def test_rejects_unhashable_values_before_membership_checks(case: str) -> None:
    """数组等不可哈希取值必须返回 400，而不是在字典/集合成员判断时抛 TypeError。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    if case == "accessor_component_type":
        gltf["accessors"][0]["componentType"] = []
    elif case == "accessor_type":
        gltf["accessors"][0]["type"] = []
    elif case == "camera_type":
        gltf["cameras"] = [{"type": []}]
    else:
        gltf["animations"] = [
            {
                "samplers": [{"input": 0, "output": 0}],
                "channels": [{"sampler": 0, "target": {"node": 0, "path": []}}],
            }
        ]
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")


@pytest.mark.parametrize("case", ["camera_yfov", "accessor_min", "node_translation"])
def test_rejects_oversized_json_integers(case: str) -> None:
    """超出 float 范围的整数不得触发 OverflowError，必须返回 400。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    huge = 10 ** 400
    if case == "camera_yfov":
        gltf["cameras"] = [{"type": "perspective", "perspective": {"yfov": huge, "znear": 0.1}}]
    elif case == "accessor_min":
        gltf["accessors"][0]["min"] = [huge, 0, 0]
    else:
        gltf["nodes"][0]["translation"] = [huge, 0, 0]
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")


def test_triangle_budget_counts_mesh_instances_per_node() -> None:
    """同一 mesh 被多个节点实例化时，三角形预算必须按实例数累计。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    gltf["nodes"] = [{"mesh": 0}, {"mesh": 0}, {"mesh": 0}, {"mesh": 0}]
    gltf["scenes"] = [{"nodes": [0, 1, 2, 3]}]
    gltf["scene"] = 0
    # 单实例 1 个三角形；四个节点实例化后总数 4，必须超过 max_triangles=1。
    _assert_rejected(
        _build_glb(gltf, payload),
        "MODEL3D_LIMIT_EXCEEDED",
        policy=Model3dAcceptancePolicy(max_triangles=1),
    )

    # 未超过预算的实例数仍然通过。
    summary = Model3dGlbService.analyze(
        _build_glb(gltf, payload),
        policy=Model3dAcceptancePolicy(max_triangles=4),
    )
    assert summary["format"] == "glb"


def test_rejects_external_image_uri() -> None:
    """图片引用外部文件被拒绝。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    gltf["images"] = [{"uri": "textures/base.png"}]
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_EXTERNAL_URI_FORBIDDEN")


def test_rejects_unsupported_embedded_image_type() -> None:
    """非 PNG/JPEG 的内嵌图片被拒绝。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    gltf["images"] = [{"uri": "data:image/webp;base64,AAAA"}]
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")


def test_rejects_buffer_view_image_without_mime() -> None:
    """bufferView 图片缺少 mimeType 被拒绝。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    gltf["bufferViews"] = [*gltf["bufferViews"], {"buffer": 0, "byteOffset": 0, "byteLength": 8}]
    gltf["images"] = [{"bufferView": 1}]
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")


def test_rejects_texture_edge_over_budget() -> None:
    """纹理单边超过策略上限被拒绝。"""

    png = _png_bytes(2, 2)
    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(png), "uri": "data:image/png;base64," + base64.b64encode(png).decode("ascii")}],
        "images": [{"bufferView": 0, "mimeType": "image/png"}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(png)}],
    }
    policy = Model3dAcceptancePolicy(max_texture_edge=1)
    _assert_rejected(_build_glb(gltf), "MODEL3D_LIMIT_EXCEEDED", policy=policy)


def test_rejects_texture_pixels_over_budget() -> None:
    """纹理解码总像素超过策略上限被拒绝。"""

    png = _png_bytes(2, 2)
    encoded = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(png), "uri": encoded}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(png)}],
        "images": [{"bufferView": 0, "mimeType": "image/png"}],
    }
    policy = Model3dAcceptancePolicy(max_texture_pixels=3)
    _assert_rejected(_build_glb(gltf), "MODEL3D_LIMIT_EXCEEDED", policy=policy)


def test_jpeg_dimensions_supported() -> None:
    """JPEG 内嵌图片按 SOF 头解析尺寸并通过校验。"""

    jpeg = _jpeg_bytes(4, 3)
    encoded = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(jpeg), "uri": encoded}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(jpeg)}],
        "images": [{"bufferView": 0, "mimeType": "image/jpeg"}],
    }
    Model3dGlbService.analyze(_build_glb(gltf))


def test_rejects_corrupt_embedded_image() -> None:
    """内嵌图片头无法解析被拒绝。"""

    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": 16, "uri": "data:image/png;base64," + base64.b64encode(b"\x00" * 16).decode("ascii")}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 16}],
        "images": [{"bufferView": 0, "mimeType": "image/png"}],
    }
    _assert_rejected(_build_glb(gltf), "MODEL3D_FORMAT_INVALID")


def test_rejects_default_scene_out_of_range() -> None:
    """scene 默认场景索引越界被拒绝。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    gltf["scene"] = 3
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")


def test_rejects_higher_min_version() -> None:
    """minVersion 高于 2.0 被拒绝。"""

    _assert_rejected(_build_glb({"asset": {"version": "2.0", "minVersion": "3.0"}}), "MODEL3D_FORMAT_INVALID")


@pytest.mark.parametrize("version", ["2", "2.0.0", "02.0", "2.x", " 2.0"])
def test_rejects_non_schema_asset_version(version: str) -> None:
    """asset.version 必须严格符合 glTF 官方 <major>.<minor> 格式。"""

    _assert_rejected(_build_glb({"asset": {"version": version}}), "MODEL3D_FORMAT_INVALID")


@pytest.mark.parametrize("min_version", ["2", "2.0.0", "02.0", "3.0.0"])
def test_rejects_non_schema_min_version(min_version: str) -> None:
    """asset.minVersion 同样必须是 <major>.<minor> 格式。"""

    _assert_rejected(
        _build_glb({"asset": {"version": "2.0", "minVersion": min_version}}),
        "MODEL3D_FORMAT_INVALID",
    )


def test_accepts_schema_min_version() -> None:
    """合法的 minVersion=2.0 不触发格式错误。"""

    summary = Model3dGlbService.analyze(_build_glb({"asset": {"version": "2.0", "minVersion": "2.0"}}))
    assert summary["gltf_version"] == "2.0"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("meshes", 5),
        ("cameras", 5),
        ("skins", 5),
        ("materials", 5),
    ],
)
def test_rejects_non_array_top_level_collections(field: str, value: int) -> None:
    """顶级集合声明为标量时必须返回 400，而不是 TypeError。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    gltf[field] = value
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")


@pytest.mark.parametrize(
    ("camera", "projection_key"),
    [
        ({"type": "perspective", "perspective": "bad"}, "perspective"),
        ({"type": "orthographic", "orthographic": ["bad"]}, "orthographic"),
        ({"type": "perspective", "perspective": 1}, "perspective"),
    ],
)
def test_rejects_non_object_camera_projection(camera: dict, projection_key: str) -> None:
    """相机投影声明不是对象时必须返回 400，而不是 AttributeError。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    gltf["cameras"] = [camera]
    error = _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")
    assert projection_key in error.detail


def test_rejects_primitive_without_position() -> None:
    """primitive 缺少 POSITION 被拒绝。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    gltf["meshes"] = [{"primitives": [{"attributes": {"NORMAL": 0}}]}]
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")


def test_rejects_bad_camera_parameters() -> None:
    """相机投影参数非法被拒绝。"""

    gltf = {"asset": {"version": "2.0"}, "cameras": [{"type": "perspective", "perspective": {"yfov": 0, "znear": 0.1}}]}
    _assert_rejected(_build_glb(gltf), "MODEL3D_FORMAT_INVALID")


def test_rejects_animation_target_path_invalid() -> None:
    """动画目标路径非法被拒绝。"""

    payload = _triangle_position_bytes()
    gltf = _minimal_gltf(len(payload))
    gltf["accessors"] = [
        gltf["accessors"][0],
        {"bufferView": 0, "componentType": 5126, "count": 3, "type": "SCALAR"},
    ]
    gltf["animations"] = [{"samplers": [{"input": 1, "output": 1}], "channels": [{"sampler": 0, "target": {"node": 0, "path": "opacity"}}]}]
    _assert_rejected(_build_glb(gltf, payload), "MODEL3D_FORMAT_INVALID")


def _animated_gltf(
    *,
    times: list[float],
    translations: list[tuple[float, float, float]],
    interpolation: str | None = None,
    output_count: int | None = None,
    png_size: tuple[int, int] = (2, 2),
) -> tuple[dict, bytes]:
    """构造带真实动画采样数据的自包含 GLB 描述。"""

    positions = _triangle_position_bytes()
    time_bytes = struct.pack(f"<{len(times)}f", *times)
    translation_values = list(translations)
    if output_count is not None:
        if output_count < len(translation_values):
            translation_values = translation_values[:output_count]
        else:
            translation_values.extend([(0.0, 0.0, 0.0)] * (output_count - len(translation_values)))
    translation_bytes = b"".join(struct.pack("<3f", *value) for value in translation_values)
    png = _png_bytes(*png_size)
    buffer = positions + time_bytes + translation_bytes + png
    views = [
        (0, len(positions)),
        (len(positions), len(time_bytes)),
        (len(positions) + len(time_bytes), len(translation_bytes)),
        (len(positions) + len(time_bytes) + len(translation_bytes), len(png)),
    ]
    gltf = _minimal_gltf(len(buffer))
    gltf["bufferViews"] = [{"buffer": 0, "byteOffset": offset, "byteLength": length} for offset, length in views]
    gltf["accessors"] = [
        gltf["accessors"][0],
        {"bufferView": 1, "componentType": 5126, "count": len(times), "type": "SCALAR"},
        {"bufferView": 2, "componentType": 5126, "count": len(translation_values), "type": "VEC3"},
    ]
    sampler = {"input": 1, "output": 2}
    if interpolation is not None:
        sampler["interpolation"] = interpolation
    gltf["animations"] = [
        {
            "name": "Idle",
            "samplers": [sampler],
            "channels": [{"sampler": 0, "target": {"node": 0, "path": "translation"}}],
        }
    ]
    gltf["images"] = [{"bufferView": 3, "mimeType": "image/png"}]
    gltf["samplers"] = [{}]
    gltf["textures"] = [{"source": 0, "sampler": 0}]
    gltf["materials"] = [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}]
    gltf["meshes"][0]["primitives"][0]["material"] = 0
    return gltf, buffer


def test_animation_signature_ignores_texture_changes() -> None:
    """纹理变化但动作不变时动作签名保持一致。"""

    gltf_a, buffer_a = _animated_gltf(times=[0.0, 1.0], translations=[(0, 0, 0), (1, 0, 0)], png_size=(2, 2))
    gltf_b, buffer_b = _animated_gltf(times=[0.0, 1.0], translations=[(0, 0, 0), (1, 0, 0)], png_size=(2, 3))
    signature_a = Model3dGlbService.analyze(_build_glb(gltf_a, buffer_a))["animations"][0]["signature"]
    signature_b = Model3dGlbService.analyze(_build_glb(gltf_b, buffer_b))["animations"][0]["signature"]
    assert signature_a == signature_b


def test_animation_signature_changes_with_action_values() -> None:
    """同一索引的动作值变化时必须产生不同签名。"""

    gltf_a, buffer_a = _animated_gltf(times=[0.0, 1.0], translations=[(0, 0, 0), (1, 0, 0)])
    gltf_b, buffer_b = _animated_gltf(times=[0.0, 1.0], translations=[(0, 0, 0), (2, 0, 0)])
    summary_a = Model3dGlbService.analyze(_build_glb(gltf_a, buffer_a))
    summary_b = Model3dGlbService.analyze(_build_glb(gltf_b, buffer_b))
    assert summary_a["animations"][0]["signature"] != summary_b["animations"][0]["signature"]
    assert summary_a["animations"][0]["duration_ms"] == 1000


def test_animation_non_monotonic_input_is_unsupported() -> None:
    """输入时间非递增时动作不可执行，但资源仍可读取。"""

    gltf, buffer = _animated_gltf(times=[1.0, 0.0], translations=[(0, 0, 0), (1, 0, 0)])
    animation = Model3dGlbService.analyze(_build_glb(gltf, buffer))["animations"][0]
    assert animation["supported"] is False
    assert "NON_MONOTONIC_INPUT" in animation["unsupported_reasons"]
    assert animation["signature"] == ""


def test_animation_output_count_mismatch_is_unsupported() -> None:
    """LINEAR 输出数量与输入不一致时动作不可执行。"""

    gltf, buffer = _animated_gltf(times=[0.0, 1.0], translations=[(0, 0, 0), (1, 0, 0)], output_count=3)
    animation = Model3dGlbService.analyze(_build_glb(gltf, buffer))["animations"][0]
    assert animation["supported"] is False
    assert "OUTPUT_COUNT_MISMATCH" in animation["unsupported_reasons"]


def test_animation_unknown_interpolation_is_unsupported() -> None:
    """未知插值不伪装成可用动作。"""

    gltf, buffer = _animated_gltf(
        times=[0.0, 1.0],
        translations=[(0, 0, 0), (1, 0, 0)],
        interpolation="CUSTOM",
    )
    animation = Model3dGlbService.analyze(_build_glb(gltf, buffer))["animations"][0]
    assert animation["supported"] is False
    assert "INTERPOLATION_UNSUPPORTED" in animation["unsupported_reasons"]


def test_animation_cubic_spline_output_count() -> None:
    """CUBICSPLINE 输出按输入数量的 3 倍校验。"""

    gltf, buffer = _animated_gltf(
        times=[0.0, 1.0],
        translations=[(0, 0, 0), (0.5, 0, 0), (1, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0)],
        interpolation="CUBICSPLINE",
        output_count=6,
    )
    animation = Model3dGlbService.analyze(_build_glb(gltf, buffer))["animations"][0]
    assert animation["supported"] is True
    assert animation["duration_ms"] == 1000
