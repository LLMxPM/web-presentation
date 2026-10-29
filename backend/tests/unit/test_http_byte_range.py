"""文件功能：验证单区间 Range 解析的退化策略与越界语义。"""

from __future__ import annotations

import pytest

from app.core.exceptions import AppException
from app.services.http_byte_range import ByteRange, parse_single_byte_range

pytestmark = pytest.mark.unit


def test_parse_range_should_return_none_for_missing_or_unsupported_header() -> None:
    """缺省、非 bytes 单位与多区间都退化为整包响应。"""

    assert parse_single_byte_range(None, 1024) is None
    assert parse_single_byte_range("", 1024) is None
    assert parse_single_byte_range("items=0-10", 1024) is None
    assert parse_single_byte_range("bytes=0-1,4-5", 1024) is None
    assert parse_single_byte_range("bytes=abc-def", 1024) is None
    assert parse_single_byte_range("bytes=10", 1024) is None
    assert parse_single_byte_range("bytes=0-10", 0) is None


def test_parse_range_should_return_closed_interval() -> None:
    """普通闭区间直接映射为起止字节。"""

    result = parse_single_byte_range("bytes=100-199", 1000)

    assert result == ByteRange(start=100, end=199)
    assert result is not None
    assert result.length == 100


def test_parse_range_should_clamp_end_beyond_object_size() -> None:
    """结尾越界按对象大小截断，而不是判为非法。"""

    result = parse_single_byte_range("bytes=900-5000", 1000)

    assert result == ByteRange(start=900, end=999)


def test_parse_range_should_support_open_ended_and_suffix_forms() -> None:
    """开放式区间与后缀区间都要遵循 RFC 7233 的默认结尾语义。"""

    assert parse_single_byte_range("bytes=500-", 1000) == ByteRange(start=500, end=999)
    assert parse_single_byte_range("bytes=-100", 1000) == ByteRange(start=900, end=999)
    # 后缀长度超过对象大小时从头开始。
    assert parse_single_byte_range("bytes=-5000", 1000) == ByteRange(start=0, end=999)


def test_parse_range_should_reject_unreachable_start() -> None:
    """起点越过对象大小时返回 416，并带上完整长度提示。"""

    with pytest.raises(AppException) as excinfo:
        parse_single_byte_range("bytes=1000-1005", 1000)

    assert excinfo.value.status_code == 416
    assert excinfo.value.headers == {"Content-Range": "bytes */1000"}


def test_parse_range_should_reject_zero_suffix() -> None:
    """bytes=-0 没有可返回内容，按越界处理。"""

    with pytest.raises(AppException) as excinfo:
        parse_single_byte_range("bytes=-0", 1000)

    assert excinfo.value.status_code == 416


def test_byte_range_should_render_request_and_response_headers() -> None:
    """区间对象负责还原 Range 头与 Content-Range 头。"""

    byte_range = ByteRange(start=10, end=19)

    assert byte_range.to_header_value() == "bytes=10-19"
    assert byte_range.to_content_range(100) == "bytes 10-19/100"
