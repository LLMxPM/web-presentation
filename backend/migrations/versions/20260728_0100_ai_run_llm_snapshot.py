"""文件功能：为智能体运行增加实际使用模型的配置 ID 与非敏感快照。 

Revision ID: 20260728_0100
Revises: 20260723_0100
Create Date: 2026-07-28 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260728_0100"
down_revision: Union[str, Sequence[str], None] = "20260723_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加 run 级模型标识和运行参数快照。"""

    op.add_column("ai_agent_runs", sa.Column("llm_config_id", sa.Integer(), nullable=True))
    op.add_column("ai_agent_runs", sa.Column("llm_config_snapshot_json", sa.JSON(), nullable=True))
    op.create_index("ix_ai_agent_runs_llm_config_id", "ai_agent_runs", ["llm_config_id"])


def downgrade() -> None:
    """移除 run 级模型信息。"""

    op.drop_index("ix_ai_agent_runs_llm_config_id", table_name="ai_agent_runs")
    op.drop_column("ai_agent_runs", "llm_config_snapshot_json")
    op.drop_column("ai_agent_runs", "llm_config_id")
