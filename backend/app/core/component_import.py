"""文件功能：提供工作空间组件导入路径与 import 语句生成通用底层能力。"""

from __future__ import annotations

import re


def to_valid_import_identifier(raw_name: str | None) -> str:
    """把组件展示名转换为合法的 PascalCase 标识符。

    :param raw_name: 原始组件名称、导入标识或编码
    :return: 合法的 PascalCase 标识符；若无法提取有效字符则返回空字符串
    """

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


def build_component_import_usage(
    component_code: str,
    version_no: int,
    component_name: str | None = None,
    import_name: str | None = None,
) -> dict[str, str]:
    """根据组件编码、版本与引用名生成稳定的导入路径和 import 语句。

    :param component_code: 组件业务编码（如 CMP20260503001）
    :param version_no: 组件发布版本号（正整数）
    :param component_name: 组件显示名称
    :param import_name: 优先使用的导入标识符
    :return: 包含 import_path 与 import_statement 的字典
    """

    import_path = f"@workspace-components/{component_code}/v/{version_no}"
    resolved_import_name = (
        to_valid_import_identifier(import_name)
        or to_valid_import_identifier(component_name)
        or to_valid_import_identifier(component_code)
        or "WorkspaceComponent"
    )
    return {
        "import_path": import_path,
        "import_statement": f"import {resolved_import_name} from '{import_path}'",
    }
