"""文件功能：统一数据库时间的 UTC 读写语义，并为历史无时区时间补齐 UTC。"""

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core.time_utils import normalize_utc


class UTCDateTime(TypeDecorator[datetime]):
    """保存 UTC 时间；SQLite 使用无时区 UTC 值，所有数据库读回 UTC aware 值。"""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """写入前转换为 UTC；历史 naive 输入直接视为 UTC，不推断原始时区。"""

        if value is None:
            return None
        normalized = normalize_utc(value)
        return normalized.replace(tzinfo=None) if dialect.name == "sqlite" else normalized

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """为 SQLite 及历史无时区值补 UTC，确保比较和接口序列化保留时间点。"""

        return normalize_utc(value) if value is not None else None
