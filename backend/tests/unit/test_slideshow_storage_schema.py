"""文件功能：验证放映配置列的 ORM 默认值与双方言 DDL，防止 JSON 默认值被参数解析破坏。"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from app.core.slideshow_defaults import default_slideshow_payload
from app.models.project_route import ProjectRoute
from app.models.workspace import Project


def _compiled_create_table(table: object, dialect: object) -> str:
    """按指定方言编译建表语句，不连接真实数据库。"""

    return str(CreateTable(table).compile(dialect=dialect))  # type: ignore[arg-type]


def test_project_slideshow_column_default_should_render_as_json_literal() -> None:
    """项目列默认值必须是合法 JSON 字面量，不能被 SQLAlchemy 绑定参数替换成 NULL。"""

    for dialect in (sqlite.dialect(), postgresql.dialect()):
        ddl = _compiled_create_table(Project.__table__, dialect)
        assert '"duration_ms":400' in ddl
        assert '"duration_ms"NULL' not in ddl
        assert '"auto_start":false' in ddl


def test_route_override_columns_should_be_nullable_json() -> None:
    """路由两组覆盖必须可空，用于表达继承项目默认值。"""

    assert ProjectRoute.__table__.c.transition_json.nullable is True
    assert ProjectRoute.__table__.c.advance_json.nullable is True
    assert Project.__table__.c.slideshow_config_json.nullable is False


def test_default_payload_should_be_isolated_between_calls() -> None:
    """默认配置返回副本，调用方修改不得污染后续项目初始化。"""

    first = default_slideshow_payload()
    first["transition"]["effect"] = "push"
    assert default_slideshow_payload()["transition"]["effect"] == "fade"
