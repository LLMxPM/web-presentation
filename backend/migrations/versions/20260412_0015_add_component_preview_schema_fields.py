"""文件功能：为工作空间组件及其版本新增独立 preview_schema 存储字段。"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260412_0015"
down_revision = "20260412_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为组件表与组件版本表新增 preview_schema 文本字段。"""

    op.add_column("workspace_components", sa.Column("preview_schema", sa.Text(), nullable=True))
    op.add_column("workspace_component_versions", sa.Column("preview_schema", sa.Text(), nullable=True))


def downgrade() -> None:
    """回滚组件 preview_schema 独立存储字段。"""

    op.drop_column("workspace_component_versions", "preview_schema")
    op.drop_column("workspace_components", "preview_schema")
