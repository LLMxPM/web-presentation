"""文件功能：定义静帧捕获的编排选择器与目标状态回执。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from render_contracts.errors import RenderContractError

MOTION_VISUAL_MODES = frozenset({"full", "reduced"})
MOTION_STATUSES = frozenset({"applied", "skipped", "degraded"})
MAX_MOTION_TIME_MS = 3_600_000


@dataclass(slots=True, frozen=True)
class MotionSnapshot:
    """指定时刻或标签的静态采样；at_ms 与 at_label 互斥。"""

    timeline_id: str | None = None
    at_ms: int | None = None
    at_label: str | None = None
    offset_ms: int | None = None
    visual_mode: str = "full"

    def validate(self) -> None:
        """校验互斥字段、时间边界与视觉模式。"""

        if self.timeline_id is not None and not self.timeline_id.strip():
            raise RenderContractError("motion_snapshot.timeline_id 不能为空。")
        if self.at_ms is not None and self.at_label is not None:
            raise RenderContractError("motion_snapshot.at_ms 与 at_label 互斥。")
        if self.at_ms is not None and (self.at_ms < 0 or self.at_ms > MAX_MOTION_TIME_MS):
            raise RenderContractError(f"motion_snapshot.at_ms 必须在 0–{MAX_MOTION_TIME_MS} 内。")
        if self.at_label is not None and not self.at_label.strip():
            raise RenderContractError("motion_snapshot.at_label 不能为空。")
        if self.offset_ms is not None:
            if self.at_label is None:
                raise RenderContractError("motion_snapshot.offset_ms 只能与 at_label 一起使用。")
            if abs(self.offset_ms) > MAX_MOTION_TIME_MS:
                raise RenderContractError("motion_snapshot.offset_ms 超出允许范围。")
        if self.visual_mode not in MOTION_VISUAL_MODES:
            raise RenderContractError("motion_snapshot.visual_mode 必须为 full 或 reduced。")

    def to_dict(self) -> dict[str, Any]:
        """序列化时省略未声明字段，保持稳定身份。"""

        payload: dict[str, Any] = {"visual_mode": self.visual_mode}
        if self.timeline_id is not None:
            payload["timeline_id"] = self.timeline_id
        if self.at_ms is not None:
            payload["at_ms"] = self.at_ms
        if self.at_label is not None:
            payload["at_label"] = self.at_label
        if self.offset_ms is not None:
            payload["offset_ms"] = self.offset_ms
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MotionSnapshot":
        """从协议字典解析选择器；未提供时间时表示默认 poster。"""

        snapshot = cls(
            timeline_id=(str(payload["timeline_id"]) if payload.get("timeline_id") is not None else None),
            at_ms=(int(payload["at_ms"]) if payload.get("at_ms") is not None else None),
            at_label=(str(payload["at_label"]) if payload.get("at_label") is not None else None),
            offset_ms=(int(payload["offset_ms"]) if payload.get("offset_ms") is not None else None),
            visual_mode=str(payload.get("visual_mode") or "full"),
        )
        snapshot.validate()
        return snapshot


@dataclass(slots=True, frozen=True)
class AppliedMotion:
    """Runtime 返回的静态采样回执；applied 必须带完整计划与状态摘要。"""

    status: str
    timeline_id: str | None = None
    plan_digest: str | None = None
    sampled_time_ms: int | None = None
    state_digest: str | None = None
    visual_mode: str | None = None
    message: str | None = None

    def validate(self) -> None:
        """校验状态与必填字段的对应关系。"""

        if self.status not in MOTION_STATUSES:
            raise RenderContractError("applied_motion.status 非法。")
        if self.status == "applied":
            if not self.timeline_id or not self.plan_digest or self.sampled_time_ms is None or not self.state_digest:
                raise RenderContractError("applied_motion 成功回执缺少时间轴、计划或状态摘要。")
            if self.visual_mode not in MOTION_VISUAL_MODES:
                raise RenderContractError("applied_motion.visual_mode 非法。")
        if self.sampled_time_ms is not None and self.sampled_time_ms < 0:
            raise RenderContractError("applied_motion.sampled_time_ms 不能为负。")

    def to_dict(self) -> dict[str, Any]:
        """输出有界回执，不携带 DOM、场景或媒体字节。"""

        payload: dict[str, Any] = {"status": self.status}
        for key in ("timeline_id", "plan_digest", "sampled_time_ms", "state_digest", "visual_mode", "message"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AppliedMotion":
        """从协议字典解析回执并校验。"""

        receipt = cls(
            status=str(payload.get("status") or ""),
            timeline_id=(str(payload["timeline_id"]) if payload.get("timeline_id") is not None else None),
            plan_digest=(str(payload["plan_digest"]) if payload.get("plan_digest") is not None else None),
            sampled_time_ms=(int(payload["sampled_time_ms"]) if payload.get("sampled_time_ms") is not None else None),
            state_digest=(str(payload["state_digest"]) if payload.get("state_digest") is not None else None),
            visual_mode=(str(payload["visual_mode"]) if payload.get("visual_mode") is not None else None),
            message=(str(payload["message"]) if payload.get("message") is not None else None),
        )
        receipt.validate()
        return receipt
