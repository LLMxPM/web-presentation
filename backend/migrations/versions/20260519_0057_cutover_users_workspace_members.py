"""文件功能：将旧管理员账号表切换为多用户与工作空间成员模型。

Revision ID: 20260519_0057
Revises: 20260519_0056
Create Date: 2026-05-19 01:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260519_0057"
down_revision: str | None = "20260519_0056"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _inspector() -> sa.Inspector:
    """创建当前连接的结构检查器，避免缓存迁移过程中的旧元数据。"""

    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    """检查当前数据库是否存在指定表。"""

    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """检查指定表是否存在目标字段。"""

    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    """检查指定表是否存在目标索引。"""

    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _rename_table_if_needed(old_name: str, new_name: str) -> None:
    """在新表不存在时将旧表改名为新语义。"""

    if _has_table(old_name) and not _has_table(new_name):
        op.rename_table(old_name, new_name)


def _rename_column_if_needed(
    table_name: str,
    old_name: str,
    new_name: str,
    *,
    existing_type: sa.types.TypeEngine,
    existing_nullable: bool,
) -> None:
    """在目标字段不存在时将旧字段改名为新语义。"""

    if not _has_table(table_name) or _has_column(table_name, new_name) or not _has_column(table_name, old_name):
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(
            old_name,
            new_column_name=new_name,
            existing_type=existing_type,
            existing_nullable=existing_nullable,
        )


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    """在字段不存在时补充字段。"""

    if not _has_table(table_name) or _has_column(table_name, column.name):
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(column)


def _alter_nullable_if_column(
    table_name: str,
    column_name: str,
    *,
    existing_type: sa.types.TypeEngine,
    nullable: bool,
) -> None:
    """调整字段 nullable 约束，供全局模型配置使用。"""

    if not _has_column(table_name, column_name):
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(column_name, existing_type=existing_type, nullable=nullable)


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    """删除旧命名索引，避免字段改名后留下管理员语义。"""

    if _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def _create_index_if_missing(
    table_name: str,
    index_name: str,
    columns: list[str],
    *,
    unique: bool = False,
    where: str | None = None,
) -> None:
    """按需创建普通索引或部分唯一索引。"""

    if not _has_table(table_name) or _has_index(table_name, index_name):
        return
    kwargs: dict[str, sa.TextClause] = {}
    if where is not None:
        where_clause = sa.text(where)
        kwargs["postgresql_where"] = where_clause
        kwargs["sqlite_where"] = where_clause
    op.create_index(index_name, table_name, columns, unique=unique, **kwargs)


def _ensure_users_role() -> None:
    """为历史管理员用户补充平台管理员角色。"""

    if not _has_table("users"):
        return
    if not _has_column("users", "role"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "role",
                    sa.String(length=32),
                    nullable=False,
                    server_default=sa.text("'platform_admin'"),
                )
            )
        op.execute("UPDATE users SET role = 'platform_admin' WHERE role IS NULL")
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "role",
                existing_type=sa.String(length=32),
                existing_nullable=False,
                server_default=sa.text("'workspace_user'"),
            )


def _ensure_workspace_members() -> None:
    """创建成员表，并把历史工作空间显式归属到第一个平台管理员。"""

    if not _has_table("users") or not _has_table("workspaces"):
        return
    if not _has_table("workspace_members"):
        op.create_table(
            "workspace_members",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False, server_default="member"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
        )
    _create_index_if_missing("workspace_members", "ix_workspace_members_workspace_id", ["workspace_id"])
    _create_index_if_missing("workspace_members", "ix_workspace_members_user_id", ["user_id"])

    op.execute(
        sa.text(
            """
            INSERT INTO workspace_members (
                workspace_id,
                user_id,
                role,
                status,
                created_at,
                updated_at,
                created_by,
                updated_by
            )
            SELECT
                workspaces.id,
                first_user.id,
                'owner',
                'active',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                first_user.id,
                first_user.id
            FROM workspaces
            CROSS JOIN (
                SELECT id
                FROM users
                ORDER BY id
                LIMIT 1
            ) AS first_user
            WHERE NOT EXISTS (
                SELECT 1
                FROM workspace_members
                WHERE workspace_members.workspace_id = workspaces.id
                  AND workspace_members.user_id = first_user.id
            )
            """
        )
    )


def _cutover_llm_tables() -> None:
    """切换大模型配置表的用户字段与全局/个人 scope 字段。"""

    _rename_column_if_needed(
        "ai_llm_configs",
        "admin_user_id",
        "user_id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    _rename_column_if_needed(
        "ai_llm_slot_bindings",
        "admin_user_id",
        "user_id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    _add_column_if_missing(
        "ai_llm_configs",
        sa.Column("scope", sa.String(length=32), nullable=False, server_default=sa.text("'personal'")),
    )
    _add_column_if_missing(
        "ai_llm_slot_bindings",
        sa.Column("scope", sa.String(length=32), nullable=False, server_default=sa.text("'personal'")),
    )
    _alter_nullable_if_column("ai_llm_configs", "user_id", existing_type=sa.Integer(), nullable=True)
    _alter_nullable_if_column("ai_llm_slot_bindings", "user_id", existing_type=sa.Integer(), nullable=True)

    _drop_index_if_exists("ai_llm_configs", "ix_ai_llm_configs_admin_user_id")
    _drop_index_if_exists("ai_llm_slot_bindings", "ix_ai_llm_slot_bindings_admin_user_id")
    _create_index_if_missing("ai_llm_configs", "ix_ai_llm_configs_user_id", ["user_id"])
    _create_index_if_missing("ai_llm_configs", "ix_ai_llm_configs_scope", ["scope"])
    _create_index_if_missing("ai_llm_slot_bindings", "ix_ai_llm_slot_bindings_user_id", ["user_id"])
    _create_index_if_missing("ai_llm_slot_bindings", "ix_ai_llm_slot_bindings_scope", ["scope"])
    _create_index_if_missing(
        "ai_llm_slot_bindings",
        "uq_ai_llm_slot_bindings_personal_user_slot",
        ["user_id", "slot"],
        unique=True,
        where="scope = 'personal'",
    )
    _create_index_if_missing(
        "ai_llm_slot_bindings",
        "uq_ai_llm_slot_bindings_global_slot",
        ["slot"],
        unique=True,
        where="scope = 'global'",
    )


def _cutover_agent_user_columns() -> None:
    """切换智能体相关历史表的用户字段命名。"""

    table_configs = [
        ("ai_agent_run_tasks", "ix_ai_agent_run_tasks_admin_user_id", "ix_ai_agent_run_tasks_user_id"),
        ("ai_agent_image_attachments", "ix_ai_agent_image_attachments_admin_user_id", "ix_ai_agent_image_attachments_user_id"),
        ("ai_agent_user_configs", "ix_ai_agent_user_configs_admin_user_id", "ix_ai_agent_user_configs_user_id"),
        (
            "ai_agent_tool_user_configs",
            "ix_ai_agent_tool_user_configs_admin_user_id",
            "ix_ai_agent_tool_user_configs_user_id",
        ),
    ]
    for table_name, old_index, new_index in table_configs:
        _rename_column_if_needed(
            table_name,
            "admin_user_id",
            "user_id",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
        _drop_index_if_exists(table_name, old_index)
        _create_index_if_missing(table_name, new_index, ["user_id"])


def upgrade() -> None:
    """执行旧管理员模型到多用户模型的结构切换。"""

    _rename_table_if_needed("admin_users", "users")
    _rename_table_if_needed("admin_sessions", "user_sessions")
    _ensure_users_role()
    _ensure_workspace_members()
    _cutover_llm_tables()
    _cutover_agent_user_columns()


def downgrade() -> None:
    """该切换迁移不提供自动回滚。"""

