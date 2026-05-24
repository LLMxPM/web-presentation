"""文件功能：基于 Runtime Kit manifest 定义远程模块可导入边界与路径规范化规则。"""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

RUNTIME_REMOTE_COMPONENT_PREFIX = "@workspace-components/"
RUNTIME_KIT_ALIAS = "@runtime-kit"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_RUNTIME_KIT_MANIFEST_PATH = (
    _REPO_ROOT / "runtime" / "src" / "runtime-kit" / "manifest" / "runtime-kit.manifest.json"
)
_WORKSPACE_COMPONENT_MODULE_PATH_PATTERN = re.compile(
    r"^src/workspace-components/(?P<component_code>[A-Za-z0-9_-]+)/v/(?P<version_no>\d+)\.vue$"
)
_RUNTIME_KIT_CAPABILITY_KINDS = {"component", "composable", "util", "type"}
_RUNTIME_KIT_CAPABILITY_AUDIENCES = {"backend", "agent"}
_RUNTIME_KIT_VERSIONED_IMPORT_PATTERN = re.compile(r"\.v(?P<version_no>\d+)(?:\.[A-Za-z0-9]+)?$")


@dataclass(frozen=True)
class RuntimeKitImportDependency:
    """Runtime Kit 版本化公开能力依赖。"""

    name: str
    base_name: str
    version_no: int
    import_path: str
    module_path: str


