"""文件功能：为项目新增音频音量列与 cue 绑定表，历史项目回填默认音量且无绑定。

Revision ID: 20261018_0100
Revises: 20261017_0100
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

from app.core.audio_defaults import default_audio_volume_payload

revision = "20261018_0100"
down_revision = "20261017_0100"
branch_labels = None
depends_on = None


def _default_payload_sql() -> str:
    """生成可移植的 JSON 服务端默认值字面量；默认值由契约模块单点维护。"""

    return json.dumps(default_audio_volume_payload(), ensure_ascii=False, separators=(",", ":"))


def upgrade() -> None:
    """新增项目音频音量与 cue 绑定；历史项目保持静音且无 cue。"""

    op.add_column(
        "projects",
        sa.Column(
            "audio_settings_json",
            sa.JSON(),
            nullable=False,
            server_default=_default_payload_sql(),
        ),
    )
    op.create_table(
        "project_audio_cue_bindings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("cue_key", sa.String(length=80), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("gain_percent", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["asset_id"], ["workspace_assets.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "cue_key", name="uq_project_audio_cue_bindings_project_key"),
    )
    op.create_index(
        op.f("ix_project_audio_cue_bindings_project_id"),
        "project_audio_cue_bindings",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_audio_cue_bindings_asset_id"),
        "project_audio_cue_bindings",
        ["asset_id"],
        unique=False,
    )


def downgrade() -> None:
    """移除 cue 绑定表与项目音频列。"""

    op.drop_index(op.f("ix_project_audio_cue_bindings_asset_id"), table_name="project_audio_cue_bindings")
    op.drop_index(op.f("ix_project_audio_cue_bindings_project_id"), table_name="project_audio_cue_bindings")
    op.drop_table("project_audio_cue_bindings")
    op.drop_column("projects", "audio_settings_json")
