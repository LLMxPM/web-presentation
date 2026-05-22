"""文件功能：为项目表新增系统管理标记，供组件预览沙箱项目隔离使用。"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260412_0014"
down_revision = "20260412_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为 projects 表新增 is_system_managed 字段，并回填默认值。"""

    op.add_column(
        "projects",
        sa.Column("is_system_managed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """回滚 projects 表上的系统管理标记字段。"""

    op.drop_column("projects", "is_system_managed")
