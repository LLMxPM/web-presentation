"""文件功能：为页面版本新增展示版号字段，并按时间版号/快照版号回填。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260331_0005"
down_revision: str | None = "20260331_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """新增版本展示版号字段，并为存量数据生成默认版号。"""

    with op.batch_alter_table("page_versions") as batch_op:
        batch_op.add_column(sa.Column("version_label", sa.String(length=64), nullable=True))

    connection = op.get_bind()
    metadata = sa.MetaData()
    page_versions = sa.Table(
        "page_versions",
        metadata,
        sa.Column("id", sa.Integer()),
        sa.Column("page_id", sa.Integer()),
        sa.Column("version_no", sa.Integer()),
        sa.Column("is_important", sa.Boolean()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("version_label", sa.String(length=64)),
    )

    rows = connection.execute(
        sa.select(
            page_versions.c.id,
            page_versions.c.page_id,
            page_versions.c.version_no,
            page_versions.c.is_important,
            page_versions.c.created_at,
        ).order_by(page_versions.c.page_id.asc(), page_versions.c.version_no.asc())
    ).mappings().all()

    page_snapshot_counter: dict[int, int] = {}
    for row in rows:
        if row["is_important"]:
            page_snapshot_counter[row["page_id"]] = page_snapshot_counter.get(row["page_id"], 0) + 1
            version_label = f"V{page_snapshot_counter[row['page_id']]}"
        else:
            created_at = row["created_at"]
            version_label = created_at.strftime("%Y%m%d-%H%M%S") if created_at is not None else f"legacy-{row['version_no']}"

        connection.execute(
            page_versions.update()
            .where(page_versions.c.id == row["id"])
            .values(version_label=version_label)
        )

    with op.batch_alter_table("page_versions") as batch_op:
        batch_op.alter_column("version_label", existing_type=sa.String(length=64), nullable=False)


def downgrade() -> None:
    """移除页面版本的展示版号字段。"""

    with op.batch_alter_table("page_versions") as batch_op:
        batch_op.drop_column("version_label")