@lru_cache(maxsize=1)
def load_runtime_kit_manifest(manifest_path: str | Path | None = None) -> dict[str, Any]:
    """读取 Runtime Kit 公开清单；Backend 只消费该清单，不硬编码 Runtime 内部目录。"""

    resolved_path = Path(manifest_path) if manifest_path is not None else _DEFAULT_RUNTIME_KIT_MANIFEST_PATH
    with resolved_path.open("r", encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    if manifest.get("alias") != RUNTIME_KIT_ALIAS:
        raise ValueError(f"Runtime Kit manifest alias 必须是 {RUNTIME_KIT_ALIAS}。")
    if not isinstance(manifest.get("exports"), list):
        raise ValueError("Runtime Kit manifest 必须包含 exports 数组。")
    _validate_runtime_kit_manifest_versions(manifest)
    return manifest


def _validate_runtime_kit_manifest_versions(manifest: dict[str, Any]) -> None:
    """校验 manifest 中所有公开能力都采用文件名版本化规范。"""

    seen_names: set[str] = set()
    seen_base_versions: set[tuple[str, str, int]] = set()
    for item in manifest["exports"]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        base_name = str(item.get("base_name") or "").strip()
        name = str(item.get("name") or "").strip()
        import_path = str(item.get("import_path") or "").strip()
        version_no = _coerce_positive_int(item.get("version_no"))
        if not kind or not base_name or not name or not import_path or version_no is None:
            raise ValueError("Runtime Kit capability 必须包含 kind、base_name、version_no、name 与 import_path。")
        expected_name = f"{base_name}.v{version_no}"
        if name != expected_name:
            raise ValueError(f"Runtime Kit capability name 必须为 {expected_name}。")
        if not is_versioned_runtime_kit_import_path(import_path):
            raise ValueError(f"Runtime Kit import_path 必须包含 .v<整数版本>：{import_path}。")
        if name in seen_names:
            raise ValueError(f"Runtime Kit capability name 重复：{name}。")
        base_version_key = (kind, base_name, version_no)
        if base_version_key in seen_base_versions:
            raise ValueError(f"Runtime Kit capability 版本重复：{kind}/{base_name}/v{version_no}。")
        seen_names.add(name)
        seen_base_versions.add(base_version_key)


def _coerce_positive_int(value: Any) -> int | None:
    """把 manifest 中的版本号转为正整数；非法值返回空。"""

    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def is_versioned_runtime_kit_import_path(import_path: str) -> bool:
    """判断 Runtime Kit import_path 是否符合文件名版本化规范。"""

    normalized_path = str(import_path or "").strip().replace("\\", "/")
    if not normalized_path.startswith(f"{RUNTIME_KIT_ALIAS}/"):
        return False
    return _RUNTIME_KIT_VERSIONED_IMPORT_PATTERN.search(normalized_path) is not None


def get_runtime_kit_export_paths() -> set[str]:
    """返回 Runtime Kit manifest 中显式声明的 import_path 集合。"""

    manifest = load_runtime_kit_manifest()
    return {
        str(item.get("import_path", "")).strip()
        for item in manifest["exports"]
        if isinstance(item, dict) and str(item.get("import_path", "")).strip()
    }


def get_runtime_kit_component_export_paths() -> set[str]:
    """返回 Runtime Kit manifest 中 kind=component 的 import_path 集合。"""

    manifest = load_runtime_kit_manifest()
    return {
        str(item.get("import_path", "")).strip()
        for item in manifest["exports"]
        if isinstance(item, dict) and str(item.get("kind", "")).strip() == "component" and str(item.get("import_path", "")).strip()
    }


def get_runtime_kit_export_module_paths() -> set[str]:
    """返回 Runtime Kit manifest 中公开路径对应的 Runtime 逻辑模块路径集合。"""

    return {normalize_runtime_module_path(import_path) for import_path in get_runtime_kit_export_paths()}


def list_runtime_kit_component_capabilities(manifest_path: str | Path | None = None) -> list[dict[str, Any]]:
    """返回 manifest 中声明为 Backend 可暴露能力的 Runtime Kit 组件。"""

    return [
        item
        for item in list_runtime_kit_capabilities(manifest_path)
        if item["kind"] == "component"
    ]


def list_runtime_kit_capabilities(
    manifest_path: str | Path | None = None,
    *,
    base_name: str | None = None,
    version_no: int | None = None,
    include_all_versions: bool = False,
) -> list[dict[str, Any]]:
    """返回 manifest 中声明为可暴露能力目录的 Runtime Kit 能力项。"""

    manifest = load_runtime_kit_manifest(manifest_path)
    result: list[dict[str, Any]] = []
    normalized_base_name = str(base_name or "").strip()
    normalized_version_no = _coerce_positive_int(version_no) if version_no is not None else None
    if version_no is not None and normalized_version_no is None:
        return []
    for item in manifest["exports"]:
        if not isinstance(item, dict):
            continue

        kind = str(item.get("kind") or "").strip()
        if kind not in _RUNTIME_KIT_CAPABILITY_KINDS:
            continue
        capability = item.get("capability")
        if not isinstance(capability, dict) or capability.get("enabled") is not True:
            continue

        name = str(item.get("name") or "").strip()
        item_base_name = str(item.get("base_name") or "").strip()
        item_version_no = _coerce_positive_int(item.get("version_no"))
        import_path = str(item.get("import_path") or "").strip()
        if not name or not item_base_name or item_version_no is None or not import_path:
            raise ValueError("Runtime Kit capability 必须包含 name、base_name、version_no 与 import_path。")
        if normalized_base_name and item_base_name != normalized_base_name:
            continue
        if normalized_version_no is not None and item_version_no != normalized_version_no:
            continue

        previewable = bool(capability.get("previewable")) if kind == "component" else False
        tags = [
            str(tag).strip()
            for tag in capability.get("tags", []) or []
            if str(tag).strip()
        ]
        usage = [
            str(line).strip()
            for line in capability.get("usage", []) or []
            if str(line).strip()
        ]
        return_example = [
            str(line).strip()
            for line in capability.get("return_example", []) or []
            if str(line).strip()
        ]
        constraints = [
            str(line).strip()
            for line in capability.get("constraints", []) or []
            if str(line).strip()
        ]
        audiences = [
            str(audience).strip()
            for audience in capability.get("audiences", []) or []
            if str(audience).strip() in _RUNTIME_KIT_CAPABILITY_AUDIENCES
        ]

        result.append(
            {
                "kind": kind,
                "base_name": item_base_name,
                "version_no": item_version_no,
                "name": name,
                "import_path": import_path,
                "category": str(item.get("category") or "uncategorized").strip() or "uncategorized",
                "description": str(item.get("description") or "").strip(),
                "display_name": str(capability.get("display_name") or name).strip(),
                "summary": str(capability.get("summary") or item.get("description") or "").strip(),
                "tags": tags,
                "previewable": previewable,
                "preview_schema": capability.get("preview_schema"),
                "preview_options": capability.get("preview_options"),
                "usage": usage,
                "returns": str(capability.get("returns") or "").strip(),
                "return_example": return_example,
                "constraints": constraints,
                "audiences": audiences,
                "manifest_version": str(manifest.get("version") or "").strip(),
            }
        )
    if include_all_versions or normalized_version_no is not None:
        return result
    return _filter_latest_runtime_kit_versions(result)


def _filter_latest_runtime_kit_versions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 kind + base_name 只保留最新版本能力，保持原始 manifest 顺序。"""

    latest_by_key: dict[tuple[str, str], int] = {}
    for item in items:
        key = (str(item["kind"]), str(item["base_name"]))
        latest_by_key[key] = max(latest_by_key.get(key, 0), int(item["version_no"]))
    return [
        item
        for item in items
        if int(item["version_no"]) == latest_by_key[(str(item["kind"]), str(item["base_name"]))]
    ]


def get_runtime_kit_component_capability(name: str, manifest_path: str | Path | None = None) -> dict[str, Any] | None:
    """按组件能力名称读取 Runtime Kit 组件能力；未启用能力时返回空。"""

    return get_runtime_kit_capability(name, kind="component", manifest_path=manifest_path)


def get_runtime_kit_capability(
    name: str,
    *,
    kind: str | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """按能力名称读取 Runtime Kit 能力项；未启用能力时返回空。"""

    normalized_name = str(name or "").strip()
    normalized_kind = str(kind or "").strip() or None
    for item in list_runtime_kit_capabilities(manifest_path, include_all_versions=True):
        if item["name"] == normalized_name and (normalized_kind is None or item["kind"] == normalized_kind):
            return item
    return None


def get_runtime_kit_capability_by_import_path(
    import_path: str,
    manifest_path: str | Path | None = None,
) -> RuntimeKitImportDependency | None:
    """按版本化 import_path 读取 Runtime Kit 能力依赖元数据。"""

    normalized_path = str(import_path or "").strip().replace("\\", "/")
    for item in list_runtime_kit_capabilities(manifest_path, include_all_versions=True):
        if item["import_path"] != normalized_path:
            continue
        return RuntimeKitImportDependency(
            name=str(item["name"]),
            base_name=str(item["base_name"]),
            version_no=int(item["version_no"]),
            import_path=str(item["import_path"]),
            module_path=normalize_runtime_module_path(str(item["import_path"])),
        )
    return None


def is_runtime_public_local_module(import_path: str) -> bool:
    """判断导入源是否为 manifest 显式开放的 Runtime Kit 模块。"""

    normalized_path = str(import_path or "").strip().replace("\\", "/")
    return normalized_path in get_runtime_kit_export_paths()


def is_runtime_public_local_component_module(import_path: str) -> bool:
    """判断导入源是否为 manifest 显式开放的 Runtime Kit 组件模块。"""

    normalized_path = str(import_path or "").strip().replace("\\", "/")
    return normalized_path in get_runtime_kit_component_export_paths()


def is_runtime_public_local_module_path(module_path: str) -> bool:
    """判断规范化后的 `src/...` 模块路径是否为 manifest 显式开放项。"""

    normalized_path = normalize_runtime_module_path(module_path)
    return normalized_path in get_runtime_kit_export_module_paths()


def normalize_runtime_module_path(import_path: str) -> str:
    """把导入路径统一规范化为 Runtime 使用的 `src/...` 逻辑模块路径。"""

    normalized_path = str(import_path or "").strip().replace("\\", "/")
    if not normalized_path:
        return ""

    component_import = parse_workspace_component_import_path(normalized_path)
    if component_import is not None:
        component_code, version_no = component_import
        return f"src/workspace-components/{component_code}/v/{version_no}.vue"
    if normalized_path.startswith(f"{RUNTIME_KIT_ALIAS}/"):
        return normalized_path.replace(f"{RUNTIME_KIT_ALIAS}/", "src/runtime-kit/", 1)
    if normalized_path.startswith("@/"):
        return normalized_path.replace("@/", "src/", 1)
    if normalized_path.startswith("/src/"):
        return normalized_path[1:]
    if normalized_path.startswith("src/"):
        return normalized_path
    if normalized_path.startswith("views/"):
        return f"src/{normalized_path}"
    if normalized_path.startswith("/views/"):
        return f"src{normalized_path}"
    if normalized_path.startswith("workspace-components/"):
        return f"src/{normalized_path}"
    if normalized_path.startswith("/workspace-components/"):
        return f"src{normalized_path}"
    return normalized_path.lstrip("/")


def normalize_relative_runtime_module_path(import_path: str, importer_module_path: str) -> str:
    """基于当前导入方模块路径，计算相对导入最终对应的 Runtime 逻辑模块路径。"""

    normalized_importer = normalize_runtime_module_path(importer_module_path)
    importer_dir = posixpath.dirname(normalized_importer)
    return normalize_runtime_module_path(posixpath.normpath(posixpath.join(importer_dir, import_path)))


def is_runtime_page_module_path(module_path: str) -> bool:
    """判断给定逻辑模块路径是否指向 Runtime 远程页面模块。"""

    return normalize_runtime_module_path(module_path).startswith("src/views/")


def parse_workspace_component_import_path(import_path: str) -> tuple[str, int] | None:
    """解析 `@workspace-components/<code>/v/<version>` 形式的远程组件别名。"""

    normalized_path = str(import_path or "").strip()
    if not normalized_path.startswith(RUNTIME_REMOTE_COMPONENT_PREFIX):
        return None

    relative_path = normalized_path[len(RUNTIME_REMOTE_COMPONENT_PREFIX):]
    parts = [part for part in relative_path.split("/") if part]
    if len(parts) < 3 or parts[1] != "v":
        return None

    component_code = parts[0]
    version_segment = parts[2]
    if version_segment.endswith(".vue"):
        version_segment = version_segment[:-4]
    if not component_code or not version_segment.isdigit():
        return None
    return component_code, int(version_segment)


def parse_workspace_component_module_path(module_path: str) -> tuple[str, int] | None:
    """解析 `src/workspace-components/<code>/v/<version>.vue` 形式的逻辑模块路径。"""

    normalized_path = normalize_runtime_module_path(module_path)
    match = _WORKSPACE_COMPONENT_MODULE_PATH_PATTERN.match(normalized_path)
    if match is None:
        return None
    return match.group("component_code"), int(match.group("version_no"))


def build_runtime_module_resolver_config() -> dict[str, object]:
    """构建可下发给 Runtime 的模块解析边界配置。"""

    manifest = load_runtime_kit_manifest()
    return {
        "remote_component_prefix": RUNTIME_REMOTE_COMPONENT_PREFIX,
        "runtime_kit_alias": RUNTIME_KIT_ALIAS,
        "runtime_kit_manifest_version": manifest.get("version"),
        "runtime_kit_exports": manifest["exports"],
    }
