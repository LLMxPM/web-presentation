"""文件功能：定义远程 MCP 服务自省的版本化公开 DTO，inactive 不暴露主体信息。"""

from typing import Literal

from pydantic import BaseModel, Field


class OAuthInactiveIntrospection(BaseModel):
    """未授权、未知或失效 Token 统一只返回 active=false。"""

    active: Literal[False] = False


class OAuthActiveIntrospection(BaseModel):
    """实时有效 MCP access 的公共身份，不含原始 Token 或服务密钥。"""

    active: Literal[True] = True
    wp_version: Literal[1] = 1
    token_type: Literal["Bearer"] = "Bearer"
    client_id: str
    sub: str
    aud: str
    iss: str
    exp: int
    iat: int
    jti: str
    grant_id: str
    scope: str
    workspace_ids: list[int] = Field(min_length=1)
