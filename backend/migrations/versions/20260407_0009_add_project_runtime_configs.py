"""add project runtime yaml configs

Revision ID: 20260407_0009
Revises: 20260402_0008
Create Date: 2026-04-07 22:30:00.000000

"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260407_0009"
down_revision: Union[str, Sequence[str], None] = "20260402_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("app_config_yaml", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("icon_config_yaml", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("route_config_yaml", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("theme_config_yaml", sa.Text(), nullable=True))

    templates = load_default_templates()
    op.execute(
        sa.text(
            """
            UPDATE projects
            SET app_config_yaml = :app_config_yaml,
                icon_config_yaml = :icon_config_yaml,
                route_config_yaml = :route_config_yaml,
                theme_config_yaml = :theme_config_yaml
            WHERE app_config_yaml IS NULL
               OR icon_config_yaml IS NULL
               OR route_config_yaml IS NULL
               OR theme_config_yaml IS NULL
            """
        ).bindparams(
            sa.bindparam("app_config_yaml", value=templates["app"]),
            sa.bindparam("icon_config_yaml", value=templates["icons"]),
            sa.bindparam("route_config_yaml", value=templates["routes"]),
            sa.bindparam("theme_config_yaml", value=templates["themes"]),
        )
    )

    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column("app_config_yaml", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("icon_config_yaml", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("route_config_yaml", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("theme_config_yaml", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    """Downgrade schema."""

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("theme_config_yaml")
        batch_op.drop_column("route_config_yaml")
        batch_op.drop_column("icon_config_yaml")
        batch_op.drop_column("app_config_yaml")


def load_default_templates() -> dict[str, str]:
    """读取 runtime 的默认 YAML 配置模板，用于回填存量项目。"""

    config_root = Path(__file__).resolve().parents[3] / "runtime" / "public" / "config"
    return {
        "app": (config_root / "app.config.yaml").read_text(encoding="utf-8"),
        "icons": (config_root / "icons.config.yaml").read_text(encoding="utf-8"),
        "routes": (config_root / "routes.config.yaml").read_text(encoding="utf-8"),
        "themes": (config_root / "themes.config.yaml").read_text(encoding="utf-8"),
    }
