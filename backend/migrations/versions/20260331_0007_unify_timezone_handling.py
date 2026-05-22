"""add configurable app timezone and normalize workspace/page version timestamps

Revision ID: 20260331_0007
Revises: 20260331_0006
Create Date: 2026-03-31 18:20:00.000000

"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Sequence, Union
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260331_0007"
down_revision: Union[str, Sequence[str], None] = "20260331_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TIMESTAMP_LABEL_PATTERN = re.compile(r"^\d{8}-\d{6}$")
_DEFAULT_APP_TIMEZONE = "Asia/Shanghai"


def _normalize_utc(value: datetime) -> datetime:
    """将迁移阶段读出的时间统一规整为 UTC aware，兼容历史 naive 数据。"""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _get_business_timezone() -> ZoneInfo:
    """读取迁移执行时的业务时区配置，默认回退到上海时区。"""

    return ZoneInfo(os.getenv("APP_TIMEZONE", _DEFAULT_APP_TIMEZONE))


def _rebuild_page_version_labels(target_timezone: ZoneInfo) -> None:
    """按业务时区重算普通保存版本标签，保持历史数据与新逻辑一致。"""

    bind = op.get_bind()
    page_versions = sa.table(
        "page_versions",
        sa.column("id", sa.Integer()),
        sa.column("is_important", sa.Boolean()),
        sa.column("version_label", sa.String(length=64)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    rows = bind.execute(
        sa.select(
            page_versions.c.id,
            page_versions.c.is_important,
            page_versions.c.version_label,
            page_versions.c.created_at,
        )
    ).mappings().all()

    for row in rows:
        if row["is_important"]:
            continue
        if not row["created_at"] or not _TIMESTAMP_LABEL_PATTERN.fullmatch(row["version_label"] or ""):
            continue

        normalized_created_at = _normalize_utc(row["created_at"])
        version_label = normalized_created_at.astimezone(target_timezone).strftime("%Y%m%d-%H%M%S")
        bind.execute(
            sa.update(page_versions)
            .where(page_versions.c.id == row["id"])
            .values(version_label=version_label)
        )


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "workspaces",
            "last_opened_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=True,
            postgresql_using="last_opened_at AT TIME ZONE 'UTC'",
        )
    else:
        with op.batch_alter_table("workspaces") as batch_op:
            batch_op.alter_column(
                "last_opened_at",
                existing_type=sa.DateTime(),
                type_=sa.DateTime(timezone=True),
                existing_nullable=True,
            )

    _rebuild_page_version_labels(_get_business_timezone())


def downgrade() -> None:
    """Downgrade schema."""

    bind = op.get_bind()
    _rebuild_page_version_labels(ZoneInfo("UTC"))

    if bind.dialect.name == "postgresql":
        op.alter_column(
            "workspaces",
            "last_opened_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=True,
            postgresql_using="last_opened_at AT TIME ZONE 'UTC'",
        )
    else:
        with op.batch_alter_table("workspaces") as batch_op:
            batch_op.alter_column(
                "last_opened_at",
                existing_type=sa.DateTime(timezone=True),
                type_=sa.DateTime(),
                existing_nullable=True,
            )
