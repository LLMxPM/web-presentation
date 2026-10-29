"""文件功能：解析单区间 HTTP Range 请求头，供大文件流式下载复用。"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import AppException


@dataclass(frozen=True)
class ByteRange:
    """已校验的单区间字节范围，闭区间语义。"""

    start: int
    end: int

    @property
    def length(self) -> int:
        """返回本次响应应发送的字节数。"""

        return self.end - self.start + 1

    def to_header_value(self) -> str:
        """还原为可透传给对象存储的 Range 头。"""

        return f"bytes={self.start}-{self.end}"

    def to_content_range(self, total_size: int) -> str:
        """构造 206 响应的 Content-Range 头。"""

        return f"bytes {self.start}-{self.end}/{total_size}"


def parse_single_byte_range(range_header: str | None, total_size: int) -> ByteRange | None:
    """解析单区间 Range 头；返回 None 表示按整包响应。

    多区间、非 bytes 单位、格式非法一律退化为整包：部分响应合并的实现代价
    与实际收益不成比例，而解析差异不该变成下载失败。只有语法正确但区间越界
    才按 RFC 7233 抛出 416。
    """

    if total_size <= 0:
        return None
    raw = (range_header or "").strip()
    if not raw:
        return None

    unit, separator, spec = raw.partition("=")
    if not separator or unit.strip().lower() != "bytes":
        return None
    if "," in spec:
        return None

    start_text, range_separator, end_text = spec.strip().partition("-")
    if not range_separator:
        return None
    start_text = start_text.strip()
    end_text = end_text.strip()

    try:
        if not start_text:
            # bytes=-N 表示最后 N 个字节；N 为 0 或负数没有可返回内容。
            suffix_length = int(end_text)
            if suffix_length <= 0:
                raise _unsatisfiable(total_size)
            return ByteRange(start=max(0, total_size - suffix_length), end=total_size - 1)

        start = int(start_text)
        # 起点越界必须在补齐默认结尾之前判定：bytes=99- 的结尾默认值会小于起点，
        # 先比较 end < start 会把它误判成非法格式而退化成整包。
        if start < 0:
            return None
        if start >= total_size:
            raise _unsatisfiable(total_size)
        end = int(end_text) if end_text else total_size - 1
    except ValueError:
        return None

    if end < start:
        return None
    return ByteRange(start=start, end=min(end, total_size - 1))


def _unsatisfiable(total_size: int) -> AppException:
    """构造越界区间异常，并带上 RFC 要求的完整长度提示。"""

    return AppException(
        status_code=416,
        code="OBJECT_RANGE_NOT_SATISFIABLE",
        detail="请求的字节区间超出对象大小。",
        headers={"Content-Range": f"bytes */{total_size}"},
    )
