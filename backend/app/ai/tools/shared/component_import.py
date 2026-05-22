"""文件功能：提供工作空间组件导入路径与 import 语句生成能力。"""

from __future__ import annotations

import re


def build_component_import_usage(
    component_code: str,
    version_no: int,
    component_name: str | None,
    import_name: str | None = None,
) -> dict[str, str]:
    """根据组件编码、版本与引用名生成稳定的导入路径和 import 语句。"""

    import_path = f"@workspace-components/{component_code}/v/{version_no}"
    resolved_import_name = (
        _to_valid_identifier(import_name)
        or _to_valid_identifier(component_name)
        or _to_valid_identifier(component_code)
        or "WorkspaceComponent"
    )
    return {
        "import_path": import_path,
        "import_statement": f"import {resolved_import_name} from '{import_path}'",
    }


def _to_valid_identifier(raw_name: str | None) -> str:
    """把组件展示名转换为合法的 PascalCase 标识符。"""

    normalized_name = str(raw_name or "").strip()
    if not normalized_name:
        return ""

    tokens = [token for token in re.split(r"[^A-Za-z0-9_$]+", normalized_name) if token]
    if not tokens:
        return ""

    transformed = "".join(token[:1].upper() + token[1:] for token in tokens)
    if transformed and transformed[0].isdigit():
        transformed = f"Component{transformed}"
    return transformed
