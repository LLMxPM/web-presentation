"""文件功能：切换项目放映列的新建默认值到 Scene schema 4，不转换旧项目或页面内容。

Revision ID: 20261030_0100
Revises: 20261029_0100
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "20261030_0100"
down_revision = "20261029_0100"
branch_labels = None
depends_on = None

# 历史迁移固定当时的字段，不能在未来升级时重新读取另一版本的应用默认。
_V4 = {"transition": {"effect": "fade", "duration_ms": 400}, "advance": {"mode": "manual", "delay_ms": 5000, "completion_delay_ms": 300}, "loop": False}
_V3 = {"transition": {"effect": "fade", "duration_ms": 400}, "advance": {"mode": "manual", "delay_ms": 5000, "media_timeout_ms": 300000}, "loop": False, "auto_start": False}


def _set_default(payload: dict) -> None:
    """使用 Alembic batch 适配 SQLite 与 PostgreSQL，不拼接方言专用 SQL。"""
    with op.batch_alter_table("projects") as batch:
        batch.alter_column("slideshow_config_json", existing_type=sa.JSON(), existing_nullable=False,
                           server_default=json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def upgrade() -> None:
    """仅修改新建默认；旧配置读入返回不兼容错误，用户需明确重新保存。"""
    _set_default(_V4)


def downgrade() -> None:
    """恢复旧列默认，已经写入的新字段不回译成旧接口。"""
    _set_default(_V3)
