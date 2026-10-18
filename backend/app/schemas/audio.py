"""文件功能：定义音频资源、页面音频属性、项目音量与 cue 绑定的严格基础契约。

本模块只维护跨模块字段、默认值、校验规则和 Runtime 映射；数据库持久化、HTTP 路由与播放行为
由后续工作包接入，避免在多个模块复制音频默认值和 cue key 规则。
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

AUDIO_SCHEMA_VERSION = 1

AudioPurpose = Literal["content", "narration"]
AudioPreload = Literal["none", "metadata", "auto"]

AUDIO_ALLOWED_CONTENT_TYPES_BY_EXTENSION: dict[str, tuple[str, ...]] = {
    ".mp3": ("audio/mpeg",),
    ".m4a": ("audio/mp4", "audio/x-m4a"),
    ".aac": ("audio/aac",),
    ".ogg": ("audio/ogg",),
    ".wav": ("audio/wav", "audio/x-wav"),
}
AUDIO_ALLOWED_EXTENSIONS = frozenset(AUDIO_ALLOWED_CONTENT_TYPES_BY_EXTENSION)
AUDIO_ALLOWED_CONTENT_TYPES = frozenset(
    content_type
    for content_types in AUDIO_ALLOWED_CONTENT_TYPES_BY_EXTENSION.values()
    for content_type in content_types
)

AUDIO_CAPABILITY_AUDIO_ASSETS = "audio_assets"
AUDIO_CAPABILITY_PAGE_NARRATION = "page_narration"
AUDIO_CAPABILITY_AUDIO_CUES = "audio_cues"
AUDIO_MILESTONE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "m0": (AUDIO_CAPABILITY_AUDIO_ASSETS,),
    "m1": (AUDIO_CAPABILITY_AUDIO_ASSETS, AUDIO_CAPABILITY_PAGE_NARRATION),
    "m2": (
        AUDIO_CAPABILITY_AUDIO_ASSETS,
        AUDIO_CAPABILITY_PAGE_NARRATION,
        AUDIO_CAPABILITY_AUDIO_CUES,
    ),
}

DEFAULT_MASTER_VOLUME_PERCENT = 100
DEFAULT_NARRATION_VOLUME_PERCENT = 100
DEFAULT_EFFECTS_VOLUME_PERCENT = 30
DEFAULT_CUE_GAIN_PERCENT = 100

AUDIO_CUE_KEY_MAX_LENGTH = 80
AUDIO_CUE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+$")
AUDIO_SYSTEM_CUE_KEYS = frozenset(
    {
        "transition.forward",
        "transition.backward",
        "interaction.confirm",
        "interaction.cancel",
        "interaction.error",
        "interaction.select",
    }
)

StrictInt = Annotated[int, Field(strict=True)]
StrictBool = Annotated[bool, Field(strict=True)]
AudioName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
CueKey = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=3,
        max_length=AUDIO_CUE_KEY_MAX_LENGTH,
        pattern=AUDIO_CUE_KEY_PATTERN.pattern,
    ),
]


def _validate_strict_finite_number(value: object, *, field_name: str) -> float:
    """把 JSON number 规范化为有限浮点数，同时拒绝字符串和布尔值。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PydanticCustomError("float_type", f"{field_name} 必须是数字。")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} 必须是有限数字。")
    return normalized


def validate_audio_cue_key(value: str) -> str:
    """校验首版 cue 命名空间，只允许系统 transition key 与 interaction 扩展。"""

    if value in AUDIO_SYSTEM_CUE_KEYS or value.startswith("interaction."):
        return value
    raise ValueError("cue key 只允许 transition.forward、transition.backward 或 interaction.*。")


