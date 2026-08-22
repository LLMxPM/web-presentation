"""文件功能：增加 Mutation 人工重试来源，并迁移已纠正的 External operation 幂等记录。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260822_0100"
down_revision: Union[str, Sequence[str], None] = "20260820_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加重试来源字段，并按历史响应类型纠正 operation key。"""

    with op.batch_alter_table("api_mutation_jobs") as batch_op:
        batch_op.add_column(sa.Column("retry_of_job_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_api_mutation_jobs_retry_of_job_id",
            "api_mutation_jobs",
            ["retry_of_job_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_mutation_jobs_retry_of", ["retry_of_job_id"])
    op.execute("UPDATE api_mutation_jobs SET status = 'pending' WHERE status = 'queued'")
    op.execute("UPDATE api_mutation_jobs SET status = 'running' WHERE status = 'finalizing'")
    _migrate_operation_keys()


def _migrate_operation_keys() -> None:
    """根据已保存响应识别旧复用 operation，无法判断的进行中记录保持原值。"""

    records = sa.table(
        "api_idempotency_records",
        sa.column("id", sa.Integer()),
        sa.column("operation", sa.String()),
        sa.column("status", sa.String()),
        sa.column("response_body", sa.JSON()),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(records.c.id, records.c.operation, records.c.status, records.c.response_body).where(
            records.c.operation.in_([
                "page.update",
                "component.update",
                "jobs.mutation.page.create",
                "jobs.mutation.component.create",
            ])
        )
    ).mappings()
    for row in rows:
        if row["status"] == "in_progress":
            continue
        response = row["response_body"] if isinstance(row["response_body"], dict) else {}
        operation = row["operation"]
        replacement = None
        if operation == "page.update":
            replacement = "page.version.restore"
        elif operation == "component.update" and response:
            replacement = "component.restore" if "message" in response else "component.version.restore_draft"
        elif operation == "jobs.mutation.page.create" and response.get("job_type") == "page_edit":
            replacement = "jobs.mutation.page.edit"
        elif operation == "jobs.mutation.component.create" and response.get("job_type") == "component_edit":
            replacement = "jobs.mutation.component.edit"
        if replacement:
            bind.execute(
                sa.update(records).where(records.c.id == row["id"]).values(operation=replacement)
            )


def downgrade() -> None:
    """恢复可确定的旧 operation key，并移除人工重试来源字段。"""

    op.execute("UPDATE api_idempotency_records SET operation = 'page.update' WHERE operation = 'page.version.restore'")
    op.execute("UPDATE api_idempotency_records SET operation = 'component.update' WHERE operation IN ('component.version.restore_draft', 'component.restore')")
    op.execute("UPDATE api_idempotency_records SET operation = 'jobs.mutation.page.create' WHERE operation = 'jobs.mutation.page.edit'")
    op.execute("UPDATE api_idempotency_records SET operation = 'jobs.mutation.component.create' WHERE operation = 'jobs.mutation.component.edit'")
    with op.batch_alter_table("api_mutation_jobs") as batch_op:
        batch_op.drop_index("ix_mutation_jobs_retry_of")
        batch_op.drop_constraint("fk_api_mutation_jobs_retry_of_job_id", type_="foreignkey")
        batch_op.drop_column("retry_of_job_id")
