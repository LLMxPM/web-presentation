"""文件功能：一次描述部分索引谓词，生成 SQLite 与 PostgreSQL 双方言 DDL 要素。"""

from __future__ import annotations

from sqlalchemy import Index, text


def partial_index(
    name: str,
    columns: tuple[str, ...] | list[str],
    predicate: str,
    *,
    unique: bool = False,
) -> Index:
    """构造双方言 partial index，谓词只写一份。

    用法（model __table_args__）：
        partial_index("ix_foo_active", ("status",), "status = 'active'", unique=True)
    列名字符串由所属 Table 解析。
    """

    return Index(
        name,
        *columns,
        unique=unique,
        sqlite_where=text(predicate),
        postgresql_where=text(predicate),
    )
