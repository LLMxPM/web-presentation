"""文件功能：为管理员用户增加可维护的预设尺寸 JSON 字段。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.schemas.preview_size_preset import build_default_preview_size_presets


revision = "20260426_0031"
down_revision = "20260425_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增用户级预设尺寸字段，并为历史用户填充默认预设。"""

    default_presets = build_default_preview_size_presets()

    with op.batch_alter_table("admin_users") as batch_op:
        batch_op.add_column(sa.Column("preview_size_presets", sa.JSON(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE admin_users
            SET preview_size_presets = :preview_size_presets
            WHERE preview_size_presets IS NULL
            """
        ).bindparams(
            sa.bindparam(
                "preview_size_presets",
                value=default_presets,
                type_=sa.JSON(),
            ),
        )
    )

    with op.batch_alter_table("admin_users") as batch_op:
        batch_op.alter_column("preview_size_presets", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    """移除用户级预设尺寸字段。"""

    with op.batch_alter_table("admin_users") as batch_op:
        batch_op.drop_column("preview_size_presets")
