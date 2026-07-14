"""文件功能：统一新增截图任务租约、AI 页面变更队列与页面截图快照字段。

Revision ID: 20260712_0500
Revises: 20260701_0100
Create Date: 2026-07-12 05:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260712_0500"
down_revision: Union[str, Sequence[str], None] = "20260701_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_page_screenshot_job_leases() -> None:
    """增加截图任务租约、取消字段和可复用的任务组成员关系。"""

    op.add_column("page_screenshot_jobs", sa.Column("worker_id", sa.String(length=128), nullable=True))
    op.add_column("page_screenshot_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("page_screenshot_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("page_screenshot_jobs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_page_screenshot_jobs_worker_id", "page_screenshot_jobs", ["worker_id"])
    op.create_index("ix_page_screenshot_jobs_lease_expires_at", "page_screenshot_jobs", ["lease_expires_at"])

    op.create_table(
        "page_screenshot_job_groups",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_page_screenshot_job_groups_workspace_id", "page_screenshot_job_groups", ["workspace_id"])
    op.create_index("ix_page_screenshot_job_groups_project_id", "page_screenshot_job_groups", ["project_id"])
    op.create_table(
        "page_screenshot_job_group_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["page_screenshot_job_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["page_screenshot_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "job_id", name="uq_page_screenshot_job_group_items_group_job"),
    )
    op.create_index("ix_page_screenshot_job_group_items_group_id", "page_screenshot_job_group_items", ["group_id"])
    op.create_index("ix_page_screenshot_job_group_items_job_id", "page_screenshot_job_group_items", ["job_id"])

    op.execute(
        sa.text(
            """
            INSERT INTO page_screenshot_job_groups
                (id, source, workspace_id, project_id, created_by, created_at, updated_at)
            SELECT
                job_group_id,
                MIN(source),
                MIN(workspace_id),
                MIN(project_id),
                MIN(created_by),
                MIN(created_at),
                MAX(updated_at)
            FROM page_screenshot_jobs
            WHERE job_group_id IS NOT NULL
            GROUP BY job_group_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO page_screenshot_job_group_items (group_id, job_id, created_at)
            SELECT job_group_id, id, created_at
            FROM page_screenshot_jobs
            WHERE job_group_id IS NOT NULL
            """
        )
    )

    # 旧版本没有数据库租约；升级后的 running 任务应由新恢复逻辑安全重排。
    op.execute(
        sa.text(
            """
            UPDATE page_screenshot_jobs
            SET lease_expires_at = CURRENT_TIMESTAMP
            WHERE status = 'running'
            """
        )
    )

    # 建立活动任务唯一索引前，先收敛历史上可能已经重复的 pending/running 记录。
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY page_id, config_hash, viewport_width, viewport_height
                        ORDER BY created_at ASC, id ASC
                    ) AS row_no
                FROM page_screenshot_jobs
                WHERE status IN ('pending', 'running')
            )
            UPDATE page_screenshot_jobs
            SET
                status = 'failed',
                error_code = 'PAGE_SCREENSHOT_JOB_DEDUPED',
                error_message = '升级时合并了重复的活动截图任务。',
                finished_at = CURRENT_TIMESTAMP,
                lease_expires_at = NULL,
                heartbeat_at = NULL
            WHERE id IN (SELECT id FROM ranked WHERE row_no > 1)
            """
        )
    )
    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "config_hash", "viewport_width", "viewport_height"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def _create_ai_page_mutation_jobs() -> None:
    """创建带租约代次的 AI 页面变更批次、任务及相关索引。"""

    op.create_table(
        "ai_page_mutation_batches",
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("run_step", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requirement_id", sa.String(length=128), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_generation", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.PrimaryKeyConstraint("batch_id"),
        sa.UniqueConstraint("run_id", "run_step", name="uq_ai_page_mutation_batches_run_step"),
    )
    for column in ("run_id", "session_id", "status", "requirement_id", "worker_id", "lease_expires_at"):
        op.create_index(f"ix_ai_page_mutation_batches_{column}", "ai_page_mutation_batches", [column])

    op.create_table(
        "ai_page_mutation_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("tool_call_id", sa.String(length=255), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("base_version_no", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["ai_page_mutation_batches.batch_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "tool_call_id", name="uq_ai_page_mutation_jobs_run_tool_call"),
    )
    for column in (
        "job_id", "batch_id", "run_id", "session_id", "tool_call_id", "operation", "workspace_id",
        "project_id", "page_id", "status", "worker_id", "lease_expires_at",
    ):
        # ORM 为 job_id 声明了 unique=True 与 index=True；迁移保持相同的命名唯一索引结构。
        op.create_index(
            f"ix_ai_page_mutation_jobs_{column}",
            "ai_page_mutation_jobs",
            [column],
            unique=column == "job_id",
        )


