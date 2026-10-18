"""文件功能：定义项目音频设置的契约默认值，供 Schema、ORM 列与迁移共用单一事实源。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_MASTER_VOLUME_PERCENT = 100
DEFAULT_NARRATION_VOLUME_PERCENT = 100
DEFAULT_EFFECTS_VOLUME_PERCENT = 30
DEFAULT_CUE_GAIN_PERCENT = 100

AUDIO_DEFAULT_VOLUME_PAYLOAD: dict[str, int] = {
    "master_volume_percent": DEFAULT_MASTER_VOLUME_PERCENT,
    "narration_volume_percent": DEFAULT_NARRATION_VOLUME_PERCENT,
    "effects_volume_percent": DEFAULT_EFFECTS_VOLUME_PERCENT,
}


def default_audio_volume_payload() -> dict[str, int]:
    """返回可安全修改的默认音量副本，避免调用方污染共享常量。"""

    return deepcopy(AUDIO_DEFAULT_VOLUME_PAYLOAD)
