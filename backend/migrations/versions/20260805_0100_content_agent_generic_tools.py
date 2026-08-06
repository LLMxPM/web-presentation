"""文件功能：合并三个助手配置，并收敛迁移时仍未终止的旧运行。

Revision ID: 20260805_0100
Revises: 20260730_0100
Create Date: 2026-08-05 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260805_0100"
down_revision: Union[str, Sequence[str], None] = "20260730_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    """数据重置和运行取消不可逆，降级时不恢复旧工具覆盖。"""
