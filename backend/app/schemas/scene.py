"""文件功能：声明当前 Scene 任务与独立静态呈现的公开能力，不携带旧时间计划或取帧词汇。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.schemas.slideshow import SLIDESHOW_EXECUTABLE_ADVANCE_MODES


class ExternalSceneCapabilities(BaseModel):
    """开发支持范围；真实浏览器、媒体与产物证据由 C3 独立验收。"""

    model_config = ConfigDict(extra="forbid")
    schema_version: int
    enabled: bool
    task_roles: list[str]
    task_types: list[str]
    advance_modes: list[str]
    max_tasks: int
    prepare_timeout_ms: int
    completion_timeout_ms: int
    static_presentation: str


def build_scene_capabilities() -> ExternalSceneCapabilities:
    """从当前执行约束构造有界能力声明，媒体许可不由 enabled 布尔值保证。"""
    return ExternalSceneCapabilities(schema_version=1, enabled=True, task_roles=["blocking", "ambient"],
                                     task_types=["visual", "model3d", "media", "custom"], advance_modes=list(SLIDESHOW_EXECUTABLE_ADVANCE_MODES),
                                     max_tasks=128, prepare_timeout_ms=25000, completion_timeout_ms=3600000, static_presentation="independent")
