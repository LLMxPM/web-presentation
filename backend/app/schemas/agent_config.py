"""文件功能：定义用户级智能体配置管理接口的请求与响应模型。"""

from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import SchemaBase


class AgentToolGuideItem(SchemaBase):
    """返回给 Editor 的面向 Agent 工具调用说明。"""

    tool_name: str
    effective_description: str
    system_description: str
    instructions: str | None = None
    parameters_schema: dict[str, Any] | None = None
    call_example: dict[str, Any] | None = None
    response_example: Any | None = None
    response_notes: str | None = None
    required_context_fields: list[str] = Field(default_factory=list)
    runtime_disclosure_groups: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    risk_level: Literal["system", "read", "write", "danger"] = "read"


class AgentToolConfigItem(SchemaBase):
    """返回给 Editor 的单个工具有效配置。"""

    key: str
    label: str
    group_key: str
    group_label: str
    default_description: str
    description: str
    description_override: str | None = None
    default_instructions: str | None = None
    instructions: str | None = None
    instructions_override: str | None = None
    enabled: bool = True
    configurable: bool = True
    requires_confirmation: bool = False
    risk_level: Literal["system", "read", "write", "danger"] = "read"
    agent_guide: AgentToolGuideItem


class AgentToolGroupConfigItem(SchemaBase):
    """按工具组返回工具配置，供前端分组展示。"""

    key: str
    label: str
    description: str
    tools: list[AgentToolConfigItem] = Field(default_factory=list)


class AgentTeamMemberConfigItem(SchemaBase):
    """内容助手 Team 成员配置项，供 Editor 展示和编辑成员描述。"""

    id: str
    name: str
    icon: str
    default_description: str
    description: str
    description_override: str | None = None
    description_customized: bool = False


class AgentCatalogItem(SchemaBase):
    """内置智能体目录项，包含默认完整提示词与工具目录。"""

    id: str
    name: str
    icon: str
    summary: str
    default_session_name: str
    capabilities: list[str] = Field(default_factory=list)
    scope_type: Literal["workspace", "project", "page", "component"]
    entry_kind: Literal["agent", "team"] = "agent"
    llm_slot: str
    default_description: str
    description: str
    description_override: str | None = None
    description_customized: bool = False
    role: str
    system_prompt: str
    default_prompt: str
    team_members: list[AgentTeamMemberConfigItem] = Field(default_factory=list)
    tool_groups: list[AgentToolGroupConfigItem] = Field(default_factory=list)


class AgentConfigItem(AgentCatalogItem):
    """当前用户对某个智能体的有效配置。"""

    prompt_override: str | None = None
    effective_prompt: str
    prompt_customized: bool = False
    enabled_tool_count: int = 0
    disabled_tool_count: int = 0


class AgentConfigUpdateRequest(BaseModel):
    """更新智能体描述或完整提示词的请求。"""

    description_override: str | None = Field(default=None, max_length=4000)
    prompt_override: str | None = Field(default=None, max_length=20000)
    restore_default: bool = False


class AgentToolConfigUpdateRequest(BaseModel):
    """更新单个工具开关或工具提示词覆盖的请求。"""

    enabled: bool | None = None
    description_override: str | None = Field(default=None, max_length=4000)
    instructions_override: str | None = Field(default=None, max_length=8000)
    restore_default: bool = False
