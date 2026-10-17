"""文件功能：定义项目与路由的自动放映配置 Schema、严格解析器及 Runtime 下发映射。

本模块是放映参数（翻页动画、停留时间、循环与自动开始）的唯一字段基线：
项目保存完整规范化对象，叶子路由保存按组覆盖，Runtime 由同一解析器派生 camelCase 结构。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 放映配置结构版本，随能力自省与模板包 schema 一起演进。
SLIDESHOW_SCHEMA_VERSION = 1

TransitionEffect = Literal["none", "fade", "push"]
AdvanceMode = Literal["manual", "timer"]

SLIDESHOW_TRANSITION_EFFECTS: tuple[TransitionEffect, ...] = ("none", "fade", "push")
SLIDESHOW_ADVANCE_MODES: tuple[AdvanceMode, ...] = ("manual", "timer")

# 与契约一致的数值边界；none 效果必须为 0，由模型校验器强制。
TRANSITION_DURATION_MIN_MS = 100
TRANSITION_DURATION_MAX_MS = 2000
ADVANCE_DELAY_MIN_MS = 1000
ADVANCE_DELAY_MAX_MS = 3600000

DEFAULT_TRANSITION_EFFECT: TransitionEffect = "fade"
DEFAULT_TRANSITION_DURATION_MS = 400
DEFAULT_ADVANCE_MODE: AdvanceMode = "manual"
DEFAULT_ADVANCE_DELAY_MS = 5000

StrictInt = Annotated[int, Field(strict=True)]
StrictBool = Annotated[bool, Field(strict=True)]


class SlideshowTransition(BaseModel):
    """整页翻页动画设置，none 时长必须为 0。"""

    model_config = ConfigDict(extra="forbid")

    effect: TransitionEffect = Field(description="整页动画效果：none、fade 或 push。")
    duration_ms: StrictInt = Field(
        ge=0,
        le=TRANSITION_DURATION_MAX_MS,
        description="动画时长（毫秒）；none 必须为 0，其它效果为 100–2000。",
    )

    @model_validator(mode="after")
    def validate_effect_duration(self) -> SlideshowTransition:
        """收敛 none 与时长约束，避免保存无法执行或语义矛盾的组合。"""

        if self.effect == "none":
            if self.duration_ms != 0:
                raise ValueError("翻页动画为 none 时 duration_ms 必须为 0。")
            return self
        if self.duration_ms < TRANSITION_DURATION_MIN_MS:
            raise ValueError(
                f"翻页动画不为 none 时 duration_ms 必须在 {TRANSITION_DURATION_MIN_MS}–{TRANSITION_DURATION_MAX_MS} 之间。"
            )
        return self


class SlideshowAdvance(BaseModel):
    """翻页推进设置，手动模式保留延迟值但不运行计时。"""

    model_config = ConfigDict(extra="forbid")

    mode: AdvanceMode = Field(description="翻页模式：manual 或 timer。")
    delay_ms: StrictInt = Field(
        ge=ADVANCE_DELAY_MIN_MS,
        le=ADVANCE_DELAY_MAX_MS,
        description="当前页就绪且过渡结束后的停留时间（毫秒）。",
    )


class SlideshowSettings(BaseModel):
    """项目完整放映配置，所有字段必须显式提供，避免客户端猜测补全。"""

    model_config = ConfigDict(extra="forbid")

    transition: SlideshowTransition = Field(description="项目默认翻页动画。")
    advance: SlideshowAdvance = Field(description="项目默认翻页推进设置。")
    loop: StrictBool = Field(description="自动到达末页后是否回到第一个可放映叶子页。")
    auto_start: StrictBool = Field(description="正常放映宿主就绪后是否尝试自动开始。")


def default_slideshow_settings() -> SlideshowSettings:
    """返回契约规定的项目默认完整放映配置。"""

    return SlideshowSettings(
        transition=SlideshowTransition(effect=DEFAULT_TRANSITION_EFFECT, duration_ms=DEFAULT_TRANSITION_DURATION_MS),
        advance=SlideshowAdvance(mode=DEFAULT_ADVANCE_MODE, delay_ms=DEFAULT_ADVANCE_DELAY_MS),
        loop=False,
        auto_start=False,
    )


def default_slideshow_payload() -> dict[str, Any]:
    """返回 API/数据库使用的默认规范化 JSON 对象。"""

    return default_slideshow_settings().model_dump(mode="json")


def normalize_slideshow_settings(value: object) -> SlideshowSettings:
    """将项目配置 JSON 或 DTO 规范化为完整配置，非法数据直接抛校验错误。"""

    if isinstance(value, SlideshowSettings):
        return value
    if not isinstance(value, dict):
        raise TypeError("放映配置必须是完整 JSON 对象。")
    return SlideshowSettings.model_validate(value)


def load_slideshow_settings(value: object | None) -> SlideshowSettings:
    """读取已保存配置；历史空值按契约补默认完整值。"""

    if value is None:
        return default_slideshow_settings()
    return normalize_slideshow_settings(value)


def parse_route_transition_override(value: object | None) -> SlideshowTransition | None:
    """解析叶子路由动画覆盖；None 表示继承项目默认值。"""

    if value is None:
        return None
    if isinstance(value, SlideshowTransition):
        return value
    if not isinstance(value, dict):
        raise TypeError("路由动画覆盖必须是完整 JSON 对象或 null。")
    return SlideshowTransition.model_validate(value)


def parse_route_advance_override(value: object | None) -> SlideshowAdvance | None:
    """解析叶子路由推进覆盖；None 表示继承项目默认值。"""

    if value is None:
        return None
    if isinstance(value, SlideshowAdvance):
        return value
    if not isinstance(value, dict):
        raise TypeError("路由翻页覆盖必须是完整 JSON 对象或 null。")
    return SlideshowAdvance.model_validate(value)


@dataclass(frozen=True, slots=True)
class EffectiveSlideshow:
    """单个叶子路由的只读生效值，按组独立回退到项目默认值。"""

    transition: SlideshowTransition
    advance: SlideshowAdvance

    def to_api_dict(self) -> dict[str, Any]:
        """返回 API 响应使用的 snake_case 生效值。"""

        return {
            "transition": self.transition.model_dump(mode="json"),
            "advance": self.advance.model_dump(mode="json"),
        }


def resolve_effective_slideshow(
    project_settings: SlideshowSettings,
    transition_override: SlideshowTransition | None,
    advance_override: SlideshowAdvance | None,
) -> EffectiveSlideshow:
    """按整组覆盖语义解析叶子路由生效值，组内不做部分字段继承。"""

    return EffectiveSlideshow(
        transition=transition_override or project_settings.transition,
        advance=advance_override or project_settings.advance,
    )


def build_runtime_transition(transition: SlideshowTransition) -> dict[str, Any]:
    """将动画设置转换为 Runtime camelCase 结构。"""

    return {"effect": transition.effect, "durationMs": transition.duration_ms}


def build_runtime_advance(advance: SlideshowAdvance) -> dict[str, Any]:
    """将推进设置转换为 Runtime camelCase 结构。"""

    return {"mode": advance.mode, "delayMs": advance.delay_ms}


def build_runtime_slideshow_defaults(settings: SlideshowSettings) -> dict[str, Any]:
    """生成项目级 Runtime 下发片段，保留现有 transitionDefaults 形状。"""

    return {
        "transitionDefaults": build_runtime_transition(settings.transition),
        "playback": {
            "autoStart": settings.auto_start,
            "loop": settings.loop,
            "advanceDefaults": build_runtime_advance(settings.advance),
        },
    }
