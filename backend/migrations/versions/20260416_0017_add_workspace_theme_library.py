"""add workspace theme library

Revision ID: 20260416_0017
Revises: 20260415_0016
Create Date: 2026-04-16 12:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260416_0017"
down_revision: Union[str, Sequence[str], None] = "20260415_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_THEME_KEY = "lightblue"
DEFAULT_THEME_PALETTE = {
    "text": {
        "primary": "#0D286A",
        "secondary": "#1D5297",
        "invert": "#ffffff",
    },
    "background": {
        "default": "#ffffff",
        "invert": "#0D286A",
    },
    "border": {
        "default": "#e5e7eb",
        "subtle": "#d1d5db",
    },
    "link": {
        "default": "#3b82f6",
        "hover": "#2563eb",
        "visited": "#7c3aed",
    },
    "accent": [
        "#0D286A",
        "#260E6D",
        "#9E8403",
        "#9E6B03",
        "#A110AB",
        "#C5003C",
    ],
}


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(sa.Column("default_theme_key", sa.String(length=64), nullable=True))

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("theme_key", sa.String(length=64), nullable=True))

    op.create_table(
        "workspace_themes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logo_asset_id", sa.Integer(), nullable=True),
        sa.Column("invert_logo_asset_id", sa.Integer(), nullable=True),
        sa.Column("logo_path", sa.String(length=255), nullable=True),
        sa.Column("invert_logo_path", sa.String(length=255), nullable=True),
        sa.Column("heading_font_id", sa.Integer(), nullable=True),
        sa.Column("body_font_id", sa.Integer(), nullable=True),
        sa.Column("code_font_id", sa.Integer(), nullable=True),
        sa.Column("heading_font_label", sa.String(length=255), nullable=False),
        sa.Column("body_font_label", sa.String(length=255), nullable=False),
        sa.Column("code_font_label", sa.String(length=255), nullable=False),
        sa.Column("base_font_size", sa.String(length=32), nullable=False),
        sa.Column("palette", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["logo_asset_id"], ["workspace_assets.id"]),
        sa.ForeignKeyConstraint(["invert_logo_asset_id"], ["workspace_assets.id"]),
        sa.ForeignKeyConstraint(["heading_font_id"], ["workspace_font_configs.id"]),
        sa.ForeignKeyConstraint(["body_font_id"], ["workspace_font_configs.id"]),
        sa.ForeignKeyConstraint(["code_font_id"], ["workspace_font_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "key", name="uq_workspace_themes_workspace_key"),
    )
    op.create_index("ix_workspace_themes_workspace_id", "workspace_themes", ["workspace_id"])
    op.create_index("ix_workspace_themes_logo_asset_id", "workspace_themes", ["logo_asset_id"])
    op.create_index("ix_workspace_themes_invert_logo_asset_id", "workspace_themes", ["invert_logo_asset_id"])
    op.create_index("ix_workspace_themes_heading_font_id", "workspace_themes", ["heading_font_id"])
    op.create_index("ix_workspace_themes_body_font_id", "workspace_themes", ["body_font_id"])
    op.create_index("ix_workspace_themes_code_font_id", "workspace_themes", ["code_font_id"])

    bind = op.get_bind()
    workspaces = list(
        bind.execute(
            sa.text("SELECT id, component_preview_default_config FROM workspaces WHERE deleted_at IS NULL")
        ).mappings()
    )

    for workspace in workspaces:
        bind.execute(
            sa.text(
                """
                INSERT INTO workspace_themes (
                    workspace_id, key, name, description,
                    logo_asset_id, invert_logo_asset_id, logo_path, invert_logo_path,
                    heading_font_id, body_font_id, code_font_id,
                    heading_font_label, body_font_label, code_font_label,
                    base_font_size, palette,
                    created_by, updated_by, deleted_at
                ) VALUES (
                    :workspace_id, :key, :name, :description,
                    NULL, NULL, :logo_path, :invert_logo_path,
                    NULL, NULL, NULL,
                    :heading_font_label, :body_font_label, :code_font_label,
                    :base_font_size, :palette,
                    NULL, NULL, NULL
                )
                """
            ).bindparams(
                sa.bindparam("palette", type_=postgresql.JSONB()),
            ),
            {
                "workspace_id": workspace["id"],
                "key": DEFAULT_THEME_KEY,
                "name": "白底蓝色",
                "description": "白底蓝色主题，简约经典",
                "logo_path": "img/logo/ppt-e.png",
                "invert_logo_path": "img/logo/ppt-e-white.png",
                "heading_font_label": "思源黑体",
                "body_font_label": "思源黑体",
                "code_font_label": "SourceCodePro",
                "base_font_size": "16px",
                "palette": DEFAULT_THEME_PALETTE,
            },
        )

        preview_config = workspace["component_preview_default_config"] or {}
        release_config = dict((preview_config or {}).get("release") or {})
        release_config["theme_key"] = DEFAULT_THEME_KEY
        preview_config["release"] = release_config

        bind.execute(
            sa.text(
                """
                UPDATE workspaces
                SET default_theme_key = :default_theme_key,
                    component_preview_default_config = :component_preview_default_config
                WHERE id = :workspace_id
                """
            ).bindparams(
                sa.bindparam("component_preview_default_config", type_=sa.JSON()),
            ),
            {
                "workspace_id": workspace["id"],
                "default_theme_key": DEFAULT_THEME_KEY,
                "component_preview_default_config": preview_config,
            },
        )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index("ix_workspace_themes_code_font_id", table_name="workspace_themes")
    op.drop_index("ix_workspace_themes_body_font_id", table_name="workspace_themes")
    op.drop_index("ix_workspace_themes_heading_font_id", table_name="workspace_themes")
    op.drop_index("ix_workspace_themes_invert_logo_asset_id", table_name="workspace_themes")
    op.drop_index("ix_workspace_themes_logo_asset_id", table_name="workspace_themes")
    op.drop_index("ix_workspace_themes_workspace_id", table_name="workspace_themes")
    op.drop_table("workspace_themes")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("theme_key")

    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_column("default_theme_key")
