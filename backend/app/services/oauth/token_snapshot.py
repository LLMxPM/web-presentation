"""文件功能：定义撤销、自省与交换使用的凭证公共快照，不携带 ORM 或原始 Token。"""

from dataclasses import dataclass, field
from datetime import datetime

from app.services.oauth.snapshots import ClientSnapshot


@dataclass(frozen=True, slots=True)
class TokenSnapshot:
    """每请求数据库验证后的公共凭证身份；active 不得跨请求缓存。"""

    token_id: str
    token_hash: str = field(repr=False)
    grant_id: str
    client_id: str
    user_id: int
    issuer: str
    audience: str
    scopes: frozenset[str]
    workspace_ids: frozenset[int]
    kind: str
    created_at: datetime
    expires_at: datetime
    checked_at: datetime
    active: bool

    def check_client(self, client: ClientSnapshot) -> bool:
        """只有原用户客户端能撤销凭证，服务身份不能代管授权。"""
        return client.kind == "client" and self.client_id == client.client_id

    def is_expired(self) -> bool:
        """根据本次检查时间判断期限。"""
        return self.expires_at <= self.checked_at

    def is_revoked(self) -> bool:
        """实时校验未通过的 Token 不可自省放行。"""
        return not self.active
