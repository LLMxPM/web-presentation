"""文件功能：定义页内编排能力自省与开放门禁的单一字段基线。

能力默认关闭；只有 G2 验收通过后才允许通过构建期常量开放，不接受请求参数放宽。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

TIMELINE_SCHEMA_VERSION = 1
TIMELINE_CAPABILITY_ENABLED = False
TIMELINE_CAPTURE_SNAPSHOT_ENABLED = False
TIMELINE_TRACK_TYPES: tuple[str, ...] = ("dom", "audio", "video", "model3d")
# 新推进模式 timeline_end 在 WP08 完成代码，但 G2 前不进入开放列表。
TIMELINE_EXECUTABLE_ADVANCE_MODES: tuple[str, ...] = ()


class ExternalTimelineCapabilities(BaseModel):
    """编排能力基线；enabled=false 时客户端不得声明可执行。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    enabled: bool
    track_types: list[str]
    capture_snapshot: bool
    advance_modes: list[str]


def build_timeline_capabilities() -> ExternalTimelineCapabilities:
    """按当前开放常量构造能力声明，默认全部关闭。"""

    return ExternalTimelineCapabilities(
        schema_version=TIMELINE_SCHEMA_VERSION,
        enabled=TIMELINE_CAPABILITY_ENABLED,
        track_types=list(TIMELINE_TRACK_TYPES) if TIMELINE_CAPABILITY_ENABLED else [],
        capture_snapshot=TIMELINE_CAPTURE_SNAPSHOT_ENABLED,
        advance_modes=list(TIMELINE_EXECUTABLE_ADVANCE_MODES) if TIMELINE_CAPABILITY_ENABLED else [],
    )
