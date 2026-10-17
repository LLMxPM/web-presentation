"""文件功能：为项目和路由新增自动放映配置列，旧项目回填默认完整配置、旧路由保持空覆盖。

Revision ID: 20261017_0100
Revises: 20261016_0100
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

from app.core.slideshow_defaults import default_slideshow_payload

revision = "20261017_0100"
down_revision = "20261016_0100"
branch_labels = None
depends_on = None


def _default_payload_sql() -> str:
    """生成可移植的 JSON 服务端默认值字面量；默认值由契约模块单点维护。

    不能使用 text() 包装：JSON 中的冒号会被 SQLAlchemy 误识别为绑定参数。
    """

    return json.dumps(default_slideshow_payload(), ensure_ascii=False, separators=(",", ":"))


def upgrade() -> None:
    """新增放映配置列：项目非空并回填默认值，路由保留可空覆盖。"""

    op.add_column(
        "projects",
        sa.Column(
            "slideshow_config_json",
            sa.JSON(),
            nullable=False,
            server_default=_default_payload_sql(),
        ),
    )
    op.add_column("project_routes", sa.Column("transition_json", sa.JSON(), nullable=True))
    op.add_column("project_routes", sa.Column("advance_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    """移除放映配置列，恢复旧模型结构。"""

    op.drop_column("project_routes", "advance_json")
    op.drop_column("project_routes", "transition_json")
    op.drop_column("projects", "slideshow_config_json")
