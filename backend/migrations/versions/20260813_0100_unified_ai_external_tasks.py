"""文件功能：新增统一AI外部Batch、Task、组件任务表并扩展运行态状态约束。

Revision ID: 20260813_0100
Revises: 20260812_0100
Create Date: 2026-08-13 10:00:00.000000
"""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_0100"
down_revision: Union[str, Sequence[str], None] = "20260812_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建统一控制面；维护窗口要求活动AI任务已提前排空。"""

    _assert_ai_runtime_drained()
    op.create_table(
        "ai_agent_external_batches",
        sa.Column("batch_id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(128), sa.ForeignKey("ai_agent_runs.run_id"), nullable=False),
        sa.Column("session_id", sa.String(128), sa.ForeignKey("ai_agent_sessions.session_id"), nullable=False),
        sa.Column("member_run_id", sa.String(128), sa.ForeignKey("ai_agent_member_runs.member_run_id"), nullable=True),
        sa.Column("requirement_id", sa.String(128), nullable=True),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("group_key", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "sequence_no", name="uq_ai_external_batches_run_sequence"),
    )
    op.create_table(
        "ai_agent_external_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(128), nullable=False, unique=True),
        sa.Column("batch_id", sa.String(128), sa.ForeignKey("ai_agent_external_batches.batch_id"), nullable=False),
        sa.Column("run_id", sa.String(128), sa.ForeignKey("ai_agent_runs.run_id"), nullable=False),
        sa.Column("session_id", sa.String(128), sa.ForeignKey("ai_agent_sessions.session_id"), nullable=False),
        sa.Column("member_run_id", sa.String(128), sa.ForeignKey("ai_agent_member_runs.member_run_id"), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("tool_call_id", sa.String(255), nullable=False),
        sa.Column("deferred_tool_call_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("result_summary_json", sa.JSON(), nullable=True),
        sa.Column("result_consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "tool_call_id", name="uq_ai_external_tasks_run_tool_call"),
    )
    op.create_table(
        "ai_component_mutation_tasks",
        sa.Column("task_id", sa.String(128), sa.ForeignKey("ai_agent_external_tasks.task_id"), primary_key=True),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("component_id", sa.Integer(), sa.ForeignKey("workspace_components.id"), nullable=True),
        sa.Column("base_draft_hash", sa.String(64), nullable=True),
        sa.Column("base_published_version_no", sa.Integer(), nullable=True),
        sa.Column("arguments_json", sa.JSON(), nullable=False),
    )
    for table, columns in {
        "ai_agent_external_batches": ("run_id", "session_id", "member_run_id", "requirement_id", "status", "worker_id", "lease_expires_at"),
        "ai_agent_external_tasks": ("task_id", "batch_id", "run_id", "session_id", "member_run_id", "kind", "tool_call_id", "deferred_tool_call_id", "status", "worker_id", "lease_expires_at", "progress_at", "result_consumed_at"),
        "ai_component_mutation_tasks": ("operation", "workspace_id", "component_id"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    # SQLite 与 PostgreSQL 都支持部分唯一索引，作为多实例 active Run 最终仲裁。
    active = "status IN ('running','paused','waiting_external','cancelling')"
    op.create_index(
        "uq_ai_agent_runs_active_session_agent",
        "ai_agent_runs",
        ["session_id", "agent_id"],
        unique=True,
        sqlite_where=sa.text(active),
        postgresql_where=sa.text(active),
    )
    _backfill_terminal_external_tasks()
    op.drop_index("ix_ai_image_generation_jobs_continued_at", table_name="ai_image_generation_jobs")
    op.drop_column("ai_image_generation_jobs", "continued_at")


def downgrade() -> None:
    """删除统一控制面。"""

    op.add_column("ai_image_generation_jobs", sa.Column("continued_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_ai_image_generation_jobs_continued_at", "ai_image_generation_jobs", ["continued_at"])
    op.drop_index("uq_ai_agent_runs_active_session_agent", table_name="ai_agent_runs")
    op.drop_table("ai_component_mutation_tasks")
    op.drop_table("ai_agent_external_tasks")
    op.drop_table("ai_agent_external_batches")


def _assert_ai_runtime_drained() -> None:
    """维护窗口迁移前拒绝任何父、成员、Requirement 或旧队列活动记录。"""

    connection = op.get_bind()
    checks = (
        ("ai_agent_runs", "status IN ('running','paused','waiting_external','cancelling')"),
        ("ai_agent_member_runs", "status IN ('running','paused','waiting_external')"),
        ("ai_agent_requirements", "status IN ('pending','resolving')"),
        ("ai_page_mutation_jobs", "status IN ('pending','running')"),
        ("ai_page_mutation_batches", "status IN ('pending','resuming')"),
        ("ai_image_generation_jobs", "status IN ('pending','running','waiting_provider')"),
    )
    for table, condition in checks:
        count = int(connection.execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE {condition}")).scalar() or 0)
        if count:
            raise RuntimeError(f"AI_TASK_STATE_MIGRATION_REQUIRES_DRAIN:{table}:{count}")


def _backfill_terminal_external_tasks() -> None:
    """把历史页面和图片终态任务回填为只读审计记录，不保留完整结果副本。"""

    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    page_rows = connection.execute(
        sa.text(
            "SELECT run_id, session_id, member_run_id, tool_call_id, deferred_tool_call_id, status, "
            "error_code, error_message, created_at, updated_at, finished_at "
            "FROM ai_page_mutation_jobs WHERE status IN ('succeeded','failed','cancelled') "
            "ORDER BY run_id, created_at"
        )
    ).mappings()
    for item in page_rows:
        rows.append({**dict(item), "kind": "page_mutation", "task_status": item["status"]})
    image_rows = connection.execute(
        sa.text(
            "SELECT run_id, session_id, member_run_id, tool_call_id, deferred_tool_call_id, status, "
            "error_code, error_message, created_at, updated_at, finished_at "
            "FROM ai_image_generation_jobs WHERE status IN ('completed','error','cancelled') "
            "ORDER BY run_id, created_at"
        )
    ).mappings()
    for item in image_rows:
        mapped = {"completed": "succeeded", "error": "failed", "cancelled": "cancelled"}[str(item["status"])]
        rows.append({**dict(item), "kind": "image_generation", "task_status": mapped})

    sequence_by_run: dict[str, int] = {}
    for item in sorted(rows, key=lambda row: (str(row["run_id"]), str(row.get("created_at") or ""))):
        run_id = str(item["run_id"])
        sequence = sequence_by_run.get(run_id, 0) + 1
        sequence_by_run[run_id] = sequence
        tool_call_id = str(item["tool_call_id"])
        batch_id = _legacy_id("batch", run_id, tool_call_id)
        task_id = _legacy_id("task", run_id, tool_call_id)
        created_at = item.get("created_at") or now
        updated_at = item.get("updated_at") or created_at
        finished_at = item.get("finished_at") or updated_at
        connection.execute(
            sa.text(
                "INSERT INTO ai_agent_external_batches "
                "(batch_id, run_id, session_id, member_run_id, sequence_no, status, lease_generation, "
                "finished_at, created_at, updated_at) "
                "VALUES (:batch_id, :run_id, :session_id, :member_run_id, :sequence_no, 'completed', 0, "
                ":finished_at, :created_at, :updated_at)"
            ),
            {
                "batch_id": batch_id,
                "run_id": run_id,
                "session_id": item["session_id"],
                "member_run_id": item.get("member_run_id"),
                "sequence_no": sequence,
                "finished_at": finished_at,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO ai_agent_external_tasks "
                "(task_id, batch_id, run_id, session_id, member_run_id, kind, tool_call_id, deferred_tool_call_id, "
                "status, attempt_count, progress_at, result_summary_json, result_consumed_at, error_code, error_message, "
                "finished_at, created_at, updated_at) "
                "VALUES (:task_id, :batch_id, :run_id, :session_id, :member_run_id, :kind, :tool_call_id, "
                ":deferred_tool_call_id, :status, 0, :finished_at, :summary, :finished_at, :error_code, :error_message, "
                ":finished_at, :created_at, :updated_at)"
            ),
            {
                "task_id": task_id,
                "batch_id": batch_id,
                "run_id": run_id,
                "session_id": item["session_id"],
                "member_run_id": item.get("member_run_id"),
                "kind": item["kind"],
                "tool_call_id": tool_call_id,
                "deferred_tool_call_id": item.get("deferred_tool_call_id") or tool_call_id,
                "status": item["task_status"],
                "summary": json.dumps(
                    {"kind": item["kind"], "status": item["task_status"], "migrated": True},
                    ensure_ascii=False,
                ),
                "error_code": item.get("error_code"),
                "error_message": item.get("error_message"),
                "finished_at": finished_at,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )


def _legacy_id(kind: str, run_id: str, tool_call_id: str) -> str:
    """为迁移历史记录构造跨数据库稳定ID。"""

    digest = hashlib.sha256(f"{run_id}\x1f{tool_call_id}".encode()).hexdigest()[:32]
    return f"ai-external-legacy-{kind}-{digest}"
