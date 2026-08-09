"""文件功能：合并 2026-07-30 基线后的结构调整与数据修复。

Revision ID: 20260809_0100
Revises: 20260730_0100
Create Date: 2026-08-09 11:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260809_0100"
down_revision: Union[str, Sequence[str], None] = "20260730_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """按原始 revision 顺序执行合并后的升级。"""

    _20260805_0100_upgrade()
    _20260805_0200_upgrade()
    _20260806_0100_upgrade()
    _20260806_0200_upgrade()
    _20260807_0100_upgrade()
    _20260809_0100_upgrade()


def downgrade() -> None:
    """按原始 revision 逆序执行合并后的降级。"""

    _20260809_0100_downgrade()
    _20260807_0100_downgrade()
    _20260806_0200_downgrade()
    _20260806_0100_downgrade()
    _20260805_0200_downgrade()
    _20260805_0100_downgrade()


# ---- 原迁移 20260805_0100 ----

def _20260805_0100_upgrade() -> None:
    """删除三个旧助手的覆盖配置，并取消旧工具集上的活动运行。"""

    agent_ids = "'agent-coordinator', 'component-manager', 'resource-manager'"
    op.execute(f"DELETE FROM ai_agent_tool_user_configs WHERE agent_id IN ({agent_ids})")
    op.execute(f"DELETE FROM ai_agent_user_configs WHERE agent_id IN ({agent_ids})")
    op.execute("DELETE FROM ai_llm_slot_bindings WHERE slot IN ('component_manager', 'resource_manager')")
    op.execute(
        """
        UPDATE ai_agent_requirements
        SET status = 'cancelled', resolved_at = CURRENT_TIMESTAMP
        WHERE status = 'pending'
          AND run_id IN (
              SELECT run_id FROM ai_agent_runs
              WHERE agent_id IN ('agent-coordinator', 'component-manager', 'resource-manager')
                AND status IN ('pending', 'running', 'paused', 'waiting_external', 'cancelling')
          )
        """
    )
    op.execute(
        """
        UPDATE ai_page_mutation_jobs
        SET cancel_requested_at = CURRENT_TIMESTAMP
        WHERE run_id IN (
            SELECT run_id FROM ai_agent_runs
            WHERE agent_id IN ('agent-coordinator', 'component-manager', 'resource-manager')
              AND status IN ('pending', 'running', 'paused', 'waiting_external', 'cancelling')
        )
          AND status IN ('pending', 'running')
        """
    )
    op.execute(
        """
        UPDATE ai_agent_tool_calls
        SET status = 'error', message = '内容助手工具体系升级，旧工具调用已取消。'
        WHERE status = 'running'
          AND run_id IN (
              SELECT run_id FROM ai_agent_runs
              WHERE agent_id IN ('agent-coordinator', 'component-manager', 'resource-manager')
                AND status IN ('pending', 'running', 'paused', 'waiting_external', 'cancelling')
          )
        """
    )
    op.execute(
        """
        UPDATE ai_agent_runs
        SET status = 'cancelled',
            pending_requirement_json = NULL,
            cancel_requested_at = CURRENT_TIMESTAMP,
            finished_at = CURRENT_TIMESTAMP,
            error_code = 'AI_TOOLSET_MIGRATED',
            error_message = '内容助手工具体系升级，旧运行已取消。'
        WHERE agent_id IN ('agent-coordinator', 'component-manager', 'resource-manager')
          AND status IN ('pending', 'running', 'paused', 'waiting_external', 'cancelling')
        """
    )


def _20260805_0100_downgrade() -> None:
    """数据重置和运行取消不可逆，降级时不恢复旧工具覆盖。"""

# ---- 原迁移 20260805_0200 ----

def _20260805_0200_upgrade() -> None:
    """只迁移未绑定字体资源且保持原始值的系统内置主题。"""

    op.execute(
        """
        UPDATE workspace_themes
        SET heading_font_label = 'platform-sans',
            body_font_label = 'platform-sans',
            code_font_label = 'platform-mono',
            updated_at = CURRENT_TIMESTAMP
        WHERE heading_font_family_id IS NULL
          AND body_font_family_id IS NULL
          AND code_font_family_id IS NULL
          AND heading_font_label = 'system-ui'
          AND body_font_label = 'system-ui'
          AND code_font_label = 'monospace'
        """
    )


def _20260805_0200_downgrade() -> None:
    """将本次迁移命中的平台默认主题恢复为旧系统字体 token。"""

    op.execute(
        """
        UPDATE workspace_themes
        SET heading_font_label = 'system-ui',
            body_font_label = 'system-ui',
            code_font_label = 'monospace',
            updated_at = CURRENT_TIMESTAMP
        WHERE heading_font_family_id IS NULL
          AND body_font_family_id IS NULL
          AND code_font_family_id IS NULL
          AND heading_font_label = 'platform-sans'
          AND body_font_label = 'platform-sans'
          AND code_font_label = 'platform-mono'
        """
    )

# ---- 原迁移 20260806_0100 ----

def _20260806_0100_upgrade() -> None:
    """取消旧运行、归档旧会话，再替换会话 scope 字段。"""

    op.execute(
        """
        UPDATE ai_agent_requirements
        SET status = 'cancelled', resolved_at = CURRENT_TIMESTAMP
        WHERE status = 'pending'
          AND run_id IN (
              SELECT run_id FROM ai_agent_runs
              WHERE agent_id = 'agent-coordinator'
                AND status IN ('pending', 'running', 'paused', 'waiting_external', 'cancelling')
          )
        """
    )
    op.execute(
        """
        UPDATE ai_page_mutation_jobs
        SET status = 'cancelled', cancel_requested_at = CURRENT_TIMESTAMP,
            finished_at = CURRENT_TIMESTAMP, error_code = 'AI_SESSION_SCOPE_MIGRATED',
            error_message = '内容助手会话范围升级，旧任务已取消。'
        WHERE status IN ('pending', 'running')
          AND run_id IN (
              SELECT run_id FROM ai_agent_runs
              WHERE agent_id = 'agent-coordinator'
                AND status IN ('pending', 'running', 'paused', 'waiting_external', 'cancelling')
          )
        """
    )
    op.execute(
        """
        UPDATE ai_image_generation_jobs
        SET status = 'cancelled', cancel_requested_at = CURRENT_TIMESTAMP,
            finished_at = CURRENT_TIMESTAMP
        WHERE status IN ('pending', 'running', 'waiting_provider')
          AND run_id IN (
              SELECT run_id FROM ai_agent_runs
              WHERE agent_id = 'agent-coordinator'
                AND status IN ('pending', 'running', 'paused', 'waiting_external', 'cancelling')
          )
        """
    )
    op.execute(
        """
        UPDATE ai_agent_runs
        SET status = 'cancelled', pending_requirement_json = NULL,
            cancel_requested_at = CURRENT_TIMESTAMP, finished_at = CURRENT_TIMESTAMP,
            error_code = 'AI_SESSION_SCOPE_MIGRATED',
            error_message = '内容助手会话范围升级，旧运行已取消。'
        WHERE agent_id = 'agent-coordinator'
          AND status IN ('pending', 'running', 'paused', 'waiting_external', 'cancelling')
        """
    )
    op.execute(
        """
        UPDATE ai_agent_sessions
        SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE agent_id = 'agent-coordinator' AND deleted_at IS NULL
        """
    )

    with op.batch_alter_table("ai_agent_sessions") as batch:
        batch.add_column(sa.Column("focus_mode", sa.String(length=32), nullable=False, server_default="follow_route"))
        batch.add_column(sa.Column("pinned_project_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("work_scope_mode", sa.String(length=32), nullable=False, server_default="workspace"))
        batch.add_column(sa.Column("allowed_project_ids_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch.add_column(sa.Column("focus_version", sa.Integer(), nullable=False, server_default="0"))
        batch.create_foreign_key("fk_ai_agent_sessions_pinned_project_id_projects", "projects", ["pinned_project_id"], ["id"])
        batch.create_index("ix_ai_agent_sessions_focus_mode", ["focus_mode"])
        batch.create_index("ix_ai_agent_sessions_pinned_project_id", ["pinned_project_id"])
        batch.create_index("ix_ai_agent_sessions_work_scope_mode", ["work_scope_mode"])
        batch.drop_index("ix_ai_agent_sessions_scope_type")
        batch.drop_index("ix_ai_agent_sessions_project_id")
        batch.drop_index("ix_ai_agent_sessions_page_id")
        batch.drop_index("ix_ai_agent_sessions_component_id")
        batch.drop_index("ix_ai_agent_sessions_source")
        batch.drop_column("scope_type")
        batch.drop_column("project_id")
        batch.drop_column("page_id")
        batch.drop_column("component_id")
        batch.drop_column("source")


def _20260806_0100_downgrade() -> None:
    """恢复旧字段结构；已归档会话与已取消运行不会自动复活。"""

    with op.batch_alter_table("ai_agent_sessions") as batch:
        batch.add_column(sa.Column("scope_type", sa.String(length=32), nullable=False, server_default="workspace"))
        batch.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("page_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("component_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("source", sa.String(length=128), nullable=False, server_default="editor-workspace"))
        batch.create_index("ix_ai_agent_sessions_scope_type", ["scope_type"])
        batch.create_index("ix_ai_agent_sessions_project_id", ["project_id"])
        batch.create_index("ix_ai_agent_sessions_page_id", ["page_id"])
        batch.create_index("ix_ai_agent_sessions_component_id", ["component_id"])
        batch.create_index("ix_ai_agent_sessions_source", ["source"])
        batch.drop_index("ix_ai_agent_sessions_focus_mode")
        batch.drop_index("ix_ai_agent_sessions_pinned_project_id")
        batch.drop_index("ix_ai_agent_sessions_work_scope_mode")
        batch.drop_constraint("fk_ai_agent_sessions_pinned_project_id_projects", type_="foreignkey")
        batch.drop_column("focus_mode")
        batch.drop_column("pinned_project_id")
        batch.drop_column("work_scope_mode")
        batch.drop_column("allowed_project_ids_json")
        batch.drop_column("focus_version")

# ---- 原迁移 20260806_0200 ----

def _20260806_0200_upgrade() -> None:
    """新增成员归属与原始 deferred ID，并兼容回填历史父运行任务。"""

    with op.batch_alter_table("ai_page_mutation_jobs") as batch:
        batch.add_column(sa.Column("member_run_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("deferred_tool_call_id", sa.String(length=255), nullable=True))
        batch.create_foreign_key(
            "fk_ai_page_mutation_jobs_member_run_id_ai_agent_member_runs",
            "ai_agent_member_runs",
            ["member_run_id"],
            ["member_run_id"],
        )
        batch.create_index("ix_ai_page_mutation_jobs_member_run_id", ["member_run_id"])
        batch.create_index("ix_ai_page_mutation_jobs_deferred_tool_call_id", ["deferred_tool_call_id"])
    op.execute("UPDATE ai_page_mutation_jobs SET deferred_tool_call_id = tool_call_id")
    with op.batch_alter_table("ai_page_mutation_jobs") as batch:
        batch.alter_column("deferred_tool_call_id", existing_type=sa.String(length=255), nullable=False)


def _20260806_0200_downgrade() -> None:
    """移除成员页面任务扩展字段。"""

    with op.batch_alter_table("ai_page_mutation_jobs") as batch:
        batch.drop_index("ix_ai_page_mutation_jobs_deferred_tool_call_id")
        batch.drop_index("ix_ai_page_mutation_jobs_member_run_id")
        batch.drop_constraint(
            "fk_ai_page_mutation_jobs_member_run_id_ai_agent_member_runs",
            type_="foreignkey",
        )
        batch.drop_column("deferred_tool_call_id")
        batch.drop_column("member_run_id")

# ---- 原迁移 20260807_0100 ----

def _20260807_0100_upgrade() -> None:
    """重新启用 default 样式，并为其缺失主题补入工作空间默认主题。"""

    op.execute(
        """
        UPDATE workspace_styles
        SET deleted_at = NULL,
            theme_key = COALESCE(
                theme_key,
                (SELECT workspaces.default_theme_key FROM workspaces WHERE workspaces.id = workspace_styles.workspace_id)
            )
        WHERE key = 'default'
        """
    )


def _20260807_0100_downgrade() -> None:
    """数据修正不可安全逆转，降级时保留修正后的默认样式。"""

# ---- 原迁移 20260809_0100 ----

_FK_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
}
_FK_NAMES = {
    ("ai_agent_image_attachments", "promoted_asset_id"): "fk_ai_image_attachment_promoted_asset",
    ("asset_render_hint_backfill_jobs", "asset_id"): "fk_asset_render_hint_job_asset",
}


def _20260809_0100_upgrade() -> None:
    """记录附件最近资源状态，并让附件与回填任务不再阻断资源硬删除。"""

    with op.batch_alter_table("ai_agent_image_attachments") as batch:
        batch.add_column(
            sa.Column("last_promoted_asset_id", sa.Integer(), nullable=True)
        )
        batch.add_column(
            sa.Column("last_promoted_asset_name", sa.String(length=255), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "promoted_asset_deleted_at", sa.DateTime(timezone=True), nullable=True
            )
        )
    op.execute(
        """
        UPDATE ai_agent_image_attachments
        SET last_promoted_asset_id = promoted_asset_id,
            last_promoted_asset_name = (
                SELECT workspace_assets.name
                FROM workspace_assets
                WHERE workspace_assets.id = ai_agent_image_attachments.promoted_asset_id
            )
        WHERE promoted_asset_id IS NOT NULL
        """
    )
    _replace_foreign_key(
        table_name="ai_agent_image_attachments",
        column_name="promoted_asset_id",
        referred_table="workspace_assets",
        ondelete="SET NULL",
    )
    _replace_foreign_key(
        table_name="asset_render_hint_backfill_jobs",
        column_name="asset_id",
        referred_table="workspace_assets",
        ondelete="CASCADE",
    )


def _20260809_0100_downgrade() -> None:
    """恢复旧外键约束并移除附件资源生命周期字段。"""

    _replace_foreign_key(
        table_name="asset_render_hint_backfill_jobs",
        column_name="asset_id",
        referred_table="workspace_assets",
        ondelete=None,
    )
    _replace_foreign_key(
        table_name="ai_agent_image_attachments",
        column_name="promoted_asset_id",
        referred_table="workspace_assets",
        ondelete=None,
    )
    with op.batch_alter_table("ai_agent_image_attachments") as batch:
        batch.drop_column("promoted_asset_deleted_at")
        batch.drop_column("last_promoted_asset_name")
        batch.drop_column("last_promoted_asset_id")


def _replace_foreign_key(
    *,
    table_name: str,
    column_name: str,
    referred_table: str,
    ondelete: str | None,
) -> None:
    """跨 PostgreSQL 与 SQLite 查找并替换指定单列外键。"""

    bind = op.get_bind()
    foreign_keys = sa.inspect(bind).get_foreign_keys(table_name)
    matched = next(
        (
            item
            for item in foreign_keys
            if item.get("constrained_columns") == [column_name]
            and item.get("referred_table") == referred_table
        ),
        None,
    )
    reflected_name = f"fk_{table_name}_{column_name}_{referred_table}"
    constraint_name = str((matched or {}).get("name") or reflected_name)
    new_constraint_name = _FK_NAMES.get(
        (table_name, column_name),
        f"fk_{table_name[:24]}_{column_name[:20]}",
    )
    with op.batch_alter_table(
        table_name, naming_convention=_FK_NAMING_CONVENTION
    ) as batch:
        batch.drop_constraint(constraint_name, type_="foreignkey")
        batch.create_foreign_key(
            new_constraint_name,
            referred_table,
            [column_name],
            ["id"],
            ondelete=ondelete,
        )
