"""文件功能：定义组件候选 contract、compile、render 校验的稳定结果与诊断契约。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ComponentValidationStatus = Literal["passed", "passed_with_warnings", "failed", "unavailable"]
ComponentValidationStageStatus = Literal[
    "passed", "passed_with_warnings", "failed", "unavailable", "skipped",
]


class ComponentValidationDiagnostic(BaseModel):
    """面向模型的单条组件诊断。"""

    model_config = ConfigDict(extra="allow")

    severity: Literal["error", "warning", "info"]
    source: str
    code: str
    message: str
    stage: Literal["contract", "compile", "render"]
    scenario_key: str | None = None
    profile_key: str | None = None
    location: dict[str, Any] | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    suggestion: str | None = None


class ComponentValidationScenarioResult(BaseModel):
    """组件默认态或 preset 的单场景结果。"""

    model_config = ConfigDict(extra="allow")

    key: str
    profile_key: str
    status: Literal["passed", "passed_with_warnings", "failed"]
    diagnostic_count: int = Field(ge=0)


class ComponentValidationResult(BaseModel):
    """组件独立 check 与自动写入 check 共用的顶层结果。"""

    model_config = ConfigDict(extra="allow")

    schema_version: int = 1
    success: bool
    valid: bool
    status: ComponentValidationStatus
    retryable: bool
    summary: str
    stages: dict[Literal["contract", "compile", "render"], ComponentValidationStageStatus]
    diagnostics: list[ComponentValidationDiagnostic] = Field(default_factory=list)
    scenarios: list[ComponentValidationScenarioResult] = Field(default_factory=list)
    candidate_hash: str | None = None
    validation_profile_version: str
    profile_key: str | None = None
    patch_repaired: bool = False
    canonical_diff: str | None = None
