"""文件功能：回归 GLB 零填充/稀疏解码预算及深节点图遍历，避免实际分配大型数组。"""

import base64
import json
import struct

import pytest
from app.core.exceptions import AppException
from app.services.model3d_acceptance_policy import Model3dAcceptancePolicy
from app.services.model3d_glb_service import Model3dGlbService


def _glb(document: dict) -> bytes:
    """把小型 JSON 文档封装为 GLB，测试只声明大 count 而不创建大文件。"""

    raw = json.dumps(document).encode()
    raw += b" " * ((-len(raw)) % 4)
    return b"glTF" + struct.pack("<II", 2, 20 + len(raw)) + struct.pack("<II", len(raw), 0x4E4F534A) + raw


def _assert_limit(document: dict, policy: Model3dAcceptancePolicy | None = None) -> None:
    """预算超限应返回统一业务错误，不能落入浏览器解码或普通 500。"""

    with pytest.raises(AppException) as error:
        Model3dGlbService.analyze(_glb(document), policy=policy)
    assert error.value.status_code == 400
    assert error.value.code == "MODEL3D_LIMIT_EXCEEDED"


def test_indexed_triangle_cannot_hide_huge_zero_filled_positions() -> None:
    """三个索引不能掩盖十亿顶点的零填充 POSITION 分配。"""

    document = {
        "asset": {"version": "2.0"},
        "accessors": [
            {"componentType": 5126, "count": 1_000_000_000, "type": "VEC3"},
            {"componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
    }
    assert len(_glb(document)) < 1024
    _assert_limit(document)


def test_sparse_accessor_decoded_size_is_bounded() -> None:
    """稀疏数据按完整展开后的元素数计费，不能只计算一个稀疏条目。"""

    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": 16, "uri": "data:application/octet-stream;base64," + base64.b64encode(bytes(16)).decode()}],
        "bufferViews": [{"buffer": 0, "byteLength": 1}, {"buffer": 0, "byteOffset": 4, "byteLength": 12}],
        "accessors": [{
            "componentType": 5126, "count": 1_000_000_000, "type": "VEC3",
            "sparse": {"count": 1, "indices": {"bufferView": 0, "componentType": 5121}, "values": {"bufferView": 1}},
        }],
    }
    _assert_limit(document)


def test_multiple_small_accessors_share_total_budget() -> None:
    """每项低于上限时仍需检查总量，不能拆成多个 accessor 绕过限制。"""

    document = {"asset": {"version": "2.0"}, "accessors": [
        {"componentType": 5126, "count": 2, "type": "VEC3"} for _ in range(3)
    ]}
    _assert_limit(document, Model3dAcceptancePolicy(max_accessor_decoded_bytes=32, max_total_accessor_decoded_bytes=64))


def test_decoded_budget_accepts_exact_boundary() -> None:
    """单项及累计预算恰好等于上限时仍允许合法零填充 accessor。"""

    document = {"asset": {"version": "2.0"}, "accessors": [{"componentType": 5126, "count": 2, "type": "VEC3"}]}
    Model3dGlbService.analyze(
        _glb(document), policy=Model3dAcceptancePolicy(max_accessor_decoded_bytes=24, max_total_accessor_decoded_bytes=24)
    )


@pytest.mark.parametrize("cycle", [False, True])
def test_deep_node_chain_uses_controlled_validation(cycle: bool) -> None:
    """2048 层链不依赖递归；深处闭环仍按格式非法返回。"""

    nodes = [{"children": [index + 1]} for index in range(2047)] + [{"children": [0]} if cycle else {}]
    document = {"asset": {"version": "2.0"}, "nodes": nodes, "scenes": [{"nodes": [0]}], "scene": 0}
    if cycle:
        with pytest.raises(AppException) as error:
            Model3dGlbService.analyze(_glb(document))
        assert error.value.code == "MODEL3D_FORMAT_INVALID"
    else:
        Model3dGlbService.analyze(_glb(document))


def test_shared_descendant_is_not_a_cycle() -> None:
    """共享已完成节点不应被误判为当前遍历路径上的环。"""

    Model3dGlbService.analyze(_glb({"asset": {"version": "2.0"}, "nodes": [
        {"children": [1, 2]}, {"children": [3]}, {"children": [3]}, {},
    ]}))
