"""文件功能：投影 Runtime Kit 执行身份，将目录文案与导入、预览和引擎输入分离。"""

from copy import deepcopy
from typing import Any

RUNTIME_KIT_IMPORT_POLICY_VERSION = "runtime-kit-import.v2"


def project_runtime_kit_execution_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """仅剔除已知目录字段，保留 Schema、引擎和未来未知字段；不修改缓存中的原始清单。"""

    identity = deepcopy(manifest)
    documentation_fields = (
        "enabled", "previewable", "display_name", "summary", "tags", "usage", "returns",
        "return_example", "constraints", "audiences",
    )
    for entry in identity.get("exports", []):
        if not isinstance(entry, dict):
            continue
        entry.pop("category", None)
        entry.pop("description", None)
        capability = entry.get("capability")
        if not isinstance(capability, dict):
            continue
        for key in documentation_fields:
            capability.pop(key, None)
        if not capability:
            entry.pop("capability", None)
    return identity
