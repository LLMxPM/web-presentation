"""文件功能：提供文本内容的统一归一化能力与源码指纹计算。"""

from __future__ import annotations

import hashlib


def normalize_text_to_lf(content: str | None) -> str:
    """将任意文本中的 CRLF 或 CR 统一转换为 LF，便于源码比对与版本管理。"""

    if content is None:
        return ""
    return str(content).replace("\r\n", "\n").replace("\r", "\n")


def calculate_source_hash(content: str | None) -> str:
    """计算归一化源码的 SHA-256 指纹，用于草稿并发校验。"""

    return hashlib.sha256(normalize_text_to_lf(content).encode("utf-8")).hexdigest()
