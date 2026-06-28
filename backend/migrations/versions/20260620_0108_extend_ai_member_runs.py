"""文件功能：扩展内容助手成员运行表，保存成员输入、历史、输出和暂停状态。

Revision ID: 20260620_0108
Revises: 20260619_0107
Create Date: 2026-06-20 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260620_0108"
down_revision: Union[str, Sequence[str], None] = "20260619_0107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为成员运行补充可恢复执行所需字段。"""

    op.add_column("ai_agent_member_runs", sa.Column("input_payload_json", sa.JSON(), nullable=True))
    op.add_column("ai_agent_member_runs", sa.Column("message_history_json", sa.JSON(), nullable=True))
    op.add_column("ai_agent_member_runs", sa.Column("content", sa.Text(), nullable=True))
    op.add_column("ai_agent_member_runs", sa.Column("reasoning_content", sa.Text(), nullable=True))
    op.add_column("ai_agent_member_runs", sa.Column("pending_requirement_json", sa.JSON(), nullable=True))
    op.execute("UPDATE ai_agent_member_runs SET input_payload_json = '{}' WHERE input_payload_json IS NULL")
    op.execute("UPDATE ai_agent_member_runs SET message_history_json = '[]' WHERE message_history_json IS NULL")
    with op.batch_alter_table("ai_agent_member_runs") as batch_op:
        batch_op.alter_column("input_payload_json", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column("message_history_json", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    """回滚成员运行可恢复执行字段。"""

    op.drop_column("ai_agent_member_runs", "pending_requirement_json")
    op.drop_column("ai_agent_member_runs", "reasoning_content")
    op.drop_column("ai_agent_member_runs", "content")
    op.drop_column("ai_agent_member_runs", "message_history_json")
    op.drop_column("ai_agent_member_runs", "input_payload_json")
