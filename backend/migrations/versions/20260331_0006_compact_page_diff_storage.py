"""文件功能：将页面历史 diff 从 ndiff 数组迁移为紧凑反向 patch 存储。"""

from __future__ import annotations

import json
from collections.abc import Sequence
from difflib import SequenceMatcher, restore

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260331_0006"
down_revision: str | None = "20260331_0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """将历史 diff 内容重写为更紧凑的反向 patch 结构。"""

    connection = op.get_bind()
    metadata = sa.MetaData()
    page_versions = sa.Table(
        "page_versions",
        metadata,
        sa.Column("id", sa.Integer()),
        sa.Column("page_id", sa.Integer()),
        sa.Column("version_no", sa.Integer()),
        sa.Column("storage_type", sa.String(length=32)),
        sa.Column("content", sa.Text()),
    )

    page_ids = [
        row[0]
        for row in connection.execute(
            sa.select(page_versions.c.page_id).distinct().order_by(page_versions.c.page_id.asc())
        ).all()
    ]

    for page_id in page_ids:
        rows = connection.execute(
            sa.select(
                page_versions.c.id,
                page_versions.c.version_no,
                page_versions.c.storage_type,
                page_versions.c.content,
            )
            .where(page_versions.c.page_id == page_id)
            .order_by(page_versions.c.version_no.desc())
        ).mappings().all()
        if not rows:
            continue

        materialized: dict[int, str] = {}
        newer_content = ""
        for row in rows:
            if row["storage_type"] == "snapshot":
                current_content = row["content"]
            else:
                current_content = _apply_backward_diff_legacy(newer_content, row["content"])
            materialized[row["version_no"]] = current_content
            newer_content = current_content

        for row in rows:
            if row["storage_type"] != "diff":
                continue
            compact_patch = _build_backward_patch(
                newer_content=materialized[row["version_no"] + 1],
                older_content=materialized[row["version_no"]],
            )
            connection.execute(
                page_versions.update()
                .where(page_versions.c.id == row["id"])
                .values(content=compact_patch)
            )


def downgrade() -> None:
    """不回滚历史 diff 内容格式。"""


def _apply_backward_diff_legacy(newer_content: str, diff_content: str) -> str:
    """兼容旧 ndiff 数组和新反向 patch 两种 diff 内容。"""

    payload = json.loads(diff_content)
    if isinstance(payload, list):
        return "".join(restore(payload, 2))

    if isinstance(payload, dict) and payload.get("format") == "reverse_patch_v1":
        newer_lines = newer_content.splitlines(keepends=True)
        cursor = 0
        restored_lines: list[str] = []
        for operation in payload.get("ops", []):
            tag = operation[0]
            if tag == "=":
                keep_count = int(operation[1])
                restored_lines.extend(newer_lines[cursor: cursor + keep_count])
                cursor += keep_count
            elif tag == "-":
                cursor += int(operation[1])
            elif tag == "+":
                restored_lines.extend(operation[1])
            elif tag == "~":
                cursor += int(operation[1])
                restored_lines.extend(operation[2])
        return "".join(restored_lines)

    raise RuntimeError("Unsupported legacy diff payload.")


def _build_backward_patch(newer_content: str, older_content: str) -> str:
    """生成紧凑反向 patch，用于降低历史 diff 存储体积。"""

    newer_lines = newer_content.splitlines(keepends=True)
    older_lines = older_content.splitlines(keepends=True)
    matcher = SequenceMatcher(a=newer_lines, b=older_lines, autojunk=False)
    operations: list[list[object]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            operations.append(["=", i2 - i1])
        elif tag == "delete":
            operations.append(["-", i2 - i1])
        elif tag == "insert":
            operations.append(["+", older_lines[j1:j2]])
        elif tag == "replace":
            operations.append(["~", i2 - i1, older_lines[j1:j2]])

    return json.dumps(
        {"format": "reverse_patch_v1", "ops": operations},
        ensure_ascii=False,
        separators=(",", ":"),
    )
