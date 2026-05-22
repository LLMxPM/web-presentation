"""文件功能：固定工作空间组件分类，并将历史自由分类回填为默认分类。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260426_0032"
down_revision = "20260426_0031"
branch_labels = None
depends_on = None

DEFAULT_COMPONENT_TYPE = "内容区块"
FIXED_COMPONENT_TYPES = ("整页模板", "布局容器", "内容区块", "数据展示", "资源渲染", "样式能力", "路由能力")


def upgrade() -> None:
    """将组件分类默认值改为固定分类，并清理历史自由文本分类。"""

    fixed_types = "', '".join(FIXED_COMPONENT_TYPES)
    op.execute(
        f"""
        UPDATE workspace_components
        SET component_type = '{DEFAULT_COMPONENT_TYPE}'
        WHERE component_type IS NULL
           OR component_type = ''
           OR component_type NOT IN ('{fixed_types}')
        """
    )
    with op.batch_alter_table("workspace_components") as batch_op:
        batch_op.alter_column(
            "component_type",
            existing_type=sa.String(length=64),
            existing_nullable=False,
            server_default=DEFAULT_COMPONENT_TYPE,
        )


def downgrade() -> None:
    """恢复旧版自由分类默认值。"""

    with op.batch_alter_table("workspace_components") as batch_op:
        batch_op.alter_column(
            "component_type",
            existing_type=sa.String(length=64),
            existing_nullable=False,
            server_default="general",
        )
