"""文件功能：定义内容助手通用业务工具的稳定参数与统一返回结构。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


BusinessResourceType = Literal[
    "project",
    "page",
    "component",
    "asset",
    "theme",
    "style",
    "runtime_kit",
    "font",
]
BusinessOperation = Literal["query", "create", "update", "archive", "action"]


class EntityTarget(BaseModel):
    """描述通用工具的单个目标对象。"""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0, description="目标对象主键。")
    version: int | None = Field(default=None, ge=0, description="对象要求乐观锁时传入的版本号。")


class EntityArchiveArguments(BaseModel):
    """校验并归一化单项或批量归档参数。"""

    model_config = ConfigDict(extra="forbid")

    resource_type: BusinessResourceType
    target_ids: list[int] = Field(min_length=1, max_length=100)
    archive_reason: str | None = Field(default=None, max_length=1000)
    versions: dict[str, int] = Field(
        default_factory=dict,
        description="可选乐观锁版本，key 为字符串形式的目标 ID。",
    )

    @field_validator("target_ids")
    @classmethod
    def normalize_target_ids(cls, value: list[int]) -> list[int]:
        """保持顺序去重并拒绝非法主键。"""

        normalized: list[int] = []
        seen: set[int] = set()
        for raw_id in value:
            target_id = int(raw_id)
            if target_id <= 0:
                raise ValueError("target_ids 只能包含正整数。")
            if target_id not in seen:
                seen.add(target_id)
                normalized.append(target_id)
        return normalized


def build_mutation_envelope(
    *,
    resource_type: str,
    operation: str,
    message: str,
    data: Any,
    action: str | None = None,
    target: dict[str, Any] | None = None,
    targets: list[dict[str, Any]] | None = None,
    mutation_kind: str | None = None,
) -> dict[str, Any]:
    """构造供模型和 Editor 同时消费的统一写入结果。"""

    mutation: dict[str, Any] = {
        "kind": mutation_kind or resource_type,
        "resource_type": resource_type,
        "operation": operation,
    }
    if action:
        mutation["action"] = action
    if target:
        mutation["target"] = target
    if targets:
        mutation["targets"] = targets
    payload: dict[str, Any] = {
        "success": True,
        "resource_type": resource_type,
        "operation": operation,
        "action": action,
        "message": message,
        "mutation": mutation,
        "data": data,
    }
    if target is not None:
        payload["target"] = target
    if targets is not None:
        payload["targets"] = targets
    return payload


def build_query_envelope(
    *,
    resource_type: str,
    action: str,
    data: Any,
    message: str = "查询完成。",
) -> dict[str, Any]:
    """构造统一查询结果，不携带刷新信息。"""

    return {
        "success": True,
        "resource_type": resource_type,
        "operation": "query",
        "action": action,
        "message": message,
        "data": data,
    }
