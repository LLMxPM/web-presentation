"""文件功能：定义页面诊断附带截图的独立阶段结果与捕获策略身份。"""

from dataclasses import asdict, dataclass
from typing import Any

from render_contracts.errors import RenderContractError

CAPTURE_POLICY_VERSION = "page-static-capture.v1"


@dataclass(frozen=True, slots=True)
class ScreenshotPhaseResult:
    """截图阶段与诊断终态分离；available 必须有对应的已校验 PNG。"""

    status: str
    reason_code: str | None = None
    retryable: bool = False

    def __post_init__(self) -> None:
        """拒绝未知状态与非布尔重试值，避免把字符串 false 当成真。"""
        if self.status not in {"available", "failed", "skipped"} or type(self.retryable) is not bool:
            raise RenderContractError("截图阶段 status/retryable 非法。")
        if self.status != "available" and not self.reason_code:
            raise RenderContractError("未生成图片时必须提供 reason_code。")

    def to_dict(self) -> dict[str, Any]:
        """输出可跨进程往返的有界截图阶段结果。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScreenshotPhaseResult":
        """从协议数据解析阶段状态，不推测图片可用性。"""
        return cls(status=value.get("status"), reason_code=value.get("reason_code"), retryable=value.get("retryable", False))
