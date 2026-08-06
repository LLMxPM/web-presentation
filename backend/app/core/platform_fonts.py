"""文件功能：集中定义跨端一致的内置字体 token、版本指纹与可选系统回退。"""

from typing import Final


PLATFORM_SANS_FONT: Final = "platform-sans"
PLATFORM_MONO_FONT: Final = "platform-mono"
SYSTEM_UI_FONT: Final = "system-ui"
SYSTEM_MONO_FONT: Final = "monospace"

SANS_FONT_PRESETS: Final[frozenset[str]] = frozenset({PLATFORM_SANS_FONT, SYSTEM_UI_FONT})
MONO_FONT_PRESETS: Final[frozenset[str]] = frozenset({PLATFORM_MONO_FONT, SYSTEM_MONO_FONT})

# 字体文件变化时必须更新该值，使历史截图自动失效并重新生成。
PLATFORM_FONT_REVISION: Final = (
    "source-han-sans-sc-vf:085cc88c530b9c43+"
    "source-code-pro-regular:714eee29b70d191f"
)


def resolve_font_preset(label: str | None, allowed_presets: frozenset[str]) -> str | None:
    """仅在主题未绑定工作空间字体族时，把持久化 label 解析为受支持的内置预设。"""

    normalized = str(label or "").strip()
    return normalized if normalized in allowed_presets else None
