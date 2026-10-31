"""文件功能：定义页面诊断附带截图的独立阶段结果与捕获策略身份。"""

from dataclasses import asdict, dataclass
from typing import Any

from render_contracts.errors import ERROR_CODE_STATIC_PRESENTATION_UNAVAILABLE, RenderContractError

CAPTURE_POLICY_VERSION = "page-static-capture.v3"


@dataclass(frozen=True, slots=True)
class ScreenshotPhaseResult:
    """截图阶段与诊断终态分离；available 必须有对应的已校验 PNG。"""

    status: str
    reason_code: str | None = None
    retryable: bool = False

    def __post_init__(self) -> None:
        """拒绝未知状态与非布尔重试值，避免把字符串 false 当成真。"""
        if self.status not in {"available", "failed", "skipped", "unavailable"} or type(self.retryable) is not bool:
            raise RenderContractError("截图阶段 status/retryable 非法。")
        if self.status != "available" and not self.reason_code:
            raise RenderContractError("未生成图片时必须提供 reason_code。")
        if self.reason_code is not None and (not isinstance(self.reason_code, str) or not self.reason_code.strip()):
            raise RenderContractError("截图阶段 reason_code 必须为非空字符串或 null。")
        if self.status == "available" and (self.reason_code is not None or self.retryable):
            raise RenderContractError("成功截图不能带失败原因或重试标记。")
        if self.reason_code == ERROR_CODE_STATIC_PRESENTATION_UNAVAILABLE and self.status != "unavailable":
            raise RenderContractError("内容不可呈现只能使用 unavailable，不能伪装为失败或任务跳过。")
        if self.status == "unavailable" and (self.reason_code != ERROR_CODE_STATIC_PRESENTATION_UNAVAILABLE or self.retryable):
            raise RenderContractError("静态不可呈现必须使用稳定原因码且不可重试。")

    def to_dict(self) -> dict[str, Any]:
        """输出可跨进程往返的有界截图阶段结果。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScreenshotPhaseResult":
        """从协议数据解析阶段状态，不推测图片可用性。"""
        return cls(status=value.get("status"), reason_code=value.get("reason_code"), retryable=value.get("retryable", False))
