"""文件功能：为 Models.dev 模型目录和聊天模型配置增加模型级调用协议。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260819_0100"
down_revision: Union[str, Sequence[str], None] = "20260818_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加协议列，并为已有数据提供供应商级协议的兼容回退。"""

    op.add_column(
        "ai_chat_model_catalog",
        sa.Column("protocol_key", sa.String(64), nullable=False, server_default="openai_compatible_chat"),
    )
    op.create_index("ix_ai_chat_model_catalog_protocol_key", "ai_chat_model_catalog", ["protocol_key"])
    op.execute(
        sa.text(
            "UPDATE ai_chat_model_catalog "
            "SET protocol_key = (SELECT protocol_key FROM ai_chat_provider_catalog "
            "WHERE ai_chat_provider_catalog.provider_key = ai_chat_model_catalog.provider_key)"
        )
    )

    op.add_column(
        "ai_chat_model_configs",
        sa.Column("protocol_key", sa.String(64), nullable=False, server_default="openai_compatible_chat"),
    )
    op.create_index("ix_ai_chat_model_configs_protocol_key", "ai_chat_model_configs", ["protocol_key"])
    op.execute(
        sa.text(
            "UPDATE ai_chat_model_configs "
            "SET protocol_key = (SELECT protocol_key FROM ai_chat_provider_configs "
            "WHERE ai_chat_provider_configs.id = ai_chat_model_configs.provider_config_id)"
        )
    )


def downgrade() -> None:
    """移除模型级协议列；历史配置回退到供应商级协议。"""

    op.drop_index("ix_ai_chat_model_configs_protocol_key", table_name="ai_chat_model_configs")
    op.drop_column("ai_chat_model_configs", "protocol_key")
    op.drop_index("ix_ai_chat_model_catalog_protocol_key", table_name="ai_chat_model_catalog")
    op.drop_column("ai_chat_model_catalog", "protocol_key")
