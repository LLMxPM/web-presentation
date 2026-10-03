"""文件功能：将已解析的 HTTP 参数适配为 Authlib 请求，保留重复参数以拒绝歧义。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

from authlib.oauth2.rfc6749.errors import InvalidRequestError
from authlib.oauth2.rfc6749.requests import OAuth2Payload, OAuth2Request
from starlette.datastructures import Headers


class MultiValuePayload(OAuth2Payload):
    """保留原始参数列表；不能先转 dict 而丢失重复的安全相关参数。"""

    def __init__(self, pairs: Iterable[tuple[str, str]]) -> None:
        """复制请求参数，避免协议验证过程中被调用方修改。"""
        self._datalist: defaultdict[str, list[str]] = defaultdict(list)
        for key, value in pairs:
            self._datalist[key].append(value)
        self._data = {key: values[0] for key, values in self._datalist.items()}

    @property
    def data(self) -> dict[str, str]:
        """向 Authlib 提供单值读取视图。"""
        return self._data

    @property
    def datalist(self) -> defaultdict[str, list[str]]:
        """向协议验证器提供重复参数证据。"""
        return self._datalist

    def ensure_single_values(self) -> None:
        """首期仅接受单资源请求，所有重复参数统一返回 invalid_request。"""
        if any(len(values) != 1 for values in self._datalist.values()):
            raise InvalidRequestError("Duplicate request parameter.")


class ProtocolRequest(OAuth2Request):
    """与 FastAPI 无同步 IO 耦合的请求；URI 必须由受信 issuer 构造。"""

    def __init__(
        self,
        *,
        method: str,
        uri: str,
        pairs: Iterable[tuple[str, str]],
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """使用 Authlib 的 TLS 检查及大小写无关 Header；不关闭安全传输校验。"""
        super().__init__(method, uri, headers=Headers(headers or {}))
        self.payload = MultiValuePayload(pairs)

    @property
    def form(self) -> dict[str, str]:
        """向 Token grant 提供已读取的表单；HTTP 层应先限制表单大小。"""
        return self.payload.data if self.method == "POST" else {}

    @property
    def args(self) -> dict[str, str]:
        """向授权 grant 提供查询参数视图。"""
        return self.payload.data if self.method == "GET" else {}
