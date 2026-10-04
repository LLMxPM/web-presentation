"""文件功能：增加 OAuth 服务审计标识和凭证依赖索引，支持有界清理及停用撤销。

Revision ID: 20261004_0101
Revises: 20261004_0100
"""

import sqlalchemy as sa
from alembic import op

revision = "20261004_0101"
down_revision = "20261004_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """只添加可空审计字段及索引，不更改既有凭证、授权或业务数据。"""
    op.add_column(
        "oauth_audit_events", sa.Column("service_id", sa.String(128), nullable=True)
    )
    for column in ("parent_token_id", "source_token_id", "service_id"):
        op.create_index(f"ix_oauth_tokens_{column}", "oauth_tokens", [column])


def downgrade() -> None:
    """回退仅删除本批索引和公共审计标识，保留授权表与凭证。"""
    for column in ("service_id", "source_token_id", "parent_token_id"):
        op.drop_index(f"ix_oauth_tokens_{column}", table_name="oauth_tokens")
    op.drop_column("oauth_audit_events", "service_id")
