"""文件功能：定义外部 whoami 的用户、空间、PAT 兼容信息和可区分的凭证来源 DTO。"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExternalIdentityModel(BaseModel):
    """外部身份响应拒绝意外字段，避免泄露 ORM 内部属性。"""

    model_config = ConfigDict(extra="forbid")


class ExternalIdentityUser(ExternalIdentityModel):
    """当前用户的公共信息。"""

    id: int
    username: str
    display_name: str | None
    role: str
    status: str


class ExternalIdentityWorkspace(ExternalIdentityModel):
    """授权范围内且用户仍是活跃成员的空间。"""

    id: int
    code: str
    name: str
    role: str


class ExternalPatTokenInfo(ExternalIdentityModel):
    """保留旧 CLI 使用的 PAT 字段及其含义。"""

    id: int
    name: str
    token_public_id: str
    scopes: list[str]
    expires_at: datetime | None
    all_workspaces: bool


class ExternalPatCredentialInfo(ExternalIdentityModel):
    """PAT 公共凭证来源，不返回原始 Bearer。"""

    type: Literal["pat"] = "pat"
    public_id: str
    expires_at: datetime | None


class ExternalDelegatedCredentialInfo(ExternalIdentityModel):
    """委托公共来源，不占用或伪造 PAT 标识。"""

    type: Literal["delegated"] = "delegated"
    public_id: str
    grant_id: str
    client_id: str
    service_id: str
    issuer: str
    audience: str
    expires_at: datetime


ExternalCredentialInfo = Annotated[
    ExternalPatCredentialInfo | ExternalDelegatedCredentialInfo,
    Field(discriminator="type"),
]
