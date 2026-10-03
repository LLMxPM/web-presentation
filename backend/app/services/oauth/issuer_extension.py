"""文件功能：将显式发行身份接入 Authlib RFC 9207 扩展，覆盖成功和错误授权回调。"""

from authlib.oauth2.rfc9207 import IssuerParameter


class ExplicitIssuerParameter(IssuerParameter):
    """保留 Authlib 的标准响应钩子，不自行拼接授权协议。"""

    def __init__(self, issuer: str) -> None:
        """只接受应用配置已经校验的 issuer。"""
        self.issuer = issuer

    def get_issuer(self) -> str:
        """返回与发现文档完全一致的发行身份。"""
        return self.issuer
