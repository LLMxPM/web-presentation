"""文件功能：允许 PAT 长期有效，并支持动态授权用户当前及未来加入的所有工作空间。"""

from datetime import timedelta
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260904_0100"
down_revision: Union[str, Sequence[str], None] = "20260823_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加全空间授权标记，并允许用空过期时间表达长期有效。"""

    with op.batch_alter_table("api_access_tokens") as batch_op:
        batch_op.add_column(
            sa.Column(
                "all_workspaces",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.alter_column(
            "expires_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )


def downgrade() -> None:
    """将长期令牌收敛为一年后到期，再恢复旧版非空约束。"""

    tokens = sa.table(
        "api_access_tokens",
        sa.column("id", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("expires_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(tokens.c.id, tokens.c.created_at).where(tokens.c.expires_at.is_(None))
    ).mappings()
    for row in rows:
        bind.execute(
            sa.update(tokens)
            .where(tokens.c.id == row["id"])
            .values(expires_at=row["created_at"] + timedelta(days=365))
        )

    with op.batch_alter_table("api_access_tokens") as batch_op:
        batch_op.alter_column(
            "expires_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
        batch_op.drop_column("all_workspaces")
