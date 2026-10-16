"""文件功能：集中定义三维资源（model3d/GLB）的接受策略、预算上限、扩展白名单与统一错误码。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

# 统一错误码：格式非法、必需扩展不支持、外部 URI、预算超限、引用无法冻结。
MODEL3D_ERROR_FORMAT_INVALID: Final = "MODEL3D_FORMAT_INVALID"
MODEL3D_ERROR_EXTENSION_UNSUPPORTED: Final = "MODEL3D_EXTENSION_UNSUPPORTED"
MODEL3D_ERROR_EXTERNAL_URI_FORBIDDEN: Final = "MODEL3D_EXTERNAL_URI_FORBIDDEN"
MODEL3D_ERROR_LIMIT_EXCEEDED: Final = "MODEL3D_LIMIT_EXCEEDED"
MODEL3D_ERROR_REFERENCE_UNRESOLVED: Final = "MODEL3D_REFERENCE_UNRESOLVED"
MODEL3D_ERROR_REPLACE_BASELINE_REQUIRED: Final = "MODEL3D_REPLACE_BASELINE_REQUIRED"

# 版本与并发控制错误码：通用资源替换基线冲突与按 ID 替换要求。
ASSET_ERROR_VERSION_CONFLICT: Final = "ASSET_VERSION_CONFLICT"
ASSET_ERROR_OVERWRITE_REQUIRES_REPLACE: Final = "MODEL3D_OVERWRITE_REQUIRES_REPLACE"

# 三维资源规范 MIME；上传时客户端可能给出 octet-stream，按规范归一化。
MODEL3D_CANONICAL_CONTENT_TYPE: Final = "model/gltf-binary"
MODEL3D_ACCEPTED_CONTENT_TYPES: Final = frozenset(
    {
        MODEL3D_CANONICAL_CONTENT_TYPE,
        "application/gltf-binary",
        "application/octet-stream",
    }
)


@dataclass(frozen=True)
class Model3dAcceptancePolicy:
    """三维资源接受策略：策略版本、预算上限与扩展白名单的单一事实源。

    策略对象同时服务上传校验、分析摘要与错误提示；Runtime 侧执行相同必要防护，
    但不允许各自维护第二份数值。M0 验证后只允许在此处调整数值并同步版本号。
    """

    # 本次接受策略版本，写入分析摘要，供运行时与缓存身份使用。
    validation_profile: str = "model3d-glb-v1"

    # 文件级预算：单文件上限与 JSON chunk 上限（字节）。
    max_file_bytes: int = 32 * 1024 * 1024
    max_json_chunk_bytes: int = 2 * 1024 * 1024

    # 结构规模预算。
    max_nodes: int = 2048
    max_triangles: int = 300_000

    # 纹理解码预算：单纹理最长边与全部纹理解码总像素。
    max_texture_edge: int = 4096
    max_texture_pixels: int = 32 * 1024 * 1024

    # 允许出现在 extensionsRequired 的扩展白名单；其余必需扩展拒绝。
    required_extension_allowlist: frozenset[str] = field(
        default_factory=lambda: frozenset({"KHR_materials_unlit", "KHR_lights_punctual"})
    )

    # 允许内嵌图片的 MIME 集合；首期不接受压缩纹理容器。
    embedded_image_mime_types: frozenset[str] = field(
        default_factory=lambda: frozenset({"image/png", "image/jpeg"})
    )

    @property
    def validation_profile_short(self) -> str:
        """返回适合写入缓存键与日志的短策略标识。"""

        return self.validation_profile


MODEL3D_ACCEPTANCE_POLICY: Final = Model3dAcceptancePolicy()


def build_model3d_support_matrix() -> dict[str, object]:
    """返回可对外的三维支持矩阵摘要，保证与策略对象同源。"""

    policy = MODEL3D_ACCEPTANCE_POLICY
    return {
        "validation_profile": policy.validation_profile,
        "formats": ["glb"],
        "max_file_bytes": policy.max_file_bytes,
        "max_json_chunk_bytes": policy.max_json_chunk_bytes,
        "max_nodes": policy.max_nodes,
        "max_triangles": policy.max_triangles,
        "max_texture_edge": policy.max_texture_edge,
        "max_texture_pixels": policy.max_texture_pixels,
        "required_extensions": sorted(policy.required_extension_allowlist),
        "embedded_image_mime_types": sorted(policy.embedded_image_mime_types),
    }
