"""文件功能：为工作空间组件发布版本增加内容指纹字段。

Revision ID: 20260606_0104
Revises: 20260605_0103
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260606_0104"
down_revision: Union[str, Sequence[str], None] = "20260605_0103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加组件发布版本内容 hash 与组件指纹列。"""

    op.add_column("workspace_component_versions", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("workspace_component_versions", sa.Column("preview_schema_hash", sa.String(length=64), nullable=True))
    op.add_column("workspace_component_versions", sa.Column("component_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("workspace_component_versions", sa.Column("fingerprint_schema_version", sa.Integer(), nullable=True))
    op.create_index(
        "ix_workspace_component_versions_component_fingerprint",
        "workspace_component_versions",
        ["component_fingerprint"],
        unique=False,
    )


def downgrade() -> None:
    """移除组件发布版本内容 hash 与组件指纹列。"""

    op.drop_index("ix_workspace_component_versions_component_fingerprint", table_name="workspace_component_versions")
    op.drop_column("workspace_component_versions", "fingerprint_schema_version")
    op.drop_column("workspace_component_versions", "component_fingerprint")
    op.drop_column("workspace_component_versions", "preview_schema_hash")
    op.drop_column("workspace_component_versions", "content_hash")
