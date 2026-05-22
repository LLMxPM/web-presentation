"""组件版本改为草稿保存与正式发布模型。

Revision ID: 20260426_0033
Revises: 20260426_0032
Create Date: 2026-04-26 20:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260426_0033"
down_revision: str | None = "20260426_0032"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """新增组件草稿基线和发布时间字段，并保留存量发布版本历史。"""

    with op.batch_alter_table("workspace_components") as batch_op:
        batch_op.add_column(sa.Column("draft_base_version_no", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.alter_column("current_version_no", existing_type=sa.Integer(), server_default="0")

    with op.batch_alter_table("workspace_component_versions") as batch_op:
        batch_op.add_column(sa.Column("release_name", sa.String(length=128), nullable=True))

    connection = op.get_bind()
    metadata = sa.MetaData()
    components = sa.Table(
        "workspace_components",
        metadata,
        sa.Column("id", sa.Integer()),
        sa.Column("current_version_no", sa.Integer()),
        sa.Column("draft_base_version_no", sa.Integer()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    versions = sa.Table(
        "workspace_component_versions",
        metadata,
        sa.Column("component_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    component_rows = connection.execute(
        sa.select(components.c.id, components.c.current_version_no)
    ).mappings().all()
    for row in component_rows:
        published_at = connection.execute(
            sa.select(sa.func.max(versions.c.created_at)).where(versions.c.component_id == row["id"])
        ).scalar()
        connection.execute(
            components.update()
            .where(components.c.id == row["id"])
            .values(
                draft_base_version_no=row["current_version_no"] or 0,
                published_at=published_at,
            )
        )


def downgrade() -> None:
    """移除组件草稿发布模型字段。"""

    with op.batch_alter_table("workspace_component_versions") as batch_op:
        batch_op.drop_column("release_name")

    with op.batch_alter_table("workspace_components") as batch_op:
        batch_op.alter_column("current_version_no", existing_type=sa.Integer(), server_default="1")
        batch_op.drop_column("published_at")
        batch_op.drop_column("draft_base_version_no")
