"""文件功能：验证 UTC 时间类型在 SQLite 往返、历史数据和 PostgreSQL 列定义中的行为。"""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import DateTime, Integer, create_engine, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.mixins import TimestampMixin
from app.schemas.common import SchemaBase


class ProbeBase(DeclarativeBase):
    """隔离测试元数据，避免创建或修改业务表。"""


class TimeRow(TimestampMixin, ProbeBase):
    """复用业务时间戳字段，检查默认值与显式业务时间。"""

    __tablename__ = "time_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class TimeResponse(SchemaBase):
    """复用接口序列化规则，验证读库后不会丢失时区后缀。"""

    created_at: datetime
    updated_at: datetime
    occurred_at: datetime | None


@pytest.fixture
def time_engine():
    """仅在内存 SQLite 中建立探针表，每次测试结束销毁连接。"""

    engine = create_engine("sqlite:///:memory:")
    ProbeBase.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.mark.parametrize("source", [
    datetime(2026, 9, 21, 2, tzinfo=UTC),
    datetime(2026, 9, 21, 10, tzinfo=timezone(timedelta(hours=8))),
    datetime(2026, 9, 21, 2),
])
def test_sqlite_should_store_utc_and_return_aware_datetime(time_engine, source: datetime) -> None:
    """不同偏移与历史 naive 输入必须落到同一 UTC 时间，查询比较也沿用相同规则。"""

    with Session(time_engine) as session:
        session.add(TimeRow(occurred_at=source))
        session.commit()
        row = session.scalars(select(TimeRow)).one()
        assert row.occurred_at == datetime(2026, 9, 21, 2, tzinfo=UTC)
        assert row.occurred_at.tzinfo == UTC
        assert row.created_at.tzinfo == UTC
        assert row.updated_at.tzinfo == UTC
        assert session.scalar(text("SELECT occurred_at FROM time_rows")) == "2026-09-21 02:00:00.000000"
        assert session.scalars(select(TimeRow).where(TimeRow.occurred_at <= source)).one().id == row.id
        response = TimeResponse.model_validate(row).model_dump(mode="json")
        assert response["occurred_at"] == "2026-09-21T02:00:00Z"
        assert response["created_at"].endswith("Z")


def test_sqlite_should_promote_legacy_values_without_changing_clock_time(time_engine) -> None:
    """直接插入旧格式模拟历史库；读取时直接补 UTC，不进行来源推断或小时平移。"""

    with time_engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO time_rows (id, created_at, updated_at, occurred_at) "
            "VALUES (1, '2026-09-21 02:00:00', '2026-09-21 03:00:00', NULL)"
        ))
    with Session(time_engine) as session:
        row = session.get(TimeRow, 1)
        assert row is not None
        assert TimeResponse.model_validate(row).model_dump(mode="json") == {
            "created_at": "2026-09-21T02:00:00Z",
            "updated_at": "2026-09-21T03:00:00Z",
            "occurred_at": None,
        }
        row.occurred_at = datetime(2026, 9, 21, 4, tzinfo=UTC)
        session.commit()
        session.refresh(row)
        assert row.updated_at.tzinfo == UTC
        assert row.updated_at != datetime(2026, 9, 21, 3, tzinfo=UTC)


def test_postgresql_should_keep_timezone_column_and_utc_values() -> None:
    """保留 PostgreSQL 原物理列类型，并在参数和结果边界统一 UTC。"""

    dialect = postgresql.dialect()
    column_type = UTCDateTime()
    source = datetime(2026, 9, 21, 10, tzinfo=timezone(timedelta(hours=8)))
    expected = datetime(2026, 9, 21, 2, tzinfo=UTC)
    assert column_type.compile(dialect=dialect) == "TIMESTAMP WITH TIME ZONE"
    assert column_type.process_bind_param(source, dialect) == expected
    assert column_type.process_result_value(source, dialect) == expected
    assert column_type.process_bind_param(None, dialect) is None
    assert column_type.process_result_value(None, dialect) is None


def test_all_model_datetime_columns_should_use_utc_type() -> None:
    """所有业务时间字段必须经过统一适配层，防止新增字段再次绕过 SQLite 时区补齐。"""

    import app.models  # noqa: F401

    raw_datetime_columns = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, DateTime)
    ]
    assert raw_datetime_columns == []
