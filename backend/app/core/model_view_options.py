"""文件功能：实现 AssetModel.v1 实例展示参数（ModelViewOptions）的共享校验规则。"""

from __future__ import annotations

import math
import re
from typing import Any

# 背景色只接受约定格式：transparent 或三位/六位/八位十六进制颜色。
_BACKGROUND_TRANSPARENT = "transparent"
_HEX_COLOR_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _is_finite_number(value: Any) -> bool:
    """判断值是否为有限数值（拒绝布尔与 NaN/Infinity）。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _is_non_negative_integer(value: Any) -> bool:
    """判断值是否为非负整数（拒绝布尔）。"""

    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _validate_vector3(value: Any, field_name: str, errors: list[str]) -> list[float] | None:
    """校验三元数组并返回数值列表；非法时写入错误信息。"""

    if not isinstance(value, (list, tuple)) or len(value) != 3:
        errors.append(f"{field_name} 必须是恰好包含 3 个数的数组。")
        return None
    if not all(_is_finite_number(item) for item in value):
        errors.append(f"{field_name} 的元素必须是有限数值。")
        return None
    return [float(item) for item in value]


def validate_model_view_options(payload: Any) -> list[str]:
    """校验展示参数并返回有界错误列表；空列表表示通过。

    规则与 `model_view_options.v1.json` 及 Runtime 实现保持一致：
    相机选择互斥、成对约束、有限数值、背景色格式与枚举取值。
    未知字段被忽略，供宿主按 Vue attrs 处理（如 style、其他透传属性）。
    """

    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["展示参数必须是对象。"]

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name 必须是必填的非空字符串。")

    scene_index = payload.get("sceneIndex")
    if scene_index is not None and not _is_non_negative_integer(scene_index):
        errors.append("sceneIndex 必须是非负整数。")

    camera_index = payload.get("cameraIndex")
    if camera_index is not None and not _is_non_negative_integer(camera_index):
        errors.append("cameraIndex 必须是非负整数。")

    has_position = "cameraPosition" in payload
    has_target = "cameraTarget" in payload
    if has_position != has_target:
        errors.append("cameraPosition 与 cameraTarget 必须成对提供。")

    position = _validate_vector3(payload["cameraPosition"], "cameraPosition", errors) if has_position else None
    target = _validate_vector3(payload["cameraTarget"], "cameraTarget", errors) if has_target else None
    if position is not None and target is not None and position == target:
        errors.append("cameraPosition 与 cameraTarget 不能重合。")

    if camera_index is not None and has_position:
        errors.append("cameraIndex 与显式 cameraPosition/cameraTarget 互斥，只能二选一。")

    camera_fov = payload.get("cameraFov")
    if camera_fov is not None:
        if not _is_finite_number(camera_fov):
            errors.append("cameraFov 必须是有限数值。")
        elif not 0 < float(camera_fov) < 180:
            errors.append("cameraFov 必须大于 0 且小于 180。")
        elif not (has_position and has_target):
            errors.append("cameraFov 仅能与显式 cameraPosition/cameraTarget 一起使用。")

    background = payload.get("background")
    if background is not None:
        if not isinstance(background, str):
            errors.append("background 必须是字符串。")
        else:
            normalized_background = background.strip().lower()
            if normalized_background != _BACKGROUND_TRANSPARENT and not _HEX_COLOR_PATTERN.match(background.strip()):
                errors.append("background 只接受 transparent 或 #RGB/#RRGGBB/#RRGGBBAA 颜色。")

    lighting = payload.get("lighting")
    if lighting is not None and lighting not in {"auto", "source"}:
        errors.append("lighting 只接受 auto 或 source。")

    interactive = payload.get("interactive")
    if interactive is not None and not isinstance(interactive, bool):
        errors.append("interactive 必须是布尔值。")

    for field_name in ("fallback", "class"):
        field_value = payload.get(field_name)
        if field_value is not None and not isinstance(field_value, str):
            errors.append(f"{field_name} 必须是字符串。")

    return errors