class AssetAudioPropsContract(BaseModel):
    """描述 `AssetAudio.v1` 可静态验证的公开属性。"""

    model_config = ConfigDict(extra="forbid")

    name: AudioName
    purpose: AudioPurpose = "content"
    controls: StrictBool | None = None
    volume: float = Field(default=1.0, ge=0, le=1)
    playback_rate: float = Field(default=1.0, ge=0.5, le=2)
    preload: AudioPreload = "metadata"
    loop: StrictBool = False
    fallback: str | None = None

    @field_validator("volume", "playback_rate", mode="before")
    @classmethod
    def validate_numeric_props(cls, value: object, info: ValidationInfo) -> float:
        """拒绝字符串数字和布尔值，保留模板数字字面量的 int/float 兼容。"""

        return _validate_strict_finite_number(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_narration_loop(self) -> AssetAudioPropsContract:
        """页面旁白不得循环，避免 `media_end` 永不完成。"""

        if self.purpose == "narration" and self.loop:
            raise ValueError("页面旁白不允许 loop=true。")
        return self

    def resolved_controls(self) -> bool:
        """返回组件实际 controls 默认值：内容显示、旁白隐藏。"""

        if self.controls is not None:
            return self.controls
        return self.purpose == "content"


class AudioVolumeSettings(BaseModel):
    """项目持久化的三段音量设置，不包含资源引用。"""

    model_config = ConfigDict(extra="forbid")

    master_volume_percent: StrictInt = Field(ge=0, le=100)
    narration_volume_percent: StrictInt = Field(ge=0, le=100)
    effects_volume_percent: StrictInt = Field(ge=0, le=100)


class AudioCueBindingInput(BaseModel):
    """项目 API 接受的 cue 资源绑定。"""

    model_config = ConfigDict(extra="forbid")

    key: CueKey
    asset_id: StrictInt = Field(gt=0)
    gain_percent: StrictInt = Field(default=DEFAULT_CUE_GAIN_PERCENT, ge=0, le=100)

    @field_validator("key")
    @classmethod
    def validate_key_namespace(cls, value: str) -> str:
        """拒绝未开放的系统命名空间，避免未来 key 与用户自定义冲突。"""

        return validate_audio_cue_key(value)


class ProjectAudioSettings(BaseModel):
    """项目音频 API 的完整设置，cue key 在同一项目内必须唯一。"""

    model_config = ConfigDict(extra="forbid")

    master_volume_percent: StrictInt = Field(ge=0, le=100)
    narration_volume_percent: StrictInt = Field(ge=0, le=100)
    effects_volume_percent: StrictInt = Field(ge=0, le=100)
    cue_bindings: list[AudioCueBindingInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_unique_cue_keys(self) -> ProjectAudioSettings:
        """阻止一个 cue key 同时绑定多个资产，确保 Runtime 解析确定。"""

        keys = [binding.key for binding in self.cue_bindings]
        if len(keys) != len(set(keys)):
            raise ValueError("同一项目的 cue key 不得重复。")
        return self

    def volume_settings(self) -> AudioVolumeSettings:
        """提取可独立写入项目 JSON 列的音量设置。"""

        return AudioVolumeSettings(
            master_volume_percent=self.master_volume_percent,
            narration_volume_percent=self.narration_volume_percent,
            effects_volume_percent=self.effects_volume_percent,
        )


class ResolvedAudioCueBinding(BaseModel):
    """Backend 快照阶段已把资产 ID 解析为逻辑名的内部结构。"""

    model_config = ConfigDict(extra="forbid")

    key: CueKey
    asset_name: AudioName
    gain_percent: StrictInt = Field(default=DEFAULT_CUE_GAIN_PERCENT, ge=0, le=100)

    @field_validator("key")
    @classmethod
    def validate_key_namespace(cls, value: str) -> str:
        """Runtime 快照和项目写入复用相同 cue key 约束。"""

        return validate_audio_cue_key(value)


def default_audio_volume_payload() -> dict[str, int]:
    """返回项目音量的唯一默认 payload。"""

    return {
        "master_volume_percent": DEFAULT_MASTER_VOLUME_PERCENT,
        "narration_volume_percent": DEFAULT_NARRATION_VOLUME_PERCENT,
        "effects_volume_percent": DEFAULT_EFFECTS_VOLUME_PERCENT,
    }


def default_project_audio_settings() -> ProjectAudioSettings:
    """返回无 cue 绑定的历史项目默认音频设置。"""

    return ProjectAudioSettings(**default_audio_volume_payload(), cue_bindings=[])


def normalize_audio_volume_settings(value: object) -> AudioVolumeSettings:
    """严格解析持久化音量对象，非对象形态直接拒绝。"""

    if isinstance(value, AudioVolumeSettings):
        return value
    if not isinstance(value, dict):
        raise TypeError("项目音量设置必须是完整 JSON 对象。")
    return AudioVolumeSettings.model_validate(value)


def load_audio_volume_settings(value: object | None) -> AudioVolumeSettings:
    """读取项目持久化值；历史空值补契约默认值。"""

    if value is None:
        return AudioVolumeSettings.model_validate(default_audio_volume_payload())
    return normalize_audio_volume_settings(value)


def normalize_project_audio_settings(value: object) -> ProjectAudioSettings:
    """严格解析项目 API 完整音频设置。"""

    if isinstance(value, ProjectAudioSettings):
        return value
    if not isinstance(value, dict):
        raise TypeError("项目音频设置必须是完整 JSON 对象。")
    return ProjectAudioSettings.model_validate(value)


def build_runtime_audio_config(
    volume: AudioVolumeSettings,
    cue_bindings: Iterable[ResolvedAudioCueBinding],
) -> dict[str, Any]:
    """把项目音量与已解析 cue 转换为 Runtime camelCase 快照。"""

    cues: dict[str, dict[str, str | float]] = {}
    for binding in sorted(cue_bindings, key=lambda item: item.key):
        cues[binding.key] = {
            "assetName": binding.asset_name,
            "gain": binding.gain_percent / 100,
        }
    return {
        "volume": {
            "master": volume.master_volume_percent / 100,
            "narration": volume.narration_volume_percent / 100,
            "effects": volume.effects_volume_percent / 100,
        },
        "cues": cues,
    }
