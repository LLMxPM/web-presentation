"""拆分大模型供应商凭证配置。

Revision ID: 20260626_0111
Revises: 20260620_0110
Create Date: 2026-06-26 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.ai.provider_catalog import LLM_PROVIDER_CATALOG
from app.ai.secret_cipher import LlmSecretCipher


# revision identifiers, used by Alembic.
revision: str = "20260626_0111"
down_revision: Union[str, Sequence[str], None] = "20260620_0110"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


provider_configs_table = sa.table(
    "ai_llm_provider_configs",
    sa.column("id", sa.Integer),
    sa.column("user_id", sa.Integer),
    sa.column("scope", sa.String),
    sa.column("name", sa.String),
    sa.column("provider_key", sa.String),
    sa.column("base_url", sa.Text),
    sa.column("api_key_ciphertext", sa.Text),
    sa.column("status", sa.String),
    sa.column("created_by", sa.Integer),
    sa.column("updated_by", sa.Integer),
)


def upgrade() -> None:
    """创建供应商配置表，把历史模型配置中的凭证按明文归并后迁移过去。"""

    op.create_table(
        "ai_llm_provider_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index(op.f("ix_ai_llm_provider_configs_user_id"), "ai_llm_provider_configs", ["user_id"])
    op.create_index(op.f("ix_ai_llm_provider_configs_scope"), "ai_llm_provider_configs", ["scope"])
    op.create_index(op.f("ix_ai_llm_provider_configs_provider_key"), "ai_llm_provider_configs", ["provider_key"])
    op.create_index(op.f("ix_ai_llm_provider_configs_status"), "ai_llm_provider_configs", ["status"])

    with op.batch_alter_table("ai_llm_configs") as batch_op:
        batch_op.add_column(sa.Column("provider_config_id", sa.Integer(), nullable=True))
        batch_op.create_index(op.f("ix_ai_llm_configs_provider_config_id"), ["provider_config_id"])
        batch_op.create_foreign_key(
            "fk_ai_llm_configs_provider_config_id",
            "ai_llm_provider_configs",
            ["provider_config_id"],
            ["id"],
        )

    connection = op.get_bind()
    cipher = LlmSecretCipher()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, user_id, scope, provider_key, base_url, api_key_ciphertext, created_by, updated_by
            FROM ai_llm_configs
            ORDER BY id
            """
        )
    ).mappings()

    provider_ids: dict[tuple[str, int | None, str, str, str], int] = {}
    provider_name_counts: dict[tuple[str, int | None, str], int] = {}

    for row in rows:
        provider_key = str(row["provider_key"] or "").strip().lower()
        base_url = str(row["base_url"] or "").strip()
        api_key_plain = cipher.decrypt(row["api_key_ciphertext"])
        api_key_group = str(api_key_plain or "").strip()
        group_key = (
            str(row["scope"] or "personal"),
            row["user_id"],
            provider_key,
            base_url,
            api_key_group,
        )
        provider_config_id = provider_ids.get(group_key)
        if provider_config_id is None:
            label = _provider_label(provider_key)
            count_key = (group_key[0], group_key[1], provider_key)
            provider_name_counts[count_key] = provider_name_counts.get(count_key, 0) + 1
            suffix = "" if provider_name_counts[count_key] == 1 else f" {provider_name_counts[count_key]}"
            provider_config_id = int(
                connection.execute(
                    provider_configs_table.insert()
                    .values(
                        user_id=row["user_id"],
                        scope=group_key[0],
                        name=f"{label} 凭证{suffix}",
                        provider_key=provider_key,
                        base_url=base_url or None,
                        api_key_ciphertext=cipher.encrypt(api_key_plain),
                        status="active",
                        created_by=row["created_by"],
                        updated_by=row["updated_by"],
                    )
                    .returning(provider_configs_table.c.id)
                ).scalar_one()
            )
            provider_ids[group_key] = provider_config_id

        connection.execute(
            sa.text(
                """
                UPDATE ai_llm_configs
                SET provider_config_id = :provider_config_id
                WHERE id = :config_id
                """
            ),
            {"provider_config_id": provider_config_id, "config_id": row["id"]},
        )

    with op.batch_alter_table("ai_llm_configs") as batch_op:
        batch_op.alter_column("provider_config_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_index(op.f("ix_ai_llm_configs_provider_key"))
        batch_op.drop_column("provider_key")
        batch_op.drop_column("base_url")
        batch_op.drop_column("api_key_ciphertext")


def downgrade() -> None:
    """回退到模型配置自带供应商凭证字段。"""

    with op.batch_alter_table("ai_llm_configs") as batch_op:
        batch_op.add_column(sa.Column("provider_key", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("base_url", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("api_key_ciphertext", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE ai_llm_configs
        SET provider_key = (
              SELECT provider_key
              FROM ai_llm_provider_configs
              WHERE ai_llm_provider_configs.id = ai_llm_configs.provider_config_id
            ),
            base_url = (
              SELECT base_url
              FROM ai_llm_provider_configs
              WHERE ai_llm_provider_configs.id = ai_llm_configs.provider_config_id
            ),
            api_key_ciphertext = (
              SELECT api_key_ciphertext
              FROM ai_llm_provider_configs
              WHERE ai_llm_provider_configs.id = ai_llm_configs.provider_config_id
            )
        """
    )

    with op.batch_alter_table("ai_llm_configs") as batch_op:
        batch_op.alter_column("provider_key", existing_type=sa.String(length=64), nullable=False)
        batch_op.create_index(op.f("ix_ai_llm_configs_provider_key"), ["provider_key"])
        batch_op.drop_constraint("fk_ai_llm_configs_provider_config_id", type_="foreignkey")
        batch_op.drop_index(op.f("ix_ai_llm_configs_provider_config_id"))
        batch_op.drop_column("provider_config_id")

    op.drop_index(op.f("ix_ai_llm_provider_configs_status"), table_name="ai_llm_provider_configs")
    op.drop_index(op.f("ix_ai_llm_provider_configs_provider_key"), table_name="ai_llm_provider_configs")
    op.drop_index(op.f("ix_ai_llm_provider_configs_scope"), table_name="ai_llm_provider_configs")
    op.drop_index(op.f("ix_ai_llm_provider_configs_user_id"), table_name="ai_llm_provider_configs")
    op.drop_table("ai_llm_provider_configs")


def _provider_label(provider_key: str) -> str:
    """按供应商目录返回展示名，历史异常 key 回退到原始 key。"""

    entry = LLM_PROVIDER_CATALOG.get(provider_key)
    return entry.label if entry is not None else provider_key
