"""文件功能：为智能体 Run 补充进程归属列，支撑多副本启动恢复只收敛自身遗留。

Revision ID: 20260929_0100
Revises: 20260926_0100
Create Date: 2026-09-29 01:00:00.000000

新增列可空，旧代码仍可读写本表；回退时先切旧代码再降级 schema。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260929_0100"
down_revision: Union[str, Sequence[str], None] = "20260926_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为 ai_agent_runs 增加 process_owner 列并建索引。"""

    op.add_column("ai_agent_runs", sa.Column("process_owner", sa.String(length=128), nullable=True))
    op.create_index("ix_ai_agent_runs_process_owner", "ai_agent_runs", ["process_owner"])


def downgrade() -> None:
    """移除 process_owner 列，回到无进程归属的旧形态。"""

    op.drop_index("ix_ai_agent_runs_process_owner", table_name="ai_agent_runs")
    op.drop_column("ai_agent_runs", "process_owner")
