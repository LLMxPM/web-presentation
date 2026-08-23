"""文件功能：不可逆清空 AI 历史并移除自委派 Member Run 数据结构。

Revision ID: 20260818_0100
Revises: 20260817_0100
Create Date: 2026-08-18 01:00:00.000000

本迁移要求维护窗口内停止 Backend 与全部任务 Worker。upgrade 会永久删除全部
AI 会话与运行历史；downgrade 只恢复空的表、列和索引结构，不恢复任何历史数据。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260818_0100"
down_revision: Union[str, Sequence[str], None] = "20260817_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """清空全部 AI 历史，并删除自委派表、字段和约束。"""

    _purge_ai_history()

    op.drop_index("uq_ai_external_batches_collecting_member", table_name="ai_agent_external_batches")
    op.drop_index("uq_ai_external_batches_collecting_parent", table_name="ai_agent_external_batches")
    _drop_member_column("ai_agent_external_tasks")
    _drop_member_column("ai_agent_external_batches")
    _drop_member_column("ai_page_mutation_jobs")
    _drop_member_column("ai_image_generation_jobs")
    _drop_member_column("ai_agent_tool_calls")

    _drop_columns(
        "ai_agent_requirements",
        ("member_run_id", "member_agent_name", "member_agent_id"),
        index_names=("ix_ai_agent_requirements_member_run_id",),
    )

    op.drop_table("ai_agent_member_runs")
    op.create_index(
        "uq_ai_external_batches_collecting_run",
        "ai_agent_external_batches",
        ["run_id"],
        unique=True,
        sqlite_where=sa.text("status = 'collecting'"),
        postgresql_where=sa.text("status = 'collecting'"),
    )


def downgrade() -> None:
    """仅恢复已移除的空结构；upgrade 清除的数据不可恢复。"""

    op.drop_index("uq_ai_external_batches_collecting_run", table_name="ai_agent_external_batches")
    _create_empty_member_run_table()

    _restore_member_column("ai_agent_tool_calls", with_foreign_key=False)
    _restore_requirement_columns()
    _restore_member_column("ai_image_generation_jobs", with_foreign_key=True)
    _restore_member_column("ai_page_mutation_jobs", with_foreign_key=True)
    _restore_member_column("ai_agent_external_batches", with_foreign_key=True)
    _restore_member_column("ai_agent_external_tasks", with_foreign_key=True)

    op.create_index(
        "uq_ai_external_batches_collecting_parent",
        "ai_agent_external_batches",
        ["run_id"],
        unique=True,
        sqlite_where=sa.text("status = 'collecting' AND member_run_id IS NULL"),
        postgresql_where=sa.text("status = 'collecting' AND member_run_id IS NULL"),
    )
    op.create_index(
        "uq_ai_external_batches_collecting_member",
        "ai_agent_external_batches",
        ["member_run_id"],
        unique=True,
        sqlite_where=sa.text("status = 'collecting' AND member_run_id IS NOT NULL"),
        postgresql_where=sa.text("status = 'collecting' AND member_run_id IS NOT NULL"),
    )


def _purge_ai_history() -> None:
    """按外键依赖顺序清理 AI 历史，保留模型配置和已生成业务对象。"""

    for table_name in (
        "ai_component_mutation_tasks",
        "ai_agent_external_tasks",
        "ai_agent_external_batches",
        "ai_page_mutation_jobs",
        "ai_page_mutation_batches",
        "ai_image_generation_jobs",
        "ai_agent_requirements",
        "ai_agent_tool_calls",
        "ai_agent_run_events",
        "ai_agent_messages",
        "ai_agent_member_runs",
        "ai_agent_image_attachments",
        "ai_agent_runs",
        "ai_agent_sessions",
    ):
        op.execute(sa.text(f"DELETE FROM {table_name}"))
    op.execute(
        sa.text(
            "DELETE FROM ai_agent_tool_user_configs "
            "WHERE tool_key = 'delegate_task_to_self'"
        )
    )


def _drop_member_column(table_name: str) -> None:
    """删除 Member 字段；仅 SQLite 重建表，避免 PostgreSQL 破坏外部依赖。"""

    _drop_columns(
        table_name,
        ("member_run_id",),
        index_names=(f"ix_{table_name}_member_run_id",),
    )


def _drop_columns(
    table_name: str,
    column_names: tuple[str, ...],
    *,
    index_names: tuple[str, ...],
) -> None:
    """按数据库能力删除列；PostgreSQL 原地删除，SQLite 使用批量重建。"""

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch:
            for index_name in index_names:
                batch.drop_index(index_name)
            for column_name in column_names:
                batch.drop_column(column_name)
        return

    inspector = sa.inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys(table_name):
        constrained_columns = set(foreign_key.get("constrained_columns") or ())
        constraint_name = foreign_key.get("name")
        if constraint_name and constrained_columns.intersection(column_names):
            op.drop_constraint(constraint_name, table_name, type_="foreignkey")
    for index_name in index_names:
        op.drop_index(index_name, table_name=table_name)
    for column_name in column_names:
        op.drop_column(table_name, column_name)


def _restore_member_column(table_name: str, *, with_foreign_key: bool) -> None:
    """为 downgrade 恢复可空 Member 字段、索引及可选外键。"""

    column = sa.Column("member_run_id", sa.String(length=128), nullable=True)
    constraint_name = f"fk_{table_name}_member_run_id_ai_agent_member_runs"
    index_name = f"ix_{table_name}_member_run_id"
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch:
            batch.add_column(column)
            if with_foreign_key:
                batch.create_foreign_key(
                    constraint_name,
                    "ai_agent_member_runs",
                    ["member_run_id"],
                    ["member_run_id"],
                )
            batch.create_index(index_name, ["member_run_id"])
        return

    op.add_column(table_name, column)
    if with_foreign_key:
        op.create_foreign_key(
            constraint_name,
            table_name,
            "ai_agent_member_runs",
            ["member_run_id"],
            ["member_run_id"],
        )
    op.create_index(index_name, table_name, ["member_run_id"])


def _restore_requirement_columns() -> None:
    """为 downgrade 恢复 Requirement 的三个 Member 展示字段。"""

    columns = (
        sa.Column("member_agent_id", sa.String(length=128), nullable=True),
        sa.Column("member_agent_name", sa.String(length=128), nullable=True),
        sa.Column("member_run_id", sa.String(length=128), nullable=True),
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("ai_agent_requirements", recreate="always") as batch:
            for column in columns:
                batch.add_column(column)
            batch.create_index("ix_ai_agent_requirements_member_run_id", ["member_run_id"])
        return

    for column in columns:
        op.add_column("ai_agent_requirements", column)
    op.create_index(
        "ix_ai_agent_requirements_member_run_id",
        "ai_agent_requirements",
        ["member_run_id"],
    )


def _create_empty_member_run_table() -> None:
    """为 downgrade 恢复空 Member Run 表，不尝试重建任何历史记录。"""

    op.create_table(
        "ai_agent_member_runs",
        sa.Column("member_run_id", sa.String(length=128), nullable=False),
        sa.Column("parent_run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("delegate_tool_call_id", sa.String(length=255), nullable=True),
        sa.Column("input_payload_json", sa.JSON(), nullable=False),
        sa.Column("message_history_json", sa.JSON(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("reasoning_content", sa.Text(), nullable=True),
        sa.Column("pending_requirement_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["parent_run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.PrimaryKeyConstraint("member_run_id"),
    )
    for column in ("agent_id", "delegate_tool_call_id", "parent_run_id", "session_id", "status"):
        op.create_index(f"ix_ai_agent_member_runs_{column}", "ai_agent_member_runs", [column])
