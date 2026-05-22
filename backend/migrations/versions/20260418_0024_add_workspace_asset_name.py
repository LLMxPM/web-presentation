"""add workspace asset logical name

Revision ID: 20260418_0024
Revises: 20260417_0023
Create Date: 2026-04-18 12:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op


revision: str = "20260418_0024"
down_revision: str | None = "20260417_0023"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _build_default_asset_name(original_name: str) -> str:
    """按上传文件名去掉全部后缀，生成资源逻辑名。"""

    normalized_name = Path(str(original_name or "").strip()).name.strip()
    if not normalized_name:
        return "asset"

    base_name = normalized_name
    while True:
        next_path = Path(base_name)
        if not next_path.suffix:
            break
        base_name = next_path.stem
    return base_name or Path(normalized_name).stem or normalized_name


def upgrade() -> None:
    """为工作空间资源新增逻辑 name，并回填默认值。"""

    with op.batch_alter_table("workspace_assets") as batch_op:
        batch_op.add_column(sa.Column("name", sa.String(length=255), nullable=True))

    bind = op.get_bind()
    asset_rows = bind.execute(sa.text("SELECT id, original_name FROM workspace_assets")).mappings().all()
    for row in asset_rows:
        bind.execute(
            sa.text("UPDATE workspace_assets SET name = :name WHERE id = :asset_id"),
            {
                "asset_id": row["id"],
                "name": _build_default_asset_name(str(row["original_name"] or "")),
            },
        )

    with op.batch_alter_table("workspace_assets") as batch_op:
        batch_op.alter_column("name", existing_type=sa.String(length=255), nullable=False)
        batch_op.create_unique_constraint(
            "uq_workspace_assets_workspace_name",
            ["workspace_id", "name"],
        )


def downgrade() -> None:
    """回滚工作空间资源逻辑名字段。"""

    with op.batch_alter_table("workspace_assets") as batch_op:
        batch_op.drop_constraint("uq_workspace_assets_workspace_name", type_="unique")
        batch_op.drop_column("name")
