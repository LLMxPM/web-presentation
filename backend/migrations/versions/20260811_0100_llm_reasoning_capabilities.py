"""文件功能：迁移模型推理三态、四档与模型能力快照字段。

Revision ID: 20260811_0100
Revises: 20260809_0100
Create Date: 2026-08-11 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260811_0100"
down_revision: Union[str, Sequence[str], None] = "20260809_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增规范化能力字段、迁移旧值并移除旧推理列。"""

    with op.batch_alter_table("ai_llm_configs") as batch:
        batch.add_column(sa.Column("reasoning_mode", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("reasoning_level", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("model_max_output_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("request_max_output_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("model_capability_json", sa.JSON(), nullable=True))

    op.execute(
        """
        UPDATE ai_llm_configs
        SET reasoning_mode = CASE
                WHEN thinking_enabled IS FALSE THEN 'auto'
                WHEN lower(coalesce(thinking_effort, '')) IN ('none', 'off', 'disabled') THEN 'disabled'
                ELSE 'enabled'
            END,
            reasoning_level = CASE
                WHEN thinking_enabled IS FALSE OR lower(coalesce(thinking_effort, '')) IN ('none', 'off', 'disabled') THEN NULL
                WHEN lower(coalesce(thinking_effort, '')) = 'minimal' THEN 'low'
                WHEN lower(coalesce(thinking_effort, '')) IN ('xhigh', 'max', 'ultra') THEN 'max'
                WHEN lower(coalesce(thinking_effort, '')) IN ('low', 'medium', 'high') THEN lower(thinking_effort)
                WHEN (
                    SELECT provider_key
                    FROM ai_llm_provider_configs
                    WHERE ai_llm_provider_configs.id = ai_llm_configs.provider_config_id
                ) IN ('google', 'deepseek') THEN 'high'
                ELSE 'medium'
            END,
            model_max_output_tokens = max_output_tokens,
            request_max_output_tokens = max_output_tokens,
            model_capability_json = '{}'
        """
    )

    with op.batch_alter_table("ai_llm_configs") as batch:
        batch.alter_column("reasoning_mode", nullable=False, server_default="auto")
        batch.alter_column("model_max_output_tokens", nullable=False, server_default="65536")
        batch.alter_column("request_max_output_tokens", nullable=False, server_default="25600")
        batch.alter_column("model_capability_json", nullable=False, server_default=sa.text("'{}'"))
        batch.drop_column("thinking_enabled")
        batch.drop_column("thinking_effort")
        batch.drop_column("max_output_tokens")


def downgrade() -> None:
    """恢复旧推理开关、强度和最大输出字段。"""

    with op.batch_alter_table("ai_llm_configs") as batch:
        batch.add_column(sa.Column("thinking_enabled", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("thinking_effort", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("max_output_tokens", sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE ai_llm_configs
        SET thinking_enabled = CASE WHEN reasoning_mode = 'enabled' THEN TRUE ELSE FALSE END,
            thinking_effort = CASE WHEN reasoning_mode = 'enabled' THEN reasoning_level ELSE NULL END,
            max_output_tokens = request_max_output_tokens
        """
    )

    with op.batch_alter_table("ai_llm_configs") as batch:
        batch.alter_column("thinking_enabled", nullable=False, server_default=sa.text("0"))
        batch.alter_column("max_output_tokens", nullable=False, server_default="25600")
        batch.drop_column("reasoning_mode")
        batch.drop_column("reasoning_level")
        batch.drop_column("model_max_output_tokens")
        batch.drop_column("request_max_output_tokens")
        batch.drop_column("model_capability_json")
