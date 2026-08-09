"""文件功能：拆分 AI 会话图片与资源库副本生命周期，并释放技术任务外键。

Revision ID: 20260809_0100
Revises: 20260807_0100
Create Date: 2026-08-09 11:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260809_0100"
down_revision: Union[str, Sequence[str], None] = "20260807_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
}
_FK_NAMES = {
    ("ai_agent_image_attachments", "promoted_asset_id"): "fk_ai_image_attachment_promoted_asset",
    ("asset_render_hint_backfill_jobs", "asset_id"): "fk_asset_render_hint_job_asset",
}


def upgrade() -> None:
    """记录附件最近资源状态，并让附件与回填任务不再阻断资源硬删除。"""

    with op.batch_alter_table("ai_agent_image_attachments") as batch:
        batch.add_column(
            sa.Column("last_promoted_asset_id", sa.Integer(), nullable=True)
        )
        batch.add_column(
            sa.Column("last_promoted_asset_name", sa.String(length=255), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "promoted_asset_deleted_at", sa.DateTime(timezone=True), nullable=True
            )
        )
    op.execute(
        """
        UPDATE ai_agent_image_attachments
        SET last_promoted_asset_id = promoted_asset_id,
            last_promoted_asset_name = (
                SELECT workspace_assets.name
                FROM workspace_assets
                WHERE workspace_assets.id = ai_agent_image_attachments.promoted_asset_id
            )
        WHERE promoted_asset_id IS NOT NULL
        """
    )
    _replace_foreign_key(
        table_name="ai_agent_image_attachments",
        column_name="promoted_asset_id",
        referred_table="workspace_assets",
        ondelete="SET NULL",
    )
    _replace_foreign_key(
        table_name="asset_render_hint_backfill_jobs",
        column_name="asset_id",
        referred_table="workspace_assets",
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """恢复旧外键约束并移除附件资源生命周期字段。"""

    _replace_foreign_key(
        table_name="asset_render_hint_backfill_jobs",
        column_name="asset_id",
        referred_table="workspace_assets",
        ondelete=None,
    )
    _replace_foreign_key(
        table_name="ai_agent_image_attachments",
        column_name="promoted_asset_id",
        referred_table="workspace_assets",
        ondelete=None,
    )
    with op.batch_alter_table("ai_agent_image_attachments") as batch:
        batch.drop_column("promoted_asset_deleted_at")
        batch.drop_column("last_promoted_asset_name")
        batch.drop_column("last_promoted_asset_id")


def _replace_foreign_key(
    *,
    table_name: str,
    column_name: str,
    referred_table: str,
    ondelete: str | None,
) -> None:
    """跨 PostgreSQL 与 SQLite 查找并替换指定单列外键。"""

    bind = op.get_bind()
    foreign_keys = sa.inspect(bind).get_foreign_keys(table_name)
    matched = next(
        (
            item
            for item in foreign_keys
            if item.get("constrained_columns") == [column_name]
            and item.get("referred_table") == referred_table
        ),
        None,
    )
    reflected_name = f"fk_{table_name}_{column_name}_{referred_table}"
    constraint_name = str((matched or {}).get("name") or reflected_name)
    new_constraint_name = _FK_NAMES.get(
        (table_name, column_name),
        f"fk_{table_name[:24]}_{column_name[:20]}",
    )
    with op.batch_alter_table(
        table_name, naming_convention=_FK_NAMING_CONVENTION
    ) as batch:
        batch.drop_constraint(constraint_name, type_="foreignkey")
        batch.create_foreign_key(
            new_constraint_name,
            referred_table,
            [column_name],
            ["id"],
            ondelete=ondelete,
        )
