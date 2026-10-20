"""文件功能：校验 External 主题字体来源与显式 null 组合，不改变内部 Editor 请求语义。"""

from pydantic import BaseModel

from app.core.exceptions import AppException
from app.core.platform_fonts import MONO_FONT_PRESETS, SANS_FONT_PRESETS


def validate_external_theme_fonts(payload: BaseModel, *, partial: bool) -> None:
    """按槽位验证预设、互斥来源和更新字段存在性，错误使用公共业务码。"""

    for slot, allowed in (("heading", SANS_FONT_PRESETS), ("body", SANS_FONT_PRESETS), ("code", MONO_FONT_PRESETS)):
        family_field, preset_field = f"{slot}_font_family_id", f"{slot}_font_preset"
        family_id, preset = getattr(payload, family_field), getattr(payload, preset_field)
        submitted = payload.model_fields_set & {family_field, preset_field}
        if partial and len(submitted) == 1 and getattr(payload, next(iter(submitted))) is None:
            raise AppException(
                status_code=422, code="INVALID_FONT_SOURCE_COMBINATION",
                detail=f"{slot} 字体恢复默认时必须同时将字体族和预设设为 null。",
            )
        if family_id is not None and preset is not None:
            raise AppException(
                status_code=422, code="MUTUALLY_EXCLUSIVE_FONT_SOURCE",
                detail=f"{slot} 字体不能同时指定字体族和预设。",
            )
        if preset is not None and preset.strip() not in allowed:
            raise AppException(
                status_code=422, code="UNSUPPORTED_FONT_PRESET",
                detail=f"{slot} 字体预设不受支持。",
            )
