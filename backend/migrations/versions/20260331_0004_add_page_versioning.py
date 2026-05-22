"""文件功能：为页面资源新增版本链与重点快照能力。"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260331_0004"
down_revision: str | None = "20260330_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """新增页面版本链表，并为存量页面补齐初始版本快照。"""

    with op.batch_alter_table("pages") as batch_op:
        batch_op.add_column(sa.Column("current_version_no", sa.Integer(), nullable=False, server_default="1"))

    op.create_table(
        "page_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("storage_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_important", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("snapshot_name", sa.String(length=128), nullable=True),
        sa.Column("change_note", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("page_id", "version_no", name="uq_page_versions_page_id_version_no"),
    )
    op.create_index("ix_page_versions_page_id", "page_versions", ["page_id"], unique=False)

    connection = op.get_bind()
    metadata = sa.MetaData()
    pages = sa.Table(
        "pages",
        metadata,
        sa.Column("id", sa.Integer()),
        sa.Column("page_code", sa.Text()),
        sa.Column("file_type", sa.String(length=32)),
        sa.Column("created_by", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    page_versions = sa.Table(
        "page_versions",
        metadata,
        sa.Column("page_id", sa.Integer()),
        sa.Column("version_no", sa.Integer()),
        sa.Column("file_type", sa.String(length=32)),
        sa.Column("storage_type", sa.String(length=32)),
        sa.Column("content", sa.Text()),
        sa.Column("is_important", sa.Boolean()),
        sa.Column("snapshot_name", sa.String(length=128)),
        sa.Column("change_note", sa.String(length=255)),
        sa.Column("created_by", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    rows = connection.execute(sa.select(pages.c.id, pages.c.page_code, pages.c.file_type, pages.c.created_by, pages.c.created_at)).mappings().all()
    if rows:
        now = datetime.now(UTC)
        op.bulk_insert(
            page_versions,
            [
                {
                    "page_id": row["id"],
                    "version_no": 1,
                    "file_type": row["file_type"],
                    "storage_type": "snapshot",
                    "content": row["page_code"],
                    "is_important": False,
                    "snapshot_name": None,
                    "change_note": "存量初始化版本",
                    "created_by": row["created_by"],
                    "created_at": row["created_at"] or now,
                    "updated_at": row["created_at"] or now,
                }
                for row in rows
            ],
        )


def downgrade() -> None:
    """回滚页面版本链能力。"""

    op.drop_index("ix_page_versions_page_id", table_name="page_versions")
    op.drop_table("page_versions")

    with op.batch_alter_table("pages") as batch_op:
        batch_op.drop_column("current_version_no")
