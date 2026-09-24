"""文件功能：迁移双方言差异 helper，禁止迁移文件裸判 dialect.name。"""

from __future__ import annotations

from alembic import op
from sqlalchemy import JSON, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeEngine


def is_sqlite() -> bool:
    """当前迁移连接是否 SQLite。"""

    return op.get_bind().dialect.name == "sqlite"


def json_payload_type() -> TypeEngine:
    """双方言 JSON 列类型：PostgreSQL 用 JSONB，SQLite 用 JSON。

    迁移不 import app.db.types，避免历史迁移随应用模型漂移；
    语义与 `app.db.types.JSONPayload` 一致，`with_variant(JSONB` 只允许出现在这两处。
    """

    return JSON().with_variant(JSONB(), "postgresql")


def clear_page_screenshot_pointers() -> None:
    """不可逆离线转换：清除当前有效截图指针（历史对象保留）。

    调用方必须在迁移 docstring 写明「不恢复」并要求先备份。
    """

    op.execute(
        text(
            """
            UPDATE pages
            SET screenshot_storage_key = NULL, screenshot_version_no = NULL,
                screenshot_config_hash = NULL, screenshot_viewport_width = NULL,
                screenshot_viewport_height = NULL, screenshot_updated_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE screenshot_storage_key IS NOT NULL
            """
        )
    )
