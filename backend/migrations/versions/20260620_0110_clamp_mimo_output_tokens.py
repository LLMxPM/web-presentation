"""收敛 MiMo 旧配置中过大的输出 token 上限。

Revision ID: 20260620_0110
Revises: 20260620_0109
Create Date: 2026-06-20 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260620_0110"
down_revision: Union[str, Sequence[str], None] = "20260620_0109"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """把历史 MiMo 配置截断到服务端当前允许的最大 completion token。"""

    op.execute(
        """
        UPDATE ai_llm_configs
        SET max_output_tokens = 131072
        WHERE provider_key = 'mimo'
          AND max_output_tokens > 131072
        """
    )


def downgrade() -> None:
    """数据收敛不可逆，回滚时保留当前可用配置。"""

