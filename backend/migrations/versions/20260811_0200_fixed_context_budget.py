"""文件功能：把模型配置迁移到固定上下文预算并移除冗余输出与比例字段。

Revision ID: 20260811_0200
Revises: 20260811_0100
Create Date: 2026-08-11 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260811_0200"
down_revision: Union[str, Sequence[str], None] = "20260811_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """保留 context_window_tokens 原值并删除固定策略不再需要的配置列。"""

    with op.batch_alter_table("ai_llm_configs") as batch:
        batch.drop_column("model_max_output_tokens")
        batch.drop_column("request_max_output_tokens")
        batch.drop_column("compression_target_ratio")


def downgrade() -> None:
    """恢复旧列并按固定预算写入可兼容的默认值。"""

    with op.batch_alter_table("ai_llm_configs") as batch:
        batch.add_column(sa.Column("model_max_output_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("request_max_output_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("compression_target_ratio", sa.Float(), nullable=True))

    op.execute(
        """
        UPDATE ai_llm_configs
        SET model_max_output_tokens = 32768,
            request_max_output_tokens = 32768,
            compression_target_ratio = CASE
                WHEN context_window_tokens > 0 THEN 16384.0 / context_window_tokens
                ELSE 0
            END
        """
    )

    with op.batch_alter_table("ai_llm_configs") as batch:
        batch.alter_column("model_max_output_tokens", nullable=False, server_default="32768")
        batch.alter_column("request_max_output_tokens", nullable=False, server_default="32768")
        batch.alter_column("compression_target_ratio", nullable=False, server_default="0.1")
