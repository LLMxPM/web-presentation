"""文件功能：以有界内存预算和迭代图遍历约束 GLB 的解码规模与节点拓扑。"""

from collections.abc import Iterable
from typing import Any

from app.core.exceptions import AppException
from app.services.model3d_acceptance_policy import (
    MODEL3D_ERROR_FORMAT_INVALID,
    MODEL3D_ERROR_LIMIT_EXCEEDED,
    Model3dAcceptancePolicy,
)


def validate_accessor_decoded_budget(
    accessor_sizes: Iterable[tuple[int, int]], *, policy: Model3dAcceptancePolicy
) -> None:
    """检查已验证 accessor 的元素数与单元素字节数，包含无 bufferView 的零填充数据。

    不创建解码数组；逐项及累计限制防止稀疏数据或小索引网格绕过文件/三角形预算。
    """

    total_bytes = 0
    for index, (count, element_bytes) in enumerate(accessor_sizes):
        decoded_bytes = count * element_bytes
        if decoded_bytes > policy.max_accessor_decoded_bytes:
            raise AppException(
                status_code=400,
                code=MODEL3D_ERROR_LIMIT_EXCEEDED,
                detail=f"accessors[{index}] 解码大小超过上限 {policy.max_accessor_decoded_bytes} 字节。",
            )
        total_bytes += decoded_bytes
        if total_bytes > policy.max_total_accessor_decoded_bytes:
            raise AppException(
                status_code=400,
                code=MODEL3D_ERROR_LIMIT_EXCEEDED,
                detail=f"accessors 解码总大小超过上限 {policy.max_total_accessor_decoded_bytes} 字节。",
            )


def assert_acyclic_nodes(nodes: list[dict[str, Any]]) -> None:
    """对已验证索引的节点图执行迭代三色 DFS，不受 Python 递归深度限制。"""

    state = [0] * len(nodes)
    for root in range(len(nodes)):
        if state[root] == 2:
            continue
        stack = [(root, False)]
        while stack:
            index, exiting = stack.pop()
            if exiting:
                state[index] = 2
                continue
            if state[index] == 1:
                raise AppException(status_code=400, code=MODEL3D_ERROR_FORMAT_INVALID, detail="nodes 存在父子环。")
            if state[index] == 2:
                continue
            state[index] = 1
            stack.append((index, True))
            stack.extend((child, False) for child in reversed(nodes[index].get("children", []) or []))
