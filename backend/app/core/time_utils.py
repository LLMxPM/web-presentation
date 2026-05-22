"""文件功能：提供统一的 UTC 存储与业务时区格式化工具，避免服务层混用 naive/aware 时间。"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间，作为所有写库行为的统一基准。"""

    return datetime.now(UTC)


def normalize_utc(value: datetime) -> datetime:
    """将任意 naive/aware 时间规整为 UTC aware，兼容历史数据与多数据库行为。"""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def get_app_timezone_name() -> str:
    """读取业务时区名称，统一复用环境变量配置。"""

    return get_settings().app_timezone


def get_app_timezone() -> ZoneInfo:
    """返回业务时区对象，供格式化和日期切片逻辑使用。"""

    return ZoneInfo(get_app_timezone_name())


def to_app_timezone(value: datetime) -> datetime:
    """将输入时间转换到业务时区，便于生成版号与展示型日期。"""

    return normalize_utc(value).astimezone(get_app_timezone())


def format_in_app_timezone(value: datetime | None = None, pattern: str = "%Y%m%d-%H%M%S") -> str:
    """按业务时区格式化时间，默认输出页面版本标签所需的年月日时分秒。"""

    target = to_app_timezone(value or utc_now())
    return target.strftime(pattern)


def get_app_date_code(value: datetime | None = None) -> str:
    """按业务时区生成 YYYYMMDD 日期串，用于业务编码与目录命名。"""

    return format_in_app_timezone(value=value, pattern="%Y%m%d")
