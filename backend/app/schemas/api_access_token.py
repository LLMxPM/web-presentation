"""文件功能：定义个人访问令牌（PAT）创建、展示与响应的 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.external_operations import ALL_VALID_SCOPES


class ApiAccessTokenCreateRequest(BaseModel):
    """Web 控制台创建个人访问令牌请求。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=64, description="令牌名称")
    workspace_ids: list[int] = Field(..., min_length=1, description="授权工作空间 ID 列表")
    scopes: list[str] = Field(..., min_length=1, description="授权权限范围列表")
    expires_in_days: int = Field(default=30, ge=1, le=365, description="有效天数（1-365天）")

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, scopes: list[str]) -> list[str]:
        """校验 Scope 属于系统合法 Scope 集合。"""

        invalid = [s for s in scopes if s not in ALL_VALID_SCOPES]
        if invalid:
            raise ValueError(f"包含非法权限 Scope: {', '.join(invalid)}")
        return sorted(list(set(scopes)))

    @field_validator("workspace_ids")
    @classmethod
    def validate_workspace_ids(cls, workspace_ids: list[int]) -> list[int]:
        """拒绝重复工作空间，避免关联表复合主键冲突。"""

        if len(workspace_ids) != len(set(workspace_ids)):
            raise ValueError("workspace_ids 不允许包含重复工作空间 ID")
        return workspace_ids


class ApiAccessTokenCreateResponse(BaseModel):
    """创建个人访问令牌响应（仅此一次返回明文 Token）。"""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    token_public_id: str
    token: str = Field(..., description="明文令牌（仅创建时返回一次，请立即保存）")
    expires_at: datetime
    workspace_ids: list[int]
    scopes: list[str]
    created_at: datetime


class ApiAccessTokenItem(BaseModel):
    """个人访问令牌列表项及详情模型。"""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    token_public_id: str
    token_masked: str
    expires_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None
    last_used_ip: str | None
    is_active: bool
    workspace_ids: list[int]
    scopes: list[str]
    created_at: datetime


class ApiAccessTokenListResponse(BaseModel):
    """个人访问令牌列表响应。"""

    model_config = ConfigDict(extra="forbid")

    items: list[ApiAccessTokenItem]
    total: int
