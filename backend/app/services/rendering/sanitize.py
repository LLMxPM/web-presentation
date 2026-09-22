"""文件功能：渲染链路日志与错误详情脱敏，避免预览 token 进入日志或接口返回。"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TOKEN_QUERY_PATTERN = re.compile(r"([?&](?:token|preview_token|access_token)=)[A-Za-z0-9_.\-]+", re.IGNORECASE)
_TOKEN_TEXT_PATTERN = re.compile(r"((?:token|preview_token|access_token)=)[A-Za-z0-9_.\-]+", re.IGNORECASE)


def sanitize_token_text(value: str) -> str:
    """脱敏任意文本中的 token 查询参数值。"""

    return _TOKEN_TEXT_PATTERN.sub(r"\1[redacted]", value)


def sanitize_url(url: str) -> str:
    """脱敏 URL 查询串中的 token 值，保留其它参数便于排障。"""

    try:
        parts = urlsplit(url)
        query = urlencode(
            [
                (key, "[redacted]") if "token" in key.lower() else (key, value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
            ],
            safe="[]",
        )
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
    except Exception:  # noqa: BLE001
        return sanitize_token_text(url)


def sanitize_error_message(message: str) -> str:
    """脱敏异常或错误详情文本。"""

    return sanitize_token_text(message)
