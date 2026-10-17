"""文件功能：定义自动放映配置的契约默认值，供 ORM 列默认、迁移与 Schema 共用同一事实源。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# 与 docs/developer/runtime-integration/slideshow/contract.md 保持一致的默认完整配置。
SLIDESHOW_DEFAULT_PAYLOAD: dict[str, Any] = {
    "transition": {"effect": "fade", "duration_ms": 400},
    "advance": {"mode": "manual", "delay_ms": 5000},
    "loop": False,
    "auto_start": False,
}


def default_slideshow_payload() -> dict[str, Any]:
    """返回可安全修改的默认配置副本，避免调用方污染共享常量。"""

    return deepcopy(SLIDESHOW_DEFAULT_PAYLOAD)
