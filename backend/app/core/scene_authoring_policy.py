"""文件功能：页面和组件源码只通过 Scene 门面使用 GSAP，拒绝直接导入核心包和插件。"""

from __future__ import annotations

import re

from app.core.exceptions import AppException

SCENE_AUTHORING_POLICY_VERSION = "page-scene-authoring.v1"
_FORBIDDEN = re.compile(r"^(?:gsap(?:-trial)?(?:/|$)|@gsap(?:/|$))", re.IGNORECASE)


def is_forbidden_scene_import(source: str) -> bool:
    """统一路径与 Vite 后缀，识别被受管视觉门面接管的包入口。"""
    normalized = re.split(r"[?#]", source.strip().replace("\\", "/"), maxsplit=1)[0]
    return bool(_FORBIDDEN.match(normalized))


def assert_scene_import_allowed(source: str) -> None:
    """写入和 CodeCheck 共用依赖解析；非法导入返回稳定错误码，不放行到浏览器执行。"""
    if is_forbidden_scene_import(source):
        raise AppException(
            status_code=400,
            code="SCENE_GSAP_IMPORT_FORBIDDEN",
            detail="页面与组件请通过 usePageScene.v1 创建视觉序列；不支持直接导入 GSAP 或插件。",
        )
