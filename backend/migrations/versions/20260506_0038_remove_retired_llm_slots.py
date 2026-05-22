"""移除已退役智能体的大模型槽位绑定。

Revision ID: 20260506_0038
Revises: 20260505_0037
Create Date: 2026-05-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260506_0038"
down_revision: str | None = "20260505_0037"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """删除不再开放的页面编辑与项目管理智能体槽位绑定。"""

    op.execute(
        sa.text(
            "DELETE FROM ai_llm_slot_bindings "
            "WHERE slot IN ('page_editor', 'project_manager')"
        )
    )


def downgrade() -> None:
    """数据删除不可逆；回滚时不恢复旧槽位绑定。"""