def _add_page_screenshot_job_snapshot() -> None:
    """固化截图任务目标页面版本，并扩展活动任务的去重范围。"""

    op.add_column("page_screenshot_jobs", sa.Column("target_page_version_no", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE page_screenshot_jobs
            SET target_page_version_no = COALESCE(
                (
                    SELECT pages.current_version_no
                    FROM pages
                    WHERE pages.id = page_screenshot_jobs.page_id
                ),
                1
            )
            WHERE target_page_version_no IS NULL
            """
        )
    )
    with op.batch_alter_table("page_screenshot_jobs") as batch_op:
        batch_op.alter_column("target_page_version_no", existing_type=sa.Integer(), nullable=False)

    op.create_index(
        "ix_page_screenshot_jobs_target_page_version_no",
        "page_screenshot_jobs",
        ["target_page_version_no"],
    )
    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "target_page_version_no", "config_hash", "viewport_width", "viewport_height"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def upgrade() -> None:
    """一次性升级截图任务、AI 页面变更任务和页面截图指针结构。"""

    _add_page_screenshot_job_leases()
    _create_ai_page_mutation_jobs()
    _add_page_screenshot_job_snapshot()
    op.add_column("pages", sa.Column("screenshot_viewport_width", sa.Integer(), nullable=True))
    op.add_column("pages", sa.Column("screenshot_viewport_height", sa.Integer(), nullable=True))


def downgrade() -> None:
    """完整移除本次合并迁移新增的表、索引和字段。"""

    op.drop_column("pages", "screenshot_viewport_height")
    op.drop_column("pages", "screenshot_viewport_width")

    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "config_hash", "viewport_width", "viewport_height"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.drop_index("ix_page_screenshot_jobs_target_page_version_no", table_name="page_screenshot_jobs")
    with op.batch_alter_table("page_screenshot_jobs") as batch_op:
        batch_op.drop_column("target_page_version_no")

    op.drop_table("ai_page_mutation_jobs")
    op.drop_table("ai_page_mutation_batches")

    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "config_hash", "viewport_width", "viewport_height", "status"],
    )
    op.drop_index("ix_page_screenshot_job_group_items_job_id", table_name="page_screenshot_job_group_items")
    op.drop_index("ix_page_screenshot_job_group_items_group_id", table_name="page_screenshot_job_group_items")
    op.drop_table("page_screenshot_job_group_items")
    op.drop_index("ix_page_screenshot_job_groups_project_id", table_name="page_screenshot_job_groups")
    op.drop_index("ix_page_screenshot_job_groups_workspace_id", table_name="page_screenshot_job_groups")
    op.drop_table("page_screenshot_job_groups")
    op.drop_index("ix_page_screenshot_jobs_lease_expires_at", table_name="page_screenshot_jobs")
    op.drop_index("ix_page_screenshot_jobs_worker_id", table_name="page_screenshot_jobs")
    op.drop_column("page_screenshot_jobs", "cancel_requested_at")
    op.drop_column("page_screenshot_jobs", "heartbeat_at")
    op.drop_column("page_screenshot_jobs", "lease_expires_at")
    op.drop_column("page_screenshot_jobs", "worker_id")
