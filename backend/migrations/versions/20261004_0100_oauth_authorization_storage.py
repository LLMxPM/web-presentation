"""文件功能：新增远程 MCP OAuth 持久化授权、凭证、注册与审计表。

Revision ID: 20261004_0100
Revises: 20261002_0100
"""

import sqlalchemy as sa
from alembic import op
from app.db.types import JSONPayload, UTCDateTime

revision = "20261004_0100"
down_revision = "20261002_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建授权基础表；不预置客户端、用户 Grant 或服务密钥。"""
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("redirect_uris", JSONPayload, nullable=False),
        sa.Column("scopes", JSONPayload, nullable=False),
        sa.Column("resource", sa.String(512), nullable=False),
        sa.Column("auth_method", sa.String(32), nullable=False),
        sa.Column("secret_hash", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at", UTCDateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", UTCDateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "auth_method IN ('none', 'client_secret_basic')",
            name="ck_oauth_client_auth_method",
        ),
    )
    op.create_table(
        "oauth_mcp_services",
        sa.Column("service_id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("secret_hash", sa.Text(), nullable=False),
        sa.Column("resource", sa.String(512), nullable=False),
        sa.Column("api_audience", sa.String(512), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at", UTCDateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", UTCDateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "oauth_grants",
        sa.Column("grant_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            sa.String(128),
            sa.ForeignKey("oauth_clients.client_id"),
            nullable=False,
        ),
        sa.Column("issuer", sa.String(512), nullable=False),
        sa.Column("resource", sa.String(512), nullable=False),
        sa.Column("workspace_ids", JSONPayload, nullable=False),
        sa.Column("scopes", JSONPayload, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("revoked_at", UTCDateTime(), nullable=True),
        sa.Column("revocation_reason", sa.String(64), nullable=True),
        sa.Column(
            "created_at", UTCDateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", UTCDateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_oauth_grants_client_id", "oauth_grants", ["client_id"], unique=False
    )
    op.create_index(
        "ix_oauth_grants_user_id", "oauth_grants", ["user_id"], unique=False
    )
    op.create_table(
        "oauth_refresh_families",
        sa.Column("family_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column(
            "grant_id",
            sa.String(32),
            sa.ForeignKey("oauth_grants.grant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("expires_at", UTCDateTime(), nullable=False),
        sa.Column("revoked_at", UTCDateTime(), nullable=True),
    )
    op.create_index(
        "ix_oauth_refresh_families_expires_at",
        "oauth_refresh_families",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_oauth_refresh_families_grant_id",
        "oauth_refresh_families",
        ["grant_id"],
        unique=False,
    )
    op.create_table(
        "oauth_consent_requests",
        sa.Column("request_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("user_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            sa.String(128),
            sa.ForeignKey("oauth_clients.client_id"),
            nullable=False,
        ),
        sa.Column("redirect_uri", sa.String(2048), nullable=False),
        sa.Column("resource", sa.String(512), nullable=False),
        sa.Column("scopes", JSONPayload, nullable=False),
        sa.Column("state", sa.Text(), nullable=True),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("code_challenge_method", sa.String(8), nullable=False),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("expires_at", UTCDateTime(), nullable=False),
        sa.Column("consumed_at", UTCDateTime(), nullable=True),
    )
    op.create_index(
        "ix_oauth_consent_requests_expires_at",
        "oauth_consent_requests",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_oauth_consent_requests_user_id",
        "oauth_consent_requests",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "oauth_authorization_codes",
        sa.Column("code_hash", sa.String(64), primary_key=True, nullable=False),
        sa.Column(
            "grant_id",
            sa.String(32),
            sa.ForeignKey("oauth_grants.grant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("redirect_uri", sa.String(2048), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("code_challenge_method", sa.String(8), nullable=False),
        sa.Column("scopes", JSONPayload, nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("expires_at", UTCDateTime(), nullable=False),
        sa.Column("consumed_at", UTCDateTime(), nullable=True),
    )
    op.create_index(
        "ix_oauth_authorization_codes_expires_at",
        "oauth_authorization_codes",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_oauth_authorization_codes_grant_id",
        "oauth_authorization_codes",
        ["grant_id"],
        unique=False,
    )
    op.create_table(
        "oauth_tokens",
        sa.Column("token_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "grant_id",
            sa.String(32),
            sa.ForeignKey("oauth_grants.grant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("audience", sa.String(512), nullable=False),
        sa.Column("scopes", JSONPayload, nullable=False),
        sa.Column(
            "family_id",
            sa.String(32),
            sa.ForeignKey("oauth_refresh_families.family_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "parent_token_id",
            sa.String(32),
            sa.ForeignKey("oauth_tokens.token_id"),
            nullable=True,
        ),
        sa.Column(
            "source_token_id",
            sa.String(32),
            sa.ForeignKey("oauth_tokens.token_id"),
            nullable=True,
        ),
        sa.Column(
            "service_id",
            sa.String(128),
            sa.ForeignKey("oauth_mcp_services.service_id"),
            nullable=True,
        ),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("expires_at", UTCDateTime(), nullable=False),
        sa.Column("consumed_at", UTCDateTime(), nullable=True),
        sa.Column("revoked_at", UTCDateTime(), nullable=True),
        sa.CheckConstraint(
            "kind != 'refresh' OR family_id IS NOT NULL", name="ck_oauth_refresh_family"
        ),
        sa.CheckConstraint(
            "kind IN ('access', 'refresh', 'delegated')", name="ck_oauth_token_kind"
        ),
        sa.CheckConstraint(
            "kind != 'delegated' OR (source_token_id IS NOT NULL AND service_id IS NOT NULL)",
            name="ck_oauth_delegated_source",
        ),
    )
    op.create_index(
        "ix_oauth_tokens_expires_at", "oauth_tokens", ["expires_at"], unique=False
    )
    op.create_index(
        "ix_oauth_tokens_family_id", "oauth_tokens", ["family_id"], unique=False
    )
    op.create_index(
        "ix_oauth_tokens_grant_id", "oauth_tokens", ["grant_id"], unique=False
    )
    op.create_table(
        "oauth_audit_events",
        sa.Column("event_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("client_id", sa.String(128), nullable=True),
        sa.Column("grant_id", sa.String(32), nullable=True),
        sa.Column("token_id", sa.String(32), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
    )
    op.create_index(
        "ix_oauth_audit_events_created_at",
        "oauth_audit_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """按依赖逆序删除本批新增表，不操作既有业务表。"""
    op.drop_table("oauth_audit_events")
    op.drop_table("oauth_tokens")
    op.drop_table("oauth_authorization_codes")
    op.drop_table("oauth_consent_requests")
    op.drop_table("oauth_refresh_families")
    op.drop_table("oauth_grants")
    op.drop_table("oauth_mcp_services")
    op.drop_table("oauth_clients")
