"""文件功能：解析并校验 glTF 2.0 二进制 GLB 资源，产出有界分析摘要与预算校验。"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
import struct
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote_to_bytes

from app.core.exceptions import AppException
from app.services.model3d_acceptance_policy import (
    MODEL3D_ACCEPTANCE_POLICY,
    MODEL3D_ERROR_EXTENSION_UNSUPPORTED,
    MODEL3D_ERROR_EXTERNAL_URI_FORBIDDEN,
    MODEL3D_ERROR_FORMAT_INVALID,
    MODEL3D_ERROR_LIMIT_EXCEEDED,
    Model3dAcceptancePolicy,
)
from app.services.model3d_structure_limits import (
    assert_acyclic_nodes,
    validate_accessor_decoded_budget,
)

_GLB_MAGIC = b"glTF"
_GLB_VERSION = 2
_CHUNK_TYPE_JSON = 0x4E4F534A
_CHUNK_TYPE_BIN = 0x004E4942

_COMPONENT_TYPE_BYTES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
_ACCESSOR_TYPE_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
_INDEX_COMPONENT_TYPES = {5121, 5123, 5125}
_PRIMITIVE_MODES = {0, 1, 2, 3, 4, 5, 6}
_ANIMATION_TARGET_PATHS = {"translation", "rotation", "scale", "weights"}

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}

_MAX_DETAIL_LENGTH = 220
# glTF 官方 schema 要求 version/minVersion 为 <major>.<minor>，例如 "2.0"；"2" 与 "2.0.0" 均非法。
_GLTF_VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})$")


def _is_int(value: Any) -> bool:
    """判断值是否为整数（排除布尔）。"""

    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    """判断值是否为有限数值（排除布尔与 NaN/Infinity）。

    JSON 允许任意精度整数；超出 float 范围的值在 math.isfinite 转换时会抛
    OverflowError，必须同样视为非法数值而不是让异常穿透校验边界。
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _format_invalid(detail: str) -> AppException:
    """构造格式非法错误（有界 detail）。"""

    return AppException(status_code=400, code=MODEL3D_ERROR_FORMAT_INVALID, detail=detail[:_MAX_DETAIL_LENGTH])


def _limit_exceeded(detail: str) -> AppException:
    """构造预算超限错误（有界 detail）。"""

    return AppException(status_code=400, code=MODEL3D_ERROR_LIMIT_EXCEEDED, detail=detail[:_MAX_DETAIL_LENGTH])


def _extension_unsupported(detail: str) -> AppException:
    """构造必需扩展不支持错误。"""

    return AppException(status_code=400, code=MODEL3D_ERROR_EXTENSION_UNSUPPORTED, detail=detail[:_MAX_DETAIL_LENGTH])


def _external_uri_forbidden(detail: str) -> AppException:
    """构造外部依赖拒绝错误。"""

    return AppException(status_code=400, code=MODEL3D_ERROR_EXTERNAL_URI_FORBIDDEN, detail=detail[:_MAX_DETAIL_LENGTH])


def _array_length(root: dict[str, Any], key: str) -> int:
    """读取可选顶级数组的长度；缺失或 null 视为空数组，非数组明确按格式非法拒绝。"""

    value = root.get(key)
    if value is None:
        return 0
    if not isinstance(value, list):
        raise _format_invalid(f"{key} 必须是数组。")
    return len(value)


@dataclass(frozen=True, slots=True)
class _GlbContainer:
    """GLB 容器解析结果。"""

    json_data: dict[str, Any]
    bin_bytes: bytes


@dataclass(frozen=True, slots=True)
class _BufferInfo:
    """buffer 声明与可访问数据。"""

    byte_length: int
    data: bytes


@dataclass(frozen=True, slots=True)
class _BufferViewInfo:
    """bufferView 校验后的定位信息。"""

    buffer_index: int
    byte_offset: int
    byte_length: int
    byte_stride: int | None


@dataclass(frozen=True, slots=True)
class _ImageInfo:
    """图片成员与解码后字节。"""

    data: bytes
    mime_type: str


