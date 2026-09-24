"""文件功能：创建远程渲染执行服务所需的请求、尝试、Worker、调度与结果表。

Revision ID: 20260910_0100
Revises: 20260904_0100
Create Date: 2026-09-10 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from migrations.helpers.dialect import clear_page_screenshot_pointers, json_payload_type

revision: str = "20260910_0100"
down_revision: Union[str, Sequence[str], None] = "20260904_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建远程渲染控制面数据模型。"""

    json_type = json_payload_type()
    utc_default = sa.text("(CURRENT_TIMESTAMP)")

    op.create_table(
        "render_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_key", sa.String(length=64), nullable=False),
        sa.Column("logical_owner_key", sa.String(length=128), nullable=False),
        sa.Column("business_stage", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("schedule_category", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("component_id", sa.String(length=64), nullable=True),
        sa.Column("owner_kind", sa.String(length=32), nullable=False),
        sa.Column("owner_ref", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("render_digest", sa.String(length=64), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("snapshot_ref", json_type, nullable=False),
        sa.Column("operation_options", json_type, nullable=False),
        sa.Column("viewport", json_type, nullable=False),
        sa.Column("render_profile_digest", sa.String(length=64), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("cancel_version", sa.Integer(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_id", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("claim_generation", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=utc_default, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=utc_default, nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_render_requests_owner_stage_key",
        "render_requests",
        ["logical_owner_key", "business_stage", "operation", "request_key"],
        unique=True,
    )
    op.create_index("ix_render_requests_status_category", "render_requests", ["status", "schedule_category"])
    op.create_index("ix_render_requests_workspace_status", "render_requests", ["workspace_id", "status"])
    op.create_index("ix_render_requests_retry_after", "render_requests", ["retry_after"])

    op.create_table(
        "render_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("attempt_uid", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("worker_epoch", sa.String(length=64), nullable=True),
        sa.Column("slot_generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("cleanup_status", sa.String(length=32), nullable=False),
        sa.Column("active_occupancy", sa.Integer(), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=True),
        sa.Column("dispatch_error_code", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_descriptor", json_type, nullable=True),
        sa.Column("environment_summary", json_type, nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleaned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=utc_default, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=utc_default, nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["render_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", "attempt_no", name="uq_render_attempts_request_no"),
        sa.UniqueConstraint("attempt_uid"),
    )
    # 同一 Worker/epoch 最多一个未释放占用；终态 active_occupancy=0 不参与唯一约束。
    op.create_index(
        "uq_render_attempts_worker_epoch_active",
        "render_attempts",
        ["worker_id", "worker_epoch"],
        unique=True,
        sqlite_where=sa.text("active_occupancy = 1"),
        postgresql_where=sa.text("active_occupancy = 1"),
    )
    op.create_index("ix_render_attempts_status", "render_attempts", ["status"])
    op.create_index("ix_render_attempts_worker_epoch", "render_attempts", ["worker_id", "worker_epoch"])
    op.create_index("ix_render_attempts_request_id", "render_attempts", ["request_id"])
    op.create_index("ix_render_attempts_lease_expires_at", "render_attempts", ["lease_expires_at"])

    op.create_table(
        "render_workers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("worker_epoch", sa.String(length=64), nullable=False),
        sa.Column("service_base_url", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("isolated", sa.Boolean(), nullable=False),
        sa.Column("isolation_reason", sa.Text(), nullable=True),
        sa.Column("environment_summary", json_type, nullable=True),
        sa.Column("render_profile_digest", sa.String(length=64), nullable=True),
        sa.Column("slot_generation", sa.Integer(), nullable=False),
        sa.Column("slot_state", sa.String(length=32), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=utc_default, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=utc_default, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("worker_id", "worker_epoch", name="uq_render_workers_id_epoch"),
    )
    op.create_index("ix_render_workers_worker_id", "render_workers", ["worker_id"])
    op.create_index("ix_render_workers_last_heartbeat_at", "render_workers", ["last_heartbeat_at"])

    op.create_table(
        "render_scheduler_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("singleton_key", sa.String(length=32), nullable=False),
        sa.Column("cursor_category", sa.String(length=32), nullable=False),
        sa.Column("cursor_workspace_id", sa.Integer(), nullable=True),
        sa.Column("cursor_request_id", sa.Integer(), nullable=True),
        sa.Column("workspace_weights", json_type, nullable=False),
        sa.Column("global_concurrency_limit", sa.Integer(), nullable=False),
        sa.Column("workspace_concurrency_limit", sa.Integer(), nullable=False),
        sa.Column("queue_size_limit", sa.Integer(), nullable=False),
        sa.Column("workspace_queue_size_limit", sa.Integer(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=utc_default, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=utc_default, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("singleton_key"),
    )

    op.create_table(
        "render_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("render_profile_digest", sa.String(length=64), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("environment_summary", json_type, nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("object_refs", json_type, nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("worker_epoch", sa.String(length=64), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=utc_default, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=utc_default, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_render_results_request_id", "render_results", ["request_id"])
    op.create_index("ix_render_results_attempt_id", "render_results", ["attempt_id"])

    # 离线转换：清除无法证明新输入/profile 身份的当前有效截图指针，
    # 历史对象保留，业务读取方按“待生成”处理。不可逆：downgrade 不恢复。
    clear_page_screenshot_pointers()


def downgrade() -> None:
    """删除远程渲染控制面数据模型（不恢复历史截图指针）。"""

    op.drop_table("render_results")
    op.drop_table("render_scheduler_state")
    op.drop_table("render_workers")
    op.drop_table("render_attempts")
    op.drop_table("render_requests")
    # render_attempts 随表删除，lease_expires_at 索引一并移除。
