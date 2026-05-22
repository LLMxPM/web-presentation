"""文件功能：提供文本内容的统一归一化能力，当前用于将源码换行符规范为 LF。"""

from __future__ import annotations


def normalize_text_to_lf(content: str | None) -> str:
    """将任意文本中的 CRLF 或 CR 统一转换为 LF，便于源码比对与版本管理。"""

    if content is None:
        return ""
    return str(content).replace("\r\n", "\n").replace("\r", "\n")
