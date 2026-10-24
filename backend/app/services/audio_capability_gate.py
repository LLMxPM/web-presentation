"""文件功能：统一音频能力判定与写入门禁，保证能力声明、保存校验和执行边界一致。"""

from __future__ import annotations

from collections.abc import Iterable

from app.core.exceptions import AppException
from app.schemas import audio as audio_schema
from app.schemas.audio import AUDIO_CAPABILITY_AUDIO_CUES

AUDIO_CAPABILITY_UNAVAILABLE = "AUDIO_CAPABILITY_UNAVAILABLE"
_CUE_WRITE_CLOSED_DETAIL = (
    "当前工作空间未开放 audio_cues（capability=audio_cues），"
    "拒绝写入非空 cue 绑定；已保存的历史绑定仍可读取或用原子清空接口删除。"
)


def open_audio_capabilities() -> frozenset[str]:
    """读取当前实例的开放集合，供写入门禁和检查指纹共用。"""

    return audio_schema.get_open_audio_capabilities()


def is_audio_capability_open(capability: str) -> bool:
    """判断指定音频能力是否已通过阶段出口验收。"""

    return capability in open_audio_capabilities()


def ensure_audio_capability(capability: str, *, detail: str) -> None:
    """能力关闭时以稳定业务码 422 拒绝写入；调用方不得降级为 warning。"""

    if is_audio_capability_open(capability):
        return
    raise AppException(
        status_code=422,
        code=AUDIO_CAPABILITY_UNAVAILABLE,
        detail=detail,
    )


def ensure_cue_bindings_allowed(bindings: Iterable[object]) -> None:
    """含非空 cue 绑定的写入必须已开放 audio_cues；空集合始终允许。"""

    if not list(bindings):
        return
    ensure_audio_capability(
        AUDIO_CAPABILITY_AUDIO_CUES,
        detail=_CUE_WRITE_CLOSED_DETAIL,
    )


def audio_capability_diagnostic(capability: str, *, detail: str) -> dict[str, str] | None:
    """构造 validate 用的能力诊断；能力开放时返回 None。"""

    if is_audio_capability_open(capability):
        return None
    return {
        "code": AUDIO_CAPABILITY_UNAVAILABLE,
        "capability": capability,
        "message": detail,
    }


__all__ = [
    "AUDIO_CAPABILITY_UNAVAILABLE",
    "audio_capability_diagnostic",
    "ensure_audio_capability",
    "ensure_cue_bindings_allowed",
    "is_audio_capability_open",
    "open_audio_capabilities",
]
