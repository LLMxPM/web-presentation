"""文件功能：字体按 family 实体管理——新建字体族表、回填 face 归属与主题绑定并删除旧列。

Revision ID: 20260730_0100
Revises: 20260728_0100
Create Date: 2026-07-30 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260730_0100"
down_revision: Union[str, Sequence[str], None] = "20260728_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新建 workspace_font_families，回填 face.family_id 与主题 family 绑定，删除旧的 font_family 列与主题 face 外键。"""

    op.create_table(
        "workspace_font_families",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_workspace_font_families_workspace_name"),
    )
    op.create_index(op.f("ix_workspace_font_families_workspace_id"), "workspace_font_families", ["workspace_id"], unique=False)

    # 按 (workspace_id, lower(trim(font_family))) 去重建 family，名称取首条（最小 id）原值。
    op.execute(
        """
        INSERT INTO workspace_font_families (workspace_id, name, created_at, updated_at)
        SELECT c.workspace_id, c.font_family, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM workspace_font_configs c
        JOIN (
            SELECT workspace_id, lower(trim(font_family)) AS normalized_name, MIN(id) AS first_id
            FROM workspace_font_configs
            GROUP BY workspace_id, lower(trim(font_family))
        ) g ON g.first_id = c.id
        """
    )

    # face 回填 family_id：先加可空列，回填完成后再收紧为 NOT NULL。
    op.add_column("workspace_font_configs", sa.Column("family_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE workspace_font_configs
        SET family_id = (
            SELECT f.id
            FROM workspace_font_families f
            WHERE f.workspace_id = workspace_font_configs.workspace_id
              AND lower(trim(f.name)) = lower(trim(workspace_font_configs.font_family))
        )
        """
    )
    with op.batch_alter_table("workspace_font_configs") as batch_op:
        batch_op.alter_column("family_id", nullable=False, existing_type=sa.Integer())
        batch_op.create_foreign_key(
            "fk_workspace_font_configs_family_id",
            "workspace_font_families",
            ["family_id"],
            ["id"],
        )
        batch_op.create_unique_constraint(
            "uq_workspace_font_configs_family_face",
            ["family_id", "font_weight", "font_style"],
        )
        batch_op.drop_column("font_family")
    op.create_index(op.f("ix_workspace_font_configs_family_id"), "workspace_font_configs", ["family_id"], unique=False)

    # 主题槽位改绑 family：新列回填自原 face 外键映射，再删除旧列。
    op.add_column("workspace_themes", sa.Column("heading_font_family_id", sa.Integer(), nullable=True))
    op.add_column("workspace_themes", sa.Column("body_font_family_id", sa.Integer(), nullable=True))
    op.add_column("workspace_themes", sa.Column("code_font_family_id", sa.Integer(), nullable=True))
    for new_column, old_column in (
        ("heading_font_family_id", "heading_font_id"),
        ("body_font_family_id", "body_font_id"),
        ("code_font_family_id", "code_font_id"),
    ):
        op.execute(
            f"""
            UPDATE workspace_themes
            SET {new_column} = (
                SELECT c.family_id
                FROM workspace_font_configs c
                WHERE c.id = workspace_themes.{old_column}
            )
            """
        )
    op.drop_index(op.f("ix_workspace_themes_heading_font_id"), table_name="workspace_themes")
    op.drop_index(op.f("ix_workspace_themes_body_font_id"), table_name="workspace_themes")
    op.drop_index(op.f("ix_workspace_themes_code_font_id"), table_name="workspace_themes")
    with op.batch_alter_table("workspace_themes") as batch_op:
        batch_op.create_foreign_key(
            "fk_workspace_themes_heading_font_family_id",
            "workspace_font_families",
            ["heading_font_family_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_workspace_themes_body_font_family_id",
            "workspace_font_families",
            ["body_font_family_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_workspace_themes_code_font_family_id",
            "workspace_font_families",
            ["code_font_family_id"],
            ["id"],
        )
        batch_op.drop_column("heading_font_id")
        batch_op.drop_column("body_font_id")
        batch_op.drop_column("code_font_id")
    op.create_index(op.f("ix_workspace_themes_heading_font_family_id"), "workspace_themes", ["heading_font_family_id"], unique=False)
    op.create_index(op.f("ix_workspace_themes_body_font_family_id"), "workspace_themes", ["body_font_family_id"], unique=False)
    op.create_index(op.f("ix_workspace_themes_code_font_family_id"), "workspace_themes", ["code_font_family_id"], unique=False)


def downgrade() -> None:
    """恢复 face 扁平 font_family 列与主题的 face 外键绑定，并删除字体族表。"""

    # 主题恢复旧列：family 映射回该 family 下最早注册的 face。
    op.add_column("workspace_themes", sa.Column("heading_font_id", sa.Integer(), nullable=True))
    op.add_column("workspace_themes", sa.Column("body_font_id", sa.Integer(), nullable=True))
    op.add_column("workspace_themes", sa.Column("code_font_id", sa.Integer(), nullable=True))
    for old_column, new_column in (
        ("heading_font_id", "heading_font_family_id"),
        ("body_font_id", "body_font_family_id"),
        ("code_font_id", "code_font_family_id"),
    ):
        op.execute(
            f"""
            UPDATE workspace_themes
            SET {old_column} = (
                SELECT MIN(c.id)
                FROM workspace_font_configs c
                WHERE c.family_id = workspace_themes.{new_column}
            )
            """
        )
    op.drop_index(op.f("ix_workspace_themes_heading_font_family_id"), table_name="workspace_themes")
    op.drop_index(op.f("ix_workspace_themes_body_font_family_id"), table_name="workspace_themes")
    op.drop_index(op.f("ix_workspace_themes_code_font_family_id"), table_name="workspace_themes")
    with op.batch_alter_table("workspace_themes") as batch_op:
        batch_op.drop_constraint("fk_workspace_themes_heading_font_family_id", type_="foreignkey")
        batch_op.drop_constraint("fk_workspace_themes_body_font_family_id", type_="foreignkey")
        batch_op.drop_constraint("fk_workspace_themes_code_font_family_id", type_="foreignkey")
        batch_op.create_foreign_key(None, "workspace_font_configs", ["heading_font_id"], ["id"])
        batch_op.create_foreign_key(None, "workspace_font_configs", ["body_font_id"], ["id"])
        batch_op.create_foreign_key(None, "workspace_font_configs", ["code_font_id"], ["id"])
        batch_op.drop_column("heading_font_family_id")
        batch_op.drop_column("body_font_family_id")
        batch_op.drop_column("code_font_family_id")
    op.create_index(op.f("ix_workspace_themes_heading_font_id"), "workspace_themes", ["heading_font_id"], unique=False)
    op.create_index(op.f("ix_workspace_themes_body_font_id"), "workspace_themes", ["body_font_id"], unique=False)
    op.create_index(op.f("ix_workspace_themes_code_font_id"), "workspace_themes", ["code_font_id"], unique=False)

    # face 恢复扁平 font_family 字符串。
    op.add_column("workspace_font_configs", sa.Column("font_family", sa.String(length=255), nullable=True))
    op.execute(
        """
        UPDATE workspace_font_configs
        SET font_family = (
            SELECT f.name
            FROM workspace_font_families f
            WHERE f.id = workspace_font_configs.family_id
        )
        """
    )
    op.drop_index(op.f("ix_workspace_font_configs_family_id"), table_name="workspace_font_configs")
    with op.batch_alter_table("workspace_font_configs") as batch_op:
        batch_op.alter_column("font_family", nullable=False, existing_type=sa.String(length=255))
        batch_op.drop_constraint("uq_workspace_font_configs_family_face", type_="unique")
        batch_op.drop_constraint("fk_workspace_font_configs_family_id", type_="foreignkey")
        batch_op.drop_column("family_id")

    op.drop_index(op.f("ix_workspace_font_families_workspace_id"), table_name="workspace_font_families")
    op.drop_table("workspace_font_families")
