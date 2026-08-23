"""文件功能：创建 PAT 访问令牌表、幂等记录表、Mutation 异步任务表，并扩展 Asset 存储状态机列。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260820_0100"
down_revision: Union[str, Sequence[str], None] = "20260819_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 PAT、幂等记录、Mutation 任务表，并为 WorkspaceAsset 扩展 storage_status 状态机字段。"""

    # 1. api_access_tokens
    op.create_table(
        "api_access_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("token_public_id", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_ip", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_access_tokens_token_public_id", "api_access_tokens", ["token_public_id"], unique=True)
    op.create_index("ix_api_access_tokens_user_id", "api_access_tokens", ["user_id"])

    # 2. api_access_token_workspaces
    op.create_table(
        "api_access_token_workspaces",
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["api_access_tokens.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_id", "workspace_id"),
    )
    op.create_index("ix_api_access_token_workspaces_workspace_id", "api_access_token_workspaces", ["workspace_id"])

    # 3. api_access_token_scopes
    op.create_table(
        "api_access_token_scopes",
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["api_access_tokens.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_id", "scope"),
    )

    # 4. api_idempotency_records
    op.create_table(
        "api_idempotency_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="in_progress"),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "workspace_id", "operation", "idempotency_key", name="uq_idempotency_user_ws_op_key"),
    )
    op.create_index("ix_api_idempotency_records_user_id", "api_idempotency_records", ["user_id"])
    op.create_index("ix_api_idempotency_records_workspace_id", "api_idempotency_records", ["workspace_id"])
    op.create_index("ix_api_idempotency_records_expires_at", "api_idempotency_records", ["expires_at"])

    # 5. api_mutation_jobs
    op.create_table(
        "api_mutation_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("base_version_no", sa.Integer(), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("idempotency_record_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("worker_id", sa.String(length=64), nullable=True),
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["idempotency_record_id"], ["api_idempotency_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_record_id", name="uq_api_mutation_jobs_idempotency_record_id"),
    )
    op.create_index("ix_api_mutation_jobs_job_id", "api_mutation_jobs", ["job_id"], unique=True)
    op.create_index("ix_api_mutation_jobs_workspace_id", "api_mutation_jobs", ["workspace_id"])
    op.create_index("ix_api_mutation_jobs_created_by", "api_mutation_jobs", ["created_by"])
    op.create_index("ix_api_mutation_jobs_status", "api_mutation_jobs", ["status"])
    op.create_index("ix_api_mutation_jobs_finished_at", "api_mutation_jobs", ["finished_at"])
    op.create_index("ix_mutation_jobs_status_lease", "api_mutation_jobs", ["status", "lease_expires_at"])
    op.create_index("ix_mutation_jobs_workspace_target", "api_mutation_jobs", ["workspace_id", "target_id"])
    op.create_index("ix_mutation_jobs_claim", "api_mutation_jobs", ["status", "next_attempt_at"])


def downgrade() -> None:
    """回滚新增的列与表。"""

    op.drop_index("ix_mutation_jobs_claim", table_name="api_mutation_jobs")
    op.drop_index("ix_mutation_jobs_workspace_target", table_name="api_mutation_jobs")
    op.drop_index("ix_mutation_jobs_status_lease", table_name="api_mutation_jobs")
    op.drop_index("ix_api_mutation_jobs_finished_at", table_name="api_mutation_jobs")
    op.drop_index("ix_api_mutation_jobs_status", table_name="api_mutation_jobs")
    op.drop_index("ix_api_mutation_jobs_created_by", table_name="api_mutation_jobs")
    op.drop_index("ix_api_mutation_jobs_workspace_id", table_name="api_mutation_jobs")
    op.drop_index("ix_api_mutation_jobs_job_id", table_name="api_mutation_jobs")
    op.drop_table("api_mutation_jobs")

    op.drop_index("ix_api_idempotency_records_expires_at", table_name="api_idempotency_records")
    op.drop_index("ix_api_idempotency_records_workspace_id", table_name="api_idempotency_records")
    op.drop_index("ix_api_idempotency_records_user_id", table_name="api_idempotency_records")
    op.drop_table("api_idempotency_records")

    op.drop_table("api_access_token_scopes")
    op.drop_index("ix_api_access_token_workspaces_workspace_id", table_name="api_access_token_workspaces")
    op.drop_table("api_access_token_workspaces")
    op.drop_index("ix_api_access_tokens_user_id", table_name="api_access_tokens")
    op.drop_index("ix_api_access_tokens_token_public_id", table_name="api_access_tokens")
    op.drop_table("api_access_tokens")
