"""文件功能：验证数据库连接错误日志的脱敏、分类和可读性。"""

from sqlalchemy.exc import SQLAlchemyError, OperationalError

from app.db.errors import (
    describe_database_target,
    format_database_connectivity_error,
    is_database_connectivity_error,
    is_database_timeout_error,
)


def test_database_timeout_log_should_hide_password_and_include_target() -> None:
    """连接超时日志应说明目标库和排查方向，但不能暴露数据库密码。"""

    error = OperationalError("select 1", {}, TimeoutError("connection timed out"))
    database_url = "postgresql+asyncpg://postgres:secret@db.example.com:5432/web_presentation"

    message = format_database_connectivity_error(error, database_url, phase="Backend 启动时")

    assert is_database_connectivity_error(error)
    assert is_database_timeout_error(error)
    assert "数据库连接超时" in message
    assert "host=db.example.com" in message
    assert "port=5432" in message
    assert "database=web_presentation" in message
    assert "DATABASE_CONNECT_TIMEOUT_SECONDS" in message
    assert "secret" not in message
    assert "postgres:secret" not in message
    assert "select 1" not in message


def test_database_target_description_should_support_sqlite() -> None:
    """SQLite 测试库日志只输出文件路径，不包含无意义的 host 和 port。"""

    target = describe_database_target("sqlite+aiosqlite:///tmp/test.db")

    assert target == "driver=sqlite+aiosqlite database=tmp/test.db"


def test_plain_sqlalchemy_error_should_not_be_treated_as_connectivity_error() -> None:
    """普通 SQLAlchemy 异常不应被数据库连接错误处理器吞掉。"""

    error = SQLAlchemyError("statement syntax error")

    assert not is_database_connectivity_error(error)