class Model3dGlbService:
    """glTF 2.0 GLB 容器解析、结构校验与静态分析摘要生成。"""

    @classmethod
    def analyze(cls, content: bytes, *, policy: Model3dAcceptancePolicy | None = None) -> dict[str, Any]:
        """校验 GLB 内容并返回可写入 analysis_metadata 的 model3d 摘要。"""

        resolved_policy = policy or MODEL3D_ACCEPTANCE_POLICY
        if len(content) > resolved_policy.max_file_bytes:
            raise _limit_exceeded(f"三维资源文件超过上限 {resolved_policy.max_file_bytes} 字节。")
        container = cls._parse_container(content, policy=resolved_policy)
        warnings = cls._validate_json_structure(container.json_data, container.bin_bytes, policy=resolved_policy)
        return cls._build_summary(container.json_data, warnings, policy=resolved_policy)

    # ------------------------------------------------------------------
    # 容器层
    # ------------------------------------------------------------------

    @staticmethod
    def _reject_json_constant(token: str) -> None:
        """拒绝 JSON 中的 NaN/Infinity 字面量，保持与 JSON 规范一致。"""

        raise ValueError(f"JSON 不允许常量 {token}。")

    @classmethod
    def _parse_container(cls, content: bytes, *, policy: Model3dAcceptancePolicy) -> _GlbContainer:
        """解析 GLB 头部与 chunk，校验 JSON 与 BIN 结构。"""

        if len(content) < 12 or content[:4] != _GLB_MAGIC:
            raise _format_invalid("文件头不是合法的 GLB（缺少 glTF magic）。")
        version, total_length = struct.unpack_from("<II", content, 4)
        if version != _GLB_VERSION:
            raise _format_invalid(f"仅支持 glTF 2.0 二进制容器，文件声明版本 {version}。")
        if total_length != len(content):
            raise _format_invalid("GLB 声明总长度与实际文件大小不一致。")

        offset = 12
        json_chunk: bytes | None = None
        bin_chunk: bytes | None = None
        while offset < len(content):
            if offset + 8 > len(content):
                raise _format_invalid("GLB chunk 头越界。")
            chunk_length, chunk_type = struct.unpack_from("<II", content, offset)
            offset += 8
            if chunk_length % 4 != 0:
                raise _format_invalid("GLB chunk 长度必须按 4 字节对齐。")
            if offset + chunk_length > len(content):
                raise _format_invalid("GLB chunk 数据超出文件长度。")
            chunk_data = content[offset:offset + chunk_length]
            offset += chunk_length

            if json_chunk is None:
                if chunk_type != _CHUNK_TYPE_JSON:
                    raise _format_invalid("GLB 第一个 chunk 必须是 JSON。")
                json_chunk = chunk_data
                continue
            if chunk_type == _CHUNK_TYPE_JSON:
                raise _format_invalid("GLB 不允许出现第二个 JSON chunk。")
            if chunk_type == _CHUNK_TYPE_BIN and bin_chunk is None:
                bin_chunk = chunk_data
            # 其余未知 chunk 类型按 glTF 规范忽略。

        if json_chunk is None:
            raise _format_invalid("GLB 缺少 JSON chunk。")
        if len(json_chunk) > policy.max_json_chunk_bytes:
            raise _limit_exceeded(f"JSON chunk 超过上限 {policy.max_json_chunk_bytes} 字节。")
        try:
            text = json_chunk.decode("utf-8")
        except UnicodeDecodeError as error:
            raise _format_invalid("GLB JSON chunk 不是合法 UTF-8。") from error
        try:
            json_data = json.loads(text, parse_constant=cls._reject_json_constant)
        except ValueError as error:
            raise _format_invalid("GLB JSON chunk 不是合法 JSON。") from error
        if not isinstance(json_data, dict):
            raise _format_invalid("glTF JSON 顶层必须是对象。")
        return _GlbContainer(json_data=json_data, bin_bytes=bin_chunk or b"")

    # ------------------------------------------------------------------
    # 结构校验
    # ------------------------------------------------------------------

    @classmethod
    def _validate_json_structure(
        cls,
        root: dict[str, Any],
        bin_bytes: bytes,
        *,
        policy: Model3dAcceptancePolicy,
    ) -> list[str]:
        """校验 glTF JSON 结构与引用范围，返回可选扩展降级提示。"""

        cls._validate_asset(root)
        warnings = cls._validate_extensions(root, policy)
        buffers = cls._validate_buffers(root, bin_bytes)
        views = cls._validate_buffer_views(root, buffers)
        accessors = cls._validate_accessors(root, buffers, views)
        validate_accessor_decoded_budget(
            (
                (accessor["count"], _COMPONENT_TYPE_BYTES[accessor["componentType"]] * _ACCESSOR_TYPE_COMPONENTS[accessor["type"]])
                for accessor in accessors
            ),
            policy=policy,
        )
        cls._validate_nodes_and_scenes(root, policy)
        cls._validate_meshes(root, accessors, policy)
        images = cls._validate_images(root, buffers, views, policy)
        cls._validate_textures(root, images)
        cls._validate_materials(root)
        cls._validate_cameras(root)
        cls._validate_animations(root)
        cls._validate_texture_budget(images, policy)
        return warnings

    @staticmethod
    def _validate_asset(root: dict[str, Any]) -> None:
        """校验 asset 声明与 glTF 版本。"""

        asset = root.get("asset")
        if not isinstance(asset, dict):
            raise _format_invalid("glTF 缺少 asset 对象。")
        version = asset.get("version")
        if not isinstance(version, str) or not _GLTF_VERSION_PATTERN.fullmatch(version):
            raise _format_invalid("asset.version 必须是 <major>.<minor> 格式的 glTF 版本，如 2.0。")
        if int(version.split(".", 1)[0]) != 2:
            raise _format_invalid("asset.version 必须为 glTF 2.x。")
        min_version = asset.get("minVersion")
        if min_version is not None:
            if not isinstance(min_version, str) or not _GLTF_VERSION_PATTERN.fullmatch(min_version):
                raise _format_invalid("asset.minVersion 必须是 <major>.<minor> 格式的字符串。")
            parts = tuple(int(part) for part in min_version.split("."))
            if parts > (2, 0):
                raise _format_invalid(f"文件要求 glTF {min_version}，超出首期支持范围。")

    @staticmethod
    def _validate_extensions(root: dict[str, Any], policy: Model3dAcceptancePolicy) -> list[str]:
        """校验扩展声明：必需扩展必须命中白名单，可选未知扩展降级为 warning。"""

        used = root.get("extensionsUsed", [])
        required = root.get("extensionsRequired", [])
        if not isinstance(used, list) or not all(isinstance(item, str) for item in used):
            raise _format_invalid("extensionsUsed 必须是字符串数组。")
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise _format_invalid("extensionsRequired 必须是字符串数组。")

        for name in required:
            if name not in policy.required_extension_allowlist:
                raise _extension_unsupported(f"必需的 glTF 扩展 {name} 不在首期支持范围内。")
            if name not in used:
                raise _format_invalid(f"扩展 {name} 出现在 extensionsRequired 但缺少 extensionsUsed 声明。")

        warnings: list[str] = []
        for name in used:
            if name not in policy.required_extension_allowlist:
                warnings.append(f"可选扩展 {name} 未列入验证范围，渲染时按规范降级处理。")
        return warnings

    @classmethod
    def _validate_buffers(cls, root: dict[str, Any], bin_bytes: bytes) -> list[_BufferInfo]:
        """校验 buffers 声明、自包含性与长度一致性。"""

        buffers = root.get("buffers", [])
        if not isinstance(buffers, list):
            raise _format_invalid("buffers 必须是数组。")
        result: list[_BufferInfo] = []
        for index, buffer in enumerate(buffers):
            if not isinstance(buffer, dict):
                raise _format_invalid(f"buffers[{index}] 必须是对象。")
            byte_length = buffer.get("byteLength")
            if not _is_int(byte_length) or byte_length < 0:
                raise _format_invalid(f"buffers[{index}].byteLength 必须是非负整数。")
            uri = buffer.get("uri")
            if uri is None:
                if index != 0:
                    raise _format_invalid("只有 buffers[0] 可以省略 uri 并使用 GLB BIN chunk。")
                if byte_length > len(bin_bytes):
                    raise _format_invalid("buffers[0] 声明长度超出 BIN chunk 实际长度。")
                if len(bin_bytes) - byte_length > 3:
                    raise _format_invalid("BIN chunk 超出 buffers[0] 长度的填充不得超过 3 字节。")
                result.append(_BufferInfo(byte_length=byte_length, data=bin_bytes[:byte_length]))
                continue
            if not isinstance(uri, str):
                raise _format_invalid(f"buffers[{index}].uri 必须是字符串。")
            if not uri.startswith("data:"):
                raise _external_uri_forbidden(f"buffers[{index}] 引用了外部文件，首期只接受自包含 GLB。")
            payload = cls._decode_data_uri(uri, field=f"buffers[{index}]")
            if len(payload) != byte_length:
                raise _format_invalid(f"buffers[{index}] 声明长度与 data URI 实际长度不一致。")
            result.append(_BufferInfo(byte_length=byte_length, data=payload))
        return result

    @staticmethod
    def _decode_data_uri(uri: str, *, field: str) -> bytes:
        """解码 data URI 载荷（base64 或百分号编码）。"""

        header, separator, payload = uri.partition(",")
        if not separator or not header.startswith("data:"):
            raise _format_invalid(f"{field} 的 data URI 格式非法。")
        try:
            if header.endswith(";base64"):
                # validate=True：非法字符显式失败，不让畸形 data URI 静默通过长度对拍。
                return base64.b64decode(payload, validate=True)
            return unquote_to_bytes(payload)
        except (binascii.Error, ValueError) as error:
            raise _format_invalid(f"{field} 的 data URI 载荷无法解码。") from error

    @staticmethod
    def _data_uri_media_type(uri: str) -> str:
        """提取 data URI 的媒体类型（不含参数）。"""

        header = uri.partition(",")[0]
        media = header[len("data:"):].split(";", 1)[0].strip().lower()
        return media

    @classmethod
    def _validate_buffer_views(cls, root: dict[str, Any], buffers: list[_BufferInfo]) -> list[_BufferViewInfo]:
        """校验 bufferViews 的引用范围与步长约束。"""

        views = root.get("bufferViews", [])
        if not isinstance(views, list):
            raise _format_invalid("bufferViews 必须是数组。")
        result: list[_BufferViewInfo] = []
        for index, view in enumerate(views):
            if not isinstance(view, dict):
                raise _format_invalid(f"bufferViews[{index}] 必须是对象。")
            buffer_index = view.get("buffer")
            if not _is_int(buffer_index) or not 0 <= buffer_index < len(buffers):
                raise _format_invalid(f"bufferViews[{index}].buffer 索引越界。")
            byte_offset = view.get("byteOffset", 0)
            byte_length = view.get("byteLength")
            if not _is_int(byte_offset) or byte_offset < 0:
                raise _format_invalid(f"bufferViews[{index}].byteOffset 必须是非负整数。")
            if not _is_int(byte_length) or byte_length < 1:
                raise _format_invalid(f"bufferViews[{index}].byteLength 必须是正整数。")
            if byte_offset + byte_length > buffers[buffer_index].byte_length:
                raise _format_invalid(f"bufferViews[{index}] 引用范围超出 buffers[{buffer_index}]。")
            byte_stride = view.get("byteStride")
            if byte_stride is not None and (
                not _is_int(byte_stride) or not 4 <= byte_stride <= 252 or byte_stride % 4 != 0
            ):
                raise _format_invalid(f"bufferViews[{index}].byteStride 必须是 4 到 252 之间的 4 字节倍数。")
            result.append(
                _BufferViewInfo(
                    buffer_index=buffer_index,
                    byte_offset=byte_offset,
                    byte_length=byte_length,
                    byte_stride=byte_stride,
                )
            )
        return result

    @classmethod
    def _validate_accessors(
        cls,
        root: dict[str, Any],
        buffers: list[_BufferInfo],
        views: list[_BufferViewInfo],
    ) -> list[dict[str, Any]]:
        """校验 accessors 的组件类型、对齐与数据范围。"""

        accessors = root.get("accessors", [])
        if not isinstance(accessors, list):
            raise _format_invalid("accessors 必须是数组。")
        for index, accessor in enumerate(accessors):
            if not isinstance(accessor, dict):
                raise _format_invalid(f"accessors[{index}] 必须是对象。")
            count = accessor.get("count")
            if not _is_int(count) or count < 1:
                raise _format_invalid(f"accessors[{index}].count 必须是正整数。")
            component_type = accessor.get("componentType")
            if not _is_int(component_type) or component_type not in _COMPONENT_TYPE_BYTES:
                raise _format_invalid(f"accessors[{index}].componentType 取值非法。")
            accessor_type = accessor.get("type")
            if not isinstance(accessor_type, str) or accessor_type not in _ACCESSOR_TYPE_COMPONENTS:
                raise _format_invalid(f"accessors[{index}].type 取值非法。")

            min_values = accessor.get("min")
            max_values = accessor.get("max")
            for label, values in (("min", min_values), ("max", max_values)):
                if values is None:
                    continue
                if not isinstance(values, list) or not all(_is_finite_number(item) for item in values):
                    raise _format_invalid(f"accessors[{index}].{label} 必须是有限数值数组。")

            buffer_view_index = accessor.get("bufferView")
            if buffer_view_index is None:
                cls._validate_sparse(accessor, index, views)
                continue
            if not _is_int(buffer_view_index) or not 0 <= buffer_view_index < len(views):
                raise _format_invalid(f"accessors[{index}].bufferView 索引越界。")
            view = views[buffer_view_index]
            component_bytes = _COMPONENT_TYPE_BYTES[component_type]
            element_bytes = component_bytes * _ACCESSOR_TYPE_COMPONENTS[accessor_type]
            byte_offset = accessor.get("byteOffset", 0)
            if not _is_int(byte_offset) or byte_offset < 0:
                raise _format_invalid(f"accessors[{index}].byteOffset 必须是非负整数。")
            if byte_offset % component_bytes != 0:
                raise _format_invalid(f"accessors[{index}] 偏移未按组件大小对齐。")
            if (byte_offset + view.byte_offset) % component_bytes != 0:
                raise _format_invalid(f"accessors[{index}] 与 bufferView 组合偏移未按组件大小对齐。")

            stride = view.byte_stride
            if stride is not None:
                if stride < element_bytes:
                    raise _format_invalid(f"accessors[{index}] 元素大小超过 bufferView byteStride。")
                required_bytes = (count - 1) * stride + element_bytes
            else:
                required_bytes = count * element_bytes
            if byte_offset + required_bytes > view.byte_length:
                raise _format_invalid(f"accessors[{index}] 数据范围超出 bufferViews[{buffer_view_index}]。")

            cls._validate_sparse(accessor, index, views)
        return [dict(accessor) for accessor in accessors]

    @classmethod
    def _validate_sparse(cls, accessor: dict[str, Any], index: int, views: list[_BufferViewInfo]) -> None:
        """校验 sparse accessor 的索引与数据引用（不做全量解码）。"""

        sparse = accessor.get("sparse")
        if sparse is None:
            return
        if not isinstance(sparse, dict):
            raise _format_invalid(f"accessors[{index}].sparse 必须是对象。")
        sparse_count = sparse.get("count")
        if not _is_int(sparse_count) or sparse_count < 1 or sparse_count > accessor.get("count", 0):
            raise _format_invalid(f"accessors[{index}].sparse.count 非法。")
        indices = sparse.get("indices")
        values = sparse.get("values")
        for label, block in (("indices", indices), ("values", values)):
            if not isinstance(block, dict):
                raise _format_invalid(f"accessors[{index}].sparse.{label} 必须是对象。")
            view_index = block.get("bufferView")
            if not _is_int(view_index) or not 0 <= view_index < len(views):
                raise _format_invalid(f"accessors[{index}].sparse.{label}.bufferView 索引越界。")

    @classmethod
    def _validate_nodes_and_scenes(cls, root: dict[str, Any], policy: Model3dAcceptancePolicy) -> None:
        """校验节点树、场景引用与节点数量预算，并检测父子环。"""

        nodes = root.get("nodes", [])
        if not isinstance(nodes, list):
            raise _format_invalid("nodes 必须是数组。")
        if len(nodes) > policy.max_nodes:
            raise _limit_exceeded(f"节点数量超过上限 {policy.max_nodes}。")

        mesh_count = _array_length(root, "meshes")
        camera_count = _array_length(root, "cameras")
        skin_count = _array_length(root, "skins")

        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                raise _format_invalid(f"nodes[{index}] 必须是对象。")
            children = node.get("children")
            if children is not None:
                if not isinstance(children, list):
                    raise _format_invalid(f"nodes[{index}].children 必须是数组。")
                for child in children:
                    if not _is_int(child) or not 0 <= child < len(nodes) or child == index:
                        raise _format_invalid(f"nodes[{index}].children 存在越界或自引用索引。")
            for key, limit in (("mesh", mesh_count), ("camera", camera_count), ("skin", skin_count)):
                reference = node.get(key)
                if reference is not None and (not _is_int(reference) or not 0 <= reference < limit):
                    raise _format_invalid(f"nodes[{index}].{key} 索引越界。")
            matrix = node.get("matrix")
            if matrix is not None:
                if not isinstance(matrix, list) or len(matrix) != 16 or not all(_is_finite_number(item) for item in matrix):
                    raise _format_invalid(f"nodes[{index}].matrix 必须是 16 个有限数值。")
                if any(key in node for key in ("translation", "rotation", "scale")):
                    raise _format_invalid(f"nodes[{index}] 不允许同时声明 matrix 与 TRS 属性。")
            for key, expected in (("translation", 3), ("rotation", 4), ("scale", 3)):
                values = node.get(key)
                if values is None:
                    continue
                if not isinstance(values, list) or len(values) != expected or not all(_is_finite_number(item) for item in values):
                    raise _format_invalid(f"nodes[{index}].{key} 必须包含 {expected} 个有限数值。")
            weights = node.get("weights")
            if weights is not None and (
                not isinstance(weights, list) or not all(_is_finite_number(item) for item in weights)
            ):
                raise _format_invalid(f"nodes[{index}].weights 必须是有限数值数组。")

        assert_acyclic_nodes(nodes)

        scenes = root.get("scenes", [])
        if not isinstance(scenes, list):
            raise _format_invalid("scenes 必须是数组。")
        for index, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                raise _format_invalid(f"scenes[{index}] 必须是对象。")
            scene_nodes = scene.get("nodes", [])
            if not isinstance(scene_nodes, list):
                raise _format_invalid(f"scenes[{index}].nodes 必须是数组。")
            for node_index in scene_nodes:
                if not _is_int(node_index) or not 0 <= node_index < len(nodes):
                    raise _format_invalid(f"scenes[{index}].nodes 存在越界索引。")
        default_scene = root.get("scene")
        if default_scene is not None and (
            not _is_int(default_scene) or not 0 <= default_scene < len(scenes)
        ):
            raise _format_invalid("scene 默认场景索引越界。")

    @classmethod
    def _validate_meshes(cls, root: dict[str, Any], accessors: list[dict[str, Any]], policy: Model3dAcceptancePolicy) -> None:
        """校验 mesh/primitive 引用，并累计三角形数量预算。"""

        meshes = root.get("meshes", [])
        if not isinstance(meshes, list):
            raise _format_invalid("meshes 必须是数组。")
        material_count = _array_length(root, "materials")
        # 同一 mesh 可被多个节点实例化，渲染三角形数是 mesh 三角形数乘以节点引用数。
        instance_counts = [0] * len(meshes)
        for node in root.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            mesh_index = node.get("mesh")
            if _is_int(mesh_index) and 0 <= mesh_index < len(meshes):
                instance_counts[mesh_index] += 1
        triangles = 0
        for mesh_index, mesh in enumerate(meshes):
            if not isinstance(mesh, dict):
                raise _format_invalid(f"meshes[{mesh_index}] 必须是对象。")
            instance_count = max(1, instance_counts[mesh_index])
            primitives = mesh.get("primitives")
            if not isinstance(primitives, list) or not primitives:
                raise _format_invalid(f"meshes[{mesh_index}].primitives 必须是非空数组。")
            for primitive_index, primitive in enumerate(primitives):
                if not isinstance(primitive, dict):
                    raise _format_invalid(f"meshes[{mesh_index}].primitives[{primitive_index}] 必须是对象。")
                attributes = primitive.get("attributes")
                if not isinstance(attributes, dict):
                    raise _format_invalid(f"meshes[{mesh_index}].primitives[{primitive_index}].attributes 必须是对象。")
                if "POSITION" not in attributes:
                    raise _format_invalid(f"meshes[{mesh_index}].primitives[{primitive_index}] 缺少 POSITION 属性。")
                for semantic, accessor_index in attributes.items():
                    if not _is_int(accessor_index) or not 0 <= accessor_index < len(accessors):
                        raise _format_invalid(f"meshes[{mesh_index}].primitives[{primitive_index}].attributes.{semantic} 索引越界。")
                mode = primitive.get("mode", 4)
                if not _is_int(mode) or mode not in _PRIMITIVE_MODES:
                    raise _format_invalid(f"meshes[{mesh_index}].primitives[{primitive_index}].mode 取值非法。")
                indices_accessor = primitive.get("indices")
                if indices_accessor is not None:
                    if not _is_int(indices_accessor) or not 0 <= indices_accessor < len(accessors):
                        raise _format_invalid(f"meshes[{mesh_index}].primitives[{primitive_index}].indices 索引越界。")
                    if accessors[indices_accessor].get("componentType") not in _INDEX_COMPONENT_TYPES:
                        raise _format_invalid(f"meshes[{mesh_index}].primitives[{primitive_index}].indices 组件类型必须是 UNSIGNED_BYTE/SHORT/INT。")
                material_index = primitive.get("material")
                if material_index is not None and (
                    not _is_int(material_index) or not 0 <= material_index < material_count
                ):
                    raise _format_invalid(f"meshes[{mesh_index}].primitives[{primitive_index}].material 索引越界。")

                if indices_accessor is not None:
                    element_count = accessors[indices_accessor]["count"]
                else:
                    element_count = accessors[attributes["POSITION"]]["count"]
                if mode == 4:
                    triangles += (element_count // 3) * instance_count
                elif mode in (5, 6):
                    triangles += max(0, element_count - 2) * instance_count
                if triangles > policy.max_triangles:
                    raise _limit_exceeded(f"三角形数量超过上限 {policy.max_triangles}。")

    @classmethod
    def _validate_images(
        cls,
        root: dict[str, Any],
        buffers: list[_BufferInfo],
        views: list[_BufferViewInfo],
        policy: Model3dAcceptancePolicy,
    ) -> list[_ImageInfo]:
        """校验图片成员：只接受内嵌 PNG/JPEG，并解析成员字节。"""

        images = root.get("images", [])
        if not isinstance(images, list):
            raise _format_invalid("images 必须是数组。")
        result: list[_ImageInfo] = []
        for index, image in enumerate(images):
            if not isinstance(image, dict):
                raise _format_invalid(f"images[{index}] 必须是对象。")
            uri = image.get("uri")
            buffer_view_index = image.get("bufferView")
            if uri is not None and buffer_view_index is not None:
                raise _format_invalid(f"images[{index}] 不允许同时声明 uri 与 bufferView。")
            if uri is not None:
                if not isinstance(uri, str):
                    raise _format_invalid(f"images[{index}].uri 必须是字符串。")
                if not uri.startswith("data:"):
                    raise _external_uri_forbidden(f"images[{index}] 引用了外部文件，首期只接受自包含 GLB。")
                media_type = cls._data_uri_media_type(uri)
                if media_type not in policy.embedded_image_mime_types:
                    raise _format_invalid(f"images[{index}] 的内嵌图片类型 {media_type or 'unknown'} 不在首期支持范围内。")
                payload = cls._decode_data_uri(uri, field=f"images[{index}]")
                result.append(_ImageInfo(data=payload, mime_type=media_type))
                continue
            if buffer_view_index is not None:
                if not _is_int(buffer_view_index) or not 0 <= buffer_view_index < len(views):
                    raise _format_invalid(f"images[{index}].bufferView 索引越界。")
                media_type = str(image.get("mimeType") or "").strip().lower()
                if media_type not in policy.embedded_image_mime_types:
                    raise _format_invalid(f"images[{index}].mimeType 必须是 image/png 或 image/jpeg。")
                view = views[buffer_view_index]
                buffer_data = buffers[view.buffer_index].data
                result.append(
                    _ImageInfo(
                        data=buffer_data[view.byte_offset:view.byte_offset + view.byte_length],
                        mime_type=media_type,
                    )
                )
                continue
            raise _format_invalid(f"images[{index}] 必须声明 uri 或 bufferView。")
        return result

    @staticmethod
    def _validate_textures(root: dict[str, Any], images: list[_ImageInfo]) -> None:
        """校验 textures/samplers 的索引引用。"""

        textures = root.get("textures", [])
        samplers = root.get("samplers", [])
        if not isinstance(textures, list) or not isinstance(samplers, list):
            raise _format_invalid("textures 与 samplers 必须是数组。")
        for index, texture in enumerate(textures):
            if not isinstance(texture, dict):
                raise _format_invalid(f"textures[{index}] 必须是对象。")
            source = texture.get("source")
            if source is not None and (not _is_int(source) or not 0 <= source < len(images)):
                raise _format_invalid(f"textures[{index}].source 索引越界。")
            sampler = texture.get("sampler")
            if sampler is not None and (not _is_int(sampler) or not 0 <= sampler < len(samplers)):
                raise _format_invalid(f"textures[{index}].sampler 索引越界。")

    @staticmethod
    def _validate_materials(root: dict[str, Any]) -> None:
        """校验 materials 顶层结构。"""

        materials = root.get("materials", [])
        if not isinstance(materials, list):
            raise _format_invalid("materials 必须是数组。")
        for index, material in enumerate(materials):
            if not isinstance(material, dict):
                raise _format_invalid(f"materials[{index}] 必须是对象。")

    @classmethod
    def _validate_cameras(cls, root: dict[str, Any]) -> None:
        """校验相机类型与投影参数。"""

        cameras = root.get("cameras", [])
        if not isinstance(cameras, list):
            raise _format_invalid("cameras 必须是数组。")
        for index, camera in enumerate(cameras):
            if not isinstance(camera, dict):
                raise _format_invalid(f"cameras[{index}] 必须是对象。")
            camera_type = camera.get("type")
            if not isinstance(camera_type, str) or camera_type not in {"perspective", "orthographic"}:
                raise _format_invalid(f"cameras[{index}].type 必须是 perspective 或 orthographic。")
            if camera_type == "perspective":
                projection = camera.get("perspective")
                if not isinstance(projection, dict):
                    raise _format_invalid(f"cameras[{index}].perspective 必须是对象。")
                yfov = projection.get("yfov")
                znear = projection.get("znear")
                zfar = projection.get("zfar")
                aspect = projection.get("aspectRatio")
                if not _is_finite_number(yfov) or not 0 < yfov < math.pi:
                    raise _format_invalid(f"cameras[{index}] 透视 yfov 非法。")
                if not _is_finite_number(znear) or znear <= 0:
                    raise _format_invalid(f"cameras[{index}] 透视 znear 非法。")
                if zfar is not None and (not _is_finite_number(zfar) or zfar <= znear):
                    raise _format_invalid(f"cameras[{index}] 透视 zfar 必须大于 znear。")
                if aspect is not None and (not _is_finite_number(aspect) or aspect <= 0):
                    raise _format_invalid(f"cameras[{index}] 透视 aspectRatio 非法。")
            else:
                projection = camera.get("orthographic")
                if not isinstance(projection, dict):
                    raise _format_invalid(f"cameras[{index}].orthographic 必须是对象。")
                xmag, ymag = projection.get("xmag"), projection.get("ymag")
                znear, zfar = projection.get("znear"), projection.get("zfar")
                if not _is_finite_number(xmag) or xmag == 0:
                    raise _format_invalid(f"cameras[{index}] 正交 xmag 非法。")
                if not _is_finite_number(ymag) or ymag == 0:
                    raise _format_invalid(f"cameras[{index}] 正交 ymag 非法。")
                if not _is_finite_number(znear) or not _is_finite_number(zfar) or zfar <= znear:
                    raise _format_invalid(f"cameras[{index}] 正交 znear/zfar 非法。")

    @classmethod
    def _validate_animations(cls, root: dict[str, Any]) -> None:
        """校验 animations 通道与采样器引用。"""

        animations = root.get("animations", [])
        if not isinstance(animations, list):
            raise _format_invalid("animations 必须是数组。")
        node_count = len(root.get("nodes", []) or [])
        accessor_count = len(root.get("accessors", []) or [])
        for index, animation in enumerate(animations):
            if not isinstance(animation, dict):
                raise _format_invalid(f"animations[{index}] 必须是对象。")
            samplers = animation.get("samplers", [])
            channels = animation.get("channels", [])
            if not isinstance(samplers, list) or not isinstance(channels, list):
                raise _format_invalid(f"animations[{index}] 的 channels/samplers 必须是数组。")
            for sampler_index, sampler in enumerate(samplers):
                if not isinstance(sampler, dict):
                    raise _format_invalid(f"animations[{index}].samplers[{sampler_index}] 必须是对象。")
                for key in ("input", "output"):
                    reference = sampler.get(key)
                    if not _is_int(reference) or not 0 <= reference < accessor_count:
                        raise _format_invalid(f"animations[{index}].samplers[{sampler_index}].{key} 索引越界。")
            for channel_index, channel in enumerate(channels):
                if not isinstance(channel, dict):
                    raise _format_invalid(f"animations[{index}].channels[{channel_index}] 必须是对象。")
                sampler_reference = channel.get("sampler")
                if not _is_int(sampler_reference) or not 0 <= sampler_reference < len(samplers):
                    raise _format_invalid(f"animations[{index}].channels[{channel_index}].sampler 索引越界。")
                target = channel.get("target")
                if not isinstance(target, dict):
                    raise _format_invalid(f"animations[{index}].channels[{channel_index}].target 必须是对象。")
                node_reference = target.get("node")
                if node_reference is not None and (
                    not _is_int(node_reference) or not 0 <= node_reference < node_count
                ):
                    raise _format_invalid(f"animations[{index}].channels[{channel_index}].target.node 索引越界。")
                target_path = target.get("path")
                if not isinstance(target_path, str) or target_path not in _ANIMATION_TARGET_PATHS:
                    raise _format_invalid(f"animations[{index}].channels[{channel_index}].target.path 取值非法。")

    @classmethod
    def _validate_texture_budget(cls, images: list[_ImageInfo], policy: Model3dAcceptancePolicy) -> None:
        """用图片头信息校验纹理解码预算，不做全量像素解码。"""

        total_pixels = 0
        for index, image in enumerate(images):
            dimensions = cls._probe_image_dimensions(image.data, image.mime_type)
            if dimensions is None:
                raise _format_invalid(f"images[{index}] 的内嵌图片头无法解析。")
            width, height = dimensions
            if width <= 0 or height <= 0:
                raise _format_invalid(f"images[{index}] 的尺寸非法。")
            if max(width, height) > policy.max_texture_edge:
                raise _limit_exceeded(f"images[{index}] 尺寸 {width}x{height} 超过单边上限 {policy.max_texture_edge}。")
            total_pixels += width * height
            if total_pixels > policy.max_texture_pixels:
                raise _limit_exceeded(f"纹理解码总像素超过上限 {policy.max_texture_pixels}。")

    @staticmethod
    def _probe_image_dimensions(data: bytes, mime_type: str) -> tuple[int, int] | None:
        """从 PNG/JPEG 头部读取尺寸，不解码像素。"""

        if mime_type == "image/png" or data[:8] == _PNG_SIGNATURE:
            if len(data) < 24 or data[:8] != _PNG_SIGNATURE or data[12:16] != b"IHDR":
                return None
            width, height = struct.unpack(">II", data[16:24])
            return int(width), int(height)
        if mime_type == "image/jpeg" or data[:2] == b"\xff\xd8":
            if len(data) < 4 or data[:2] != b"\xff\xd8":
                return None
            cursor = 2
            while cursor + 4 <= len(data):
                if data[cursor] != 0xFF:
                    cursor += 1
                    continue
                marker = data[cursor + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    cursor += 2
                    continue
                if marker == 0xD9:
                    break
                segment_length = int.from_bytes(data[cursor + 2:cursor + 4], "big")
                if marker in _JPEG_SOF_MARKERS:
                    if cursor + 9 > len(data):
                        return None
                    height = int.from_bytes(data[cursor + 5:cursor + 7], "big")
                    width = int.from_bytes(data[cursor + 7:cursor + 9], "big")
                    return width, height
                cursor += 2 + segment_length
            return None
        return None

    # ------------------------------------------------------------------
    # 摘要
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(root: dict[str, Any], warnings: list[str], *, policy: Model3dAcceptancePolicy) -> dict[str, Any]:
        """组装分析摘要（对应 AssetModel3dAnalysisPayload）。"""

        cameras = []
        for index, camera in enumerate(root.get("cameras", []) or []):
            name = camera.get("name")
            cameras.append(
                {
                    "index": index,
                    "name": str(name) if isinstance(name, str) and name.strip() else None,
                    "type": str(camera.get("type") or "perspective"),
                }
            )
        animations = []
        for index, animation in enumerate(root.get("animations", []) or []):
            name = animation.get("name")
            animations.append(
                {
                    "index": index,
                    "name": str(name) if isinstance(name, str) and name.strip() else None,
                    "channel_count": len(animation.get("channels", []) or []),
                }
            )
        scenes = root.get("scenes", []) or []
        default_scene = root.get("scene")
        return {
            "format": "glb",
            "gltf_version": str((root.get("asset") or {}).get("version") or "2.0"),
            "scene_count": len(scenes),
            "default_scene_index": int(default_scene) if _is_int(default_scene) else None,
            "cameras": cameras,
            "animations": animations,
            "extensions_used": [str(item) for item in root.get("extensionsUsed", []) or []],
            "extensions_required": [str(item) for item in root.get("extensionsRequired", []) or []],
            "validation_profile": policy.validation_profile,
            "warnings": list(warnings),
        }
