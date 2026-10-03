"""文件功能：定义平台 Cookie 认证的 OAuth 确认与授权管理 DTO，不暴露协议凭证。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class OAuthConsentBegin(BaseModel):
    """原始授权查询字符串保留重复参数证据，禁止客户端声明用户或会话。"""

    model_config = ConfigDict(extra="forbid")
    authorization_query: str = Field(min_length=1, max_length=8192, repr=False)


class OAuthWorkspaceChoice(BaseModel):
    """当前用户仍有成员关系的具体工作空间。"""

    id: int
    name: str


class OAuthScopeChoice(BaseModel):
    """从 External operation 单一规格派生权限和相关操作说明。"""

    scope: str
    operations: list[str]


class OAuthConsentView(BaseModel):
    """nonce 仅返回本次受保护响应，不进入 URL 或浏览器持久缓存。"""

    request_id: str
    csrf_token: str = Field(repr=False)
    client_name: str
    resource: str
    scopes: list[OAuthScopeChoice]
    workspaces: list[OAuthWorkspaceChoice]
    expires_at: datetime


class OAuthConsentDecision(BaseModel):
    """确认只能缩小原请求权限，批准时必须选择至少一个具体空间。"""

    model_config = ConfigDict(extra="forbid")
    csrf_token: str = Field(min_length=32, max_length=128, repr=False)
    approved: bool
    scopes: list[str] = Field(default_factory=list, max_length=32)
    workspace_ids: list[StrictInt] = Field(default_factory=list, max_length=100)


class OAuthConsentResult(BaseModel):
    """提交成功后才返回已经校验的客户端回调地址。"""

    redirect_uri: str = Field(repr=False)


class OAuthGrantItem(BaseModel):
    """授权管理只展示公共授权身份，不能读取原始 access/refresh。"""

    grant_id: str
    client_name: str
    resource: str
    scopes: list[str]
    workspace_ids: list[int]
    workspaces: list[OAuthWorkspaceChoice]
    created_at: datetime
    revoked_at: datetime | None
    is_active: bool


class OAuthGrantList(BaseModel):
    """默认关闭时仍允许账户界面显示服务状态。"""

    enabled: bool
    items: list[OAuthGrantItem]
