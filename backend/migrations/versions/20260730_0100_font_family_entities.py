"""文件功能：合并截至 2026-07-30 的数据库结构，作为当前发布基线。

Revision ID: 20260730_0100
Revises:
Create Date: 2026-07-30 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260730_0100"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """按原始 revision 顺序执行合并后的升级。"""

    _20260626_0111_upgrade()
    _20260701_0100_upgrade()
    _20260712_0500_upgrade()
    _20260720_0100_upgrade()
    _20260721_0100_upgrade()
    _20260723_0100_upgrade()
    _20260728_0100_upgrade()
    _20260730_0100_upgrade()


def downgrade() -> None:
    """按原始 revision 逆序执行合并后的降级。"""

    _20260730_0100_downgrade()
    _20260728_0100_downgrade()
    _20260723_0100_downgrade()
    _20260721_0100_downgrade()
    _20260720_0100_downgrade()
    _20260712_0500_downgrade()
    _20260701_0100_downgrade()
    _20260626_0111_downgrade()


# ---- 原迁移 20260626_0111 ----

def _20260626_0111_upgrade() -> None:
    """从空数据库创建当前开发库对应的完整结构。"""
    # ### Alembic 自动生成命令，作为发布基线保留。 ###
    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('display_name', sa.String(length=128), nullable=False),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('preview_size_presets', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('workspaces',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('last_opened_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('default_theme_key', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('ai_agent_tool_user_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('agent_id', sa.String(length=128), nullable=False),
    sa.Column('tool_key', sa.String(length=128), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('description_override', sa.Text(), nullable=True),
    sa.Column('instructions_override', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'agent_id', 'tool_key', name='uq_ai_agent_tool_user_configs_user_tool')
    )
    op.create_index(op.f('ix_ai_agent_tool_user_configs_agent_id'), 'ai_agent_tool_user_configs', ['agent_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_tool_user_configs_tool_key'), 'ai_agent_tool_user_configs', ['tool_key'], unique=False)
    op.create_index(op.f('ix_ai_agent_tool_user_configs_user_id'), 'ai_agent_tool_user_configs', ['user_id'], unique=False)
    op.create_table('ai_agent_user_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('agent_id', sa.String(length=128), nullable=False),
    sa.Column('description_override', sa.Text(), nullable=True),
    sa.Column('prompt_override', sa.Text(), nullable=True),
    sa.Column('prompt_mode', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'agent_id', name='uq_ai_agent_user_configs_user_agent')
    )
    op.create_index(op.f('ix_ai_agent_user_configs_agent_id'), 'ai_agent_user_configs', ['agent_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_user_configs_user_id'), 'ai_agent_user_configs', ['user_id'], unique=False)
    op.create_table('ai_llm_provider_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('scope', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('provider_key', sa.String(length=64), nullable=False),
    sa.Column('base_url', sa.Text(), nullable=True),
    sa.Column('api_key_ciphertext', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_llm_provider_configs_provider_key'), 'ai_llm_provider_configs', ['provider_key'], unique=False)
    op.create_index(op.f('ix_ai_llm_provider_configs_scope'), 'ai_llm_provider_configs', ['scope'], unique=False)
    op.create_index(op.f('ix_ai_llm_provider_configs_status'), 'ai_llm_provider_configs', ['status'], unique=False)
    op.create_index(op.f('ix_ai_llm_provider_configs_user_id'), 'ai_llm_provider_configs', ['user_id'], unique=False)
    op.create_table('projects',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_system_managed', sa.Boolean(), server_default=sa.text('(false)'), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('page_width', sa.Integer(), server_default=sa.text('(1920)'), nullable=False),
    sa.Column('page_height', sa.Integer(), server_default=sa.text('(1080)'), nullable=False),
    sa.Column('base_font_size', sa.String(length=32), server_default=sa.text("'20px'"), nullable=False),
    sa.Column('icon_default_stroke_width', sa.Integer(), server_default=sa.text('2'), nullable=False),
    sa.Column('show_pdf_export_button', sa.Boolean(), server_default=sa.text('(true)'), nullable=False),
    sa.Column('menu_mode', sa.String(length=16), server_default=sa.text("'preview'"), nullable=False),
    sa.Column('theme_key', sa.String(length=64), nullable=True),
    sa.Column('theme_config_yaml', sa.Text(), nullable=False),
    sa.Column('style_spec_markdown', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('build_extra_assets_json', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_index(op.f('ix_projects_workspace_id'), 'projects', ['workspace_id'], unique=False)
    op.create_table('user_sessions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_table('workspace_assets',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('original_name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('file_size', sa.Integer(), nullable=False),
    sa.Column('file_hash', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=255), nullable=True),
    sa.Column('asset_type', sa.String(length=50), server_default='icon', nullable=False),
    sa.Column('tags', sa.JSON(), server_default='[]', nullable=False),
    sa.Column('analysis_metadata', sa.JSON(), nullable=True),
    sa.Column('render_metadata', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(length=32), server_default='active', nullable=False),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('archive_reason', sa.Text(), nullable=True),
    sa.Column('source_asset_id', sa.Integer(), nullable=True),
    sa.Column('history_kind', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['source_asset_id'], ['workspace_assets.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'name', name='uq_workspace_assets_workspace_name')
    )
    op.create_index(op.f('ix_workspace_assets_file_hash'), 'workspace_assets', ['file_hash'], unique=False)
    op.create_index(op.f('ix_workspace_assets_source_asset_id'), 'workspace_assets', ['source_asset_id'], unique=False)
    op.create_index(op.f('ix_workspace_assets_status'), 'workspace_assets', ['status'], unique=False)
    op.create_index(op.f('ix_workspace_assets_workspace_id'), 'workspace_assets', ['workspace_id'], unique=False)
    op.create_table('workspace_components',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('preview_schema', sa.Text(), nullable=True),
    sa.Column('current_version_no', sa.Integer(), server_default='0', nullable=False),
    sa.Column('draft_base_version_no', sa.Integer(), server_default='0', nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('file_type', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('import_name', sa.String(length=64), nullable=False),
    sa.Column('component_type', sa.String(length=64), server_default='内容组件', nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_index(op.f('ix_workspace_components_component_type'), 'workspace_components', ['component_type'], unique=False)
    op.create_index(op.f('ix_workspace_components_workspace_id'), 'workspace_components', ['workspace_id'], unique=False)
    op.create_table('workspace_members',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=32), server_default=sa.text("'owner'"), nullable=False),
    sa.Column('status', sa.String(length=32), server_default=sa.text("'active'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'user_id', name='uq_workspace_members_workspace_user')
    )
    op.create_index(op.f('ix_workspace_members_status'), 'workspace_members', ['status'], unique=False)
    op.create_index(op.f('ix_workspace_members_user_id'), 'workspace_members', ['user_id'], unique=False)
    op.create_index(op.f('ix_workspace_members_workspace_id'), 'workspace_members', ['workspace_id'], unique=False)
    op.create_table('workspace_styles',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('page_width', sa.Integer(), server_default=sa.text('(1920)'), nullable=False),
    sa.Column('page_height', sa.Integer(), server_default=sa.text('(1080)'), nullable=False),
    sa.Column('base_font_size', sa.String(length=32), server_default=sa.text("'20px'"), nullable=False),
    sa.Column('icon_default_stroke_width', sa.Integer(), server_default=sa.text('2'), nullable=False),
    sa.Column('show_pdf_export_button', sa.Boolean(), server_default=sa.text('(true)'), nullable=False),
    sa.Column('menu_mode', sa.String(length=16), server_default=sa.text("'preview'"), nullable=False),
    sa.Column('theme_key', sa.String(length=64), nullable=True),
    sa.Column('style_spec_markdown', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'key', name='uq_workspace_styles_workspace_key')
    )
    op.create_index(op.f('ix_workspace_styles_workspace_id'), 'workspace_styles', ['workspace_id'], unique=False)
    op.create_table('ai_agent_image_attachments',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.String(length=128), nullable=False),
    sa.Column('run_id', sa.String(length=128), nullable=True),
    sa.Column('source_kind', sa.String(length=32), nullable=False),
    sa.Column('tool_name', sa.String(length=128), nullable=True),
    sa.Column('tool_call_id', sa.String(length=255), nullable=True),
    sa.Column('source_payload_json', sa.JSON(), nullable=True),
    sa.Column('storage_key', sa.Text(), nullable=False),
    sa.Column('original_name', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=128), nullable=False),
    sa.Column('file_size', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('model_url', sa.Text(), nullable=True),
    sa.Column('model_url_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('model_url_last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('owned_object', sa.Boolean(), nullable=False),
    sa.Column('promoted_asset_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['promoted_asset_id'], ['workspace_assets.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_agent_image_attachments_promoted_asset_id'), 'ai_agent_image_attachments', ['promoted_asset_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_image_attachments_run_id'), 'ai_agent_image_attachments', ['run_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_image_attachments_session_id'), 'ai_agent_image_attachments', ['session_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_image_attachments_sha256'), 'ai_agent_image_attachments', ['sha256'], unique=False)
    op.create_index(op.f('ix_ai_agent_image_attachments_source_kind'), 'ai_agent_image_attachments', ['source_kind'], unique=False)
    op.create_index(op.f('ix_ai_agent_image_attachments_status'), 'ai_agent_image_attachments', ['status'], unique=False)
    op.create_index(op.f('ix_ai_agent_image_attachments_tool_call_id'), 'ai_agent_image_attachments', ['tool_call_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_image_attachments_tool_name'), 'ai_agent_image_attachments', ['tool_name'], unique=False)
    op.create_index(op.f('ix_ai_agent_image_attachments_user_id'), 'ai_agent_image_attachments', ['user_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_image_attachments_workspace_id'), 'ai_agent_image_attachments', ['workspace_id'], unique=False)
    op.create_table('ai_llm_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('scope', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('provider_config_id', sa.Integer(), nullable=False),
    sa.Column('model_id', sa.String(length=255), nullable=False),
    sa.Column('thinking_enabled', sa.Boolean(), nullable=False),
    sa.Column('thinking_effort', sa.String(length=64), nullable=True),
    sa.Column('supports_image_input', sa.Boolean(), nullable=False),
    sa.Column('context_window_tokens', sa.Integer(), nullable=False),
    sa.Column('max_output_tokens', sa.Integer(), nullable=False),
    sa.Column('history_token_ratio', sa.Float(), nullable=False),
    sa.Column('compression_target_ratio', sa.Float(), nullable=False),
    sa.Column('advanced_config_json', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['provider_config_id'], ['ai_llm_provider_configs.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_llm_configs_provider_config_id'), 'ai_llm_configs', ['provider_config_id'], unique=False)
    op.create_index(op.f('ix_ai_llm_configs_scope'), 'ai_llm_configs', ['scope'], unique=False)
    op.create_index(op.f('ix_ai_llm_configs_status'), 'ai_llm_configs', ['status'], unique=False)
    op.create_index(op.f('ix_ai_llm_configs_user_id'), 'ai_llm_configs', ['user_id'], unique=False)
    op.create_table('pages',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('page_content', sa.Text(), nullable=False),
    sa.Column('current_version_no', sa.Integer(), server_default='1', nullable=False),
    sa.Column('file_type', sa.String(length=32), nullable=False),
    sa.Column('title', sa.String(length=128), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('speaker_notes', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=True),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('screenshot_storage_key', sa.String(length=255), nullable=True),
    sa.Column('screenshot_version_no', sa.Integer(), nullable=True),
    sa.Column('screenshot_config_hash', sa.String(length=64), nullable=True),
    sa.Column('screenshot_updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_index(op.f('ix_pages_project_id'), 'pages', ['project_id'], unique=False)
    op.create_index(op.f('ix_pages_workspace_id'), 'pages', ['workspace_id'], unique=False)
    op.create_table('project_suggested_components',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['workspace_components.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'component_id', name='uq_project_suggested_components_project_component')
    )
    op.create_index(op.f('ix_project_suggested_components_component_id'), 'project_suggested_components', ['component_id'], unique=False)
    op.create_index(op.f('ix_project_suggested_components_project_id'), 'project_suggested_components', ['project_id'], unique=False)
    op.create_table('project_suggested_reference_assets',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('asset_id', sa.Integer(), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['asset_id'], ['workspace_assets.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'asset_id', name='uq_project_suggested_reference_assets_project_asset')
    )
    op.create_index(op.f('ix_project_suggested_reference_assets_asset_id'), 'project_suggested_reference_assets', ['asset_id'], unique=False)
    op.create_index(op.f('ix_project_suggested_reference_assets_project_id'), 'project_suggested_reference_assets', ['project_id'], unique=False)
    op.create_table('releases',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('version', sa.String(length=128), nullable=True),
    sa.Column('is_draft', sa.Boolean(), nullable=False),
    sa.Column('manifest', sa.JSON(), nullable=False),
    sa.Column('config_bundle', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_releases_project_id'), 'releases', ['project_id'], unique=False)
    op.create_index(op.f('ix_releases_tenant_id'), 'releases', ['tenant_id'], unique=False)
    op.create_table('workspace_component_versions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('version_no', sa.Integer(), nullable=False),
    sa.Column('version_label', sa.String(length=64), nullable=False),
    sa.Column('release_name', sa.String(length=128), nullable=True),
    sa.Column('file_type', sa.String(length=32), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('preview_schema', sa.Text(), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('preview_schema_hash', sa.String(length=64), nullable=True),
    sa.Column('component_fingerprint', sa.String(length=64), nullable=True),
    sa.Column('fingerprint_schema_version', sa.Integer(), nullable=True),
    sa.Column('change_note', sa.String(length=255), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['workspace_components.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('component_id', 'version_no', name='uq_workspace_component_versions_component_version')
    )
    op.create_index('ix_workspace_component_versions_component_fingerprint', 'workspace_component_versions', ['component_fingerprint'], unique=False)
    op.create_index(op.f('ix_workspace_component_versions_component_id'), 'workspace_component_versions', ['component_id'], unique=False)
    op.create_table('workspace_font_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('asset_id', sa.Integer(), nullable=False),
    sa.Column('asset_name', sa.String(length=255), nullable=False),
    sa.Column('font_family', sa.String(length=255), nullable=False),
    sa.Column('font_format', sa.String(length=32), nullable=False),
    sa.Column('font_weight', sa.String(length=32), server_default='400', nullable=False),
    sa.Column('font_style', sa.String(length=32), server_default='normal', nullable=False),
    sa.Column('font_display', sa.String(length=32), server_default='swap', nullable=False),
    sa.Column('status', sa.String(length=32), server_default='active', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['asset_id'], ['workspace_assets.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'asset_id', name='uq_workspace_font_configs_workspace_asset'),
    sa.UniqueConstraint('workspace_id', 'asset_name', name='uq_workspace_font_configs_workspace_asset_name')
    )
    op.create_index(op.f('ix_workspace_font_configs_asset_id'), 'workspace_font_configs', ['asset_id'], unique=False)
    op.create_index(op.f('ix_workspace_font_configs_workspace_id'), 'workspace_font_configs', ['workspace_id'], unique=False)
    op.create_table('workspace_style_suggested_components',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('style_id', sa.Integer(), nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['workspace_components.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['style_id'], ['workspace_styles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('style_id', 'component_id', name='uq_workspace_style_suggested_components_style_component')
    )
    op.create_index(op.f('ix_workspace_style_suggested_components_component_id'), 'workspace_style_suggested_components', ['component_id'], unique=False)
    op.create_index(op.f('ix_workspace_style_suggested_components_style_id'), 'workspace_style_suggested_components', ['style_id'], unique=False)
    op.create_table('ai_agent_sessions',
    sa.Column('session_id', sa.String(length=128), nullable=False),
    sa.Column('agent_id', sa.String(length=128), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('session_name', sa.String(length=128), nullable=True),
    sa.Column('scope_type', sa.String(length=32), nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('page_id', sa.Integer(), nullable=True),
    sa.Column('component_id', sa.Integer(), nullable=True),
    sa.Column('source', sa.String(length=128), nullable=False),
    sa.Column('metadata_json', sa.JSON(), nullable=False),
    sa.Column('summary_json', sa.JSON(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['component_id'], ['workspace_components.id'], ),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('session_id')
    )
    op.create_index(op.f('ix_ai_agent_sessions_agent_id'), 'ai_agent_sessions', ['agent_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_sessions_component_id'), 'ai_agent_sessions', ['component_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_sessions_deleted_at'), 'ai_agent_sessions', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_ai_agent_sessions_page_id'), 'ai_agent_sessions', ['page_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_sessions_project_id'), 'ai_agent_sessions', ['project_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_sessions_scope_type'), 'ai_agent_sessions', ['scope_type'], unique=False)
    op.create_index(op.f('ix_ai_agent_sessions_source'), 'ai_agent_sessions', ['source'], unique=False)
    op.create_index(op.f('ix_ai_agent_sessions_user_id'), 'ai_agent_sessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_sessions_workspace_id'), 'ai_agent_sessions', ['workspace_id'], unique=False)
    op.create_table('ai_llm_slot_bindings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('scope', sa.String(length=32), nullable=False),
    sa.Column('slot', sa.String(length=64), nullable=False),
    sa.Column('llm_config_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['llm_config_id'], ['ai_llm_configs.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_llm_slot_bindings_llm_config_id'), 'ai_llm_slot_bindings', ['llm_config_id'], unique=False)
    op.create_index(op.f('ix_ai_llm_slot_bindings_scope'), 'ai_llm_slot_bindings', ['scope'], unique=False)
    op.create_index(op.f('ix_ai_llm_slot_bindings_user_id'), 'ai_llm_slot_bindings', ['user_id'], unique=False)
    op.create_index('uq_ai_llm_slot_bindings_global_slot', 'ai_llm_slot_bindings', ['slot'], unique=True, sqlite_where=sa.text("scope = 'global'"), postgresql_where=sa.text("scope = 'global'"))
    op.create_index('uq_ai_llm_slot_bindings_personal_user_slot', 'ai_llm_slot_bindings', ['user_id', 'slot'], unique=True, sqlite_where=sa.text("scope = 'personal'"), postgresql_where=sa.text("scope = 'personal'"))
    op.create_table('component_version_component_dependencies',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('component_version_id', sa.Integer(), nullable=False),
    sa.Column('dependency_kind', sa.String(length=32), nullable=False),
    sa.Column('dependency_component_id', sa.Integer(), nullable=True),
    sa.Column('dependency_component_version_id', sa.Integer(), nullable=True),
    sa.Column('dependency_component_code', sa.String(length=64), nullable=True),
    sa.Column('dependency_component_version_no', sa.Integer(), nullable=True),
    sa.Column('runtime_module_path', sa.String(length=255), nullable=True),
    sa.Column('runtime_kit_name', sa.String(length=128), nullable=True),
    sa.Column('runtime_kit_base_name', sa.String(length=128), nullable=True),
    sa.Column('runtime_kit_version_no', sa.Integer(), nullable=True),
    sa.Column('runtime_kit_import_path', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['workspace_components.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['component_version_id'], ['workspace_component_versions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['dependency_component_id'], ['workspace_components.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['dependency_component_version_id'], ['workspace_component_versions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('component_version_id', 'dependency_kind', 'dependency_component_version_id', 'runtime_module_path', name='uq_component_version_component_dependencies_unique_dependency')
    )
    op.create_index('ix_cvcd_comp_id', 'component_version_component_dependencies', ['component_id'], unique=False)
    op.create_index('ix_cvcd_cver_id', 'component_version_component_dependencies', ['component_version_id'], unique=False)
    op.create_index('ix_cvcd_dep_comp_id', 'component_version_component_dependencies', ['dependency_component_id'], unique=False)
    op.create_index('ix_cvcd_dep_cver_id', 'component_version_component_dependencies', ['dependency_component_version_id'], unique=False)
    op.create_table('component_version_component_resources',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('component_version_id', sa.Integer(), nullable=False),
    sa.Column('component_name', sa.String(length=128), nullable=False),
    sa.Column('resource_attr', sa.String(length=64), server_default='name', nullable=False),
    sa.Column('resource_name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['workspace_components.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['component_version_id'], ['workspace_component_versions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('component_version_id', 'component_name', 'resource_attr', 'resource_name', name='uq_component_version_component_resources_unique_resource')
    )
    op.create_index('ix_cvcr_component_id', 'component_version_component_resources', ['component_id'], unique=False)
    op.create_index('ix_cvcr_component_version_id', 'component_version_component_resources', ['component_version_id'], unique=False)
    op.create_index('ix_cvcr_workspace_component_resource', 'component_version_component_resources', ['workspace_id', 'component_name', 'resource_name'], unique=False)
    op.create_index('ix_cvcr_workspace_id', 'component_version_component_resources', ['workspace_id'], unique=False)
    op.create_table('page_screenshot_jobs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('job_group_id', sa.String(length=64), nullable=True),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('page_id', sa.Integer(), nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=True),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('viewport_width', sa.Integer(), nullable=False),
    sa.Column('viewport_height', sa.Integer(), nullable=False),
    sa.Column('config_hash', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('error_code', sa.String(length=64), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_page_screenshot_jobs_config_hash'), 'page_screenshot_jobs', ['config_hash'], unique=False)
    op.create_index(op.f('ix_page_screenshot_jobs_job_group_id'), 'page_screenshot_jobs', ['job_group_id'], unique=False)
    op.create_index(op.f('ix_page_screenshot_jobs_page_id'), 'page_screenshot_jobs', ['page_id'], unique=False)
    op.create_index(op.f('ix_page_screenshot_jobs_project_id'), 'page_screenshot_jobs', ['project_id'], unique=False)
    op.create_index(op.f('ix_page_screenshot_jobs_source'), 'page_screenshot_jobs', ['source'], unique=False)
    op.create_index(op.f('ix_page_screenshot_jobs_status'), 'page_screenshot_jobs', ['status'], unique=False)
    op.create_index(op.f('ix_page_screenshot_jobs_workspace_id'), 'page_screenshot_jobs', ['workspace_id'], unique=False)
    op.create_index('ix_page_screenshot_jobs_dedupe_active', 'page_screenshot_jobs', ['page_id', 'config_hash', 'viewport_width', 'viewport_height', 'status'], unique=False)
    op.create_table('page_versions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('page_id', sa.Integer(), nullable=False),
    sa.Column('version_no', sa.Integer(), nullable=False),
    sa.Column('version_label', sa.String(length=64), nullable=False),
    sa.Column('file_type', sa.String(length=32), nullable=False),
    sa.Column('storage_type', sa.String(length=32), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('speaker_notes', sa.Text(), nullable=True),
    sa.Column('is_important', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('snapshot_name', sa.String(length=128), nullable=True),
    sa.Column('change_note', sa.String(length=255), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('page_id', 'version_no', name='uq_page_versions_page_id_version_no')
    )
    op.create_index(op.f('ix_page_versions_page_id'), 'page_versions', ['page_id'], unique=False)
    op.create_table('project_build_jobs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('snapshot_release_id', sa.Integer(), nullable=False),
    sa.Column('base_url', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('artifact_storage_key', sa.Text(), nullable=True),
    sa.Column('artifact_download_url', sa.Text(), nullable=True),
    sa.Column('artifact_entry_file', sa.String(length=255), nullable=True),
    sa.Column('artifact_sha256', sa.String(length=128), nullable=True),
    sa.Column('artifact_size_bytes', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['snapshot_release_id'], ['releases.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_build_jobs_project_id'), 'project_build_jobs', ['project_id'], unique=False)
    op.create_index(op.f('ix_project_build_jobs_snapshot_release_id'), 'project_build_jobs', ['snapshot_release_id'], unique=False)
    op.create_index(op.f('ix_project_build_jobs_status'), 'project_build_jobs', ['status'], unique=False)
    op.create_table('project_routes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('route', sa.String(length=128), nullable=False),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.Column('hidden', sa.Boolean(), server_default=sa.text('(false)'), nullable=False),
    sa.Column('page_id', sa.Integer(), nullable=True),
    sa.Column('route_type', sa.String(length=32), nullable=False),
    sa.Column('group_title', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['parent_id'], ['project_routes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_routes_page_id'), 'project_routes', ['page_id'], unique=False)
    op.create_index(op.f('ix_project_routes_parent_id'), 'project_routes', ['parent_id'], unique=False)
    op.create_index(op.f('ix_project_routes_project_id'), 'project_routes', ['project_id'], unique=False)
    op.create_table('release_modules',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('release_id', sa.Integer(), nullable=False),
    sa.Column('logical_path', sa.String(length=255), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['release_id'], ['releases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_release_modules_release_id'), 'release_modules', ['release_id'], unique=False)
    op.create_table('workspace_themes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('logo_asset_id', sa.Integer(), nullable=True),
    sa.Column('invert_logo_asset_id', sa.Integer(), nullable=True),
    sa.Column('project_icon_asset_id', sa.Integer(), nullable=True),
    sa.Column('logo_path', sa.String(length=255), nullable=True),
    sa.Column('invert_logo_path', sa.String(length=255), nullable=True),
    sa.Column('project_icon_name', sa.String(length=255), nullable=True),
    sa.Column('heading_font_id', sa.Integer(), nullable=True),
    sa.Column('body_font_id', sa.Integer(), nullable=True),
    sa.Column('code_font_id', sa.Integer(), nullable=True),
    sa.Column('heading_font_label', sa.String(length=255), nullable=False),
    sa.Column('body_font_label', sa.String(length=255), nullable=False),
    sa.Column('code_font_label', sa.String(length=255), nullable=False),
    sa.Column('palette', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['body_font_id'], ['workspace_font_configs.id'], ),
    sa.ForeignKeyConstraint(['code_font_id'], ['workspace_font_configs.id'], ),
    sa.ForeignKeyConstraint(['heading_font_id'], ['workspace_font_configs.id'], ),
    sa.ForeignKeyConstraint(['invert_logo_asset_id'], ['workspace_assets.id'], ),
    sa.ForeignKeyConstraint(['logo_asset_id'], ['workspace_assets.id'], ),
    sa.ForeignKeyConstraint(['project_icon_asset_id'], ['workspace_assets.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'key', name='uq_workspace_themes_workspace_key')
    )
    op.create_index(op.f('ix_workspace_themes_body_font_id'), 'workspace_themes', ['body_font_id'], unique=False)
    op.create_index(op.f('ix_workspace_themes_code_font_id'), 'workspace_themes', ['code_font_id'], unique=False)
    op.create_index(op.f('ix_workspace_themes_heading_font_id'), 'workspace_themes', ['heading_font_id'], unique=False)
    op.create_index(op.f('ix_workspace_themes_invert_logo_asset_id'), 'workspace_themes', ['invert_logo_asset_id'], unique=False)
    op.create_index(op.f('ix_workspace_themes_logo_asset_id'), 'workspace_themes', ['logo_asset_id'], unique=False)
    op.create_index(op.f('ix_workspace_themes_project_icon_asset_id'), 'workspace_themes', ['project_icon_asset_id'], unique=False)
    op.create_index(op.f('ix_workspace_themes_workspace_id'), 'workspace_themes', ['workspace_id'], unique=False)
    op.create_table('ai_agent_runs',
    sa.Column('run_id', sa.String(length=128), nullable=False),
    sa.Column('session_id', sa.String(length=128), nullable=False),
    sa.Column('agent_id', sa.String(length=128), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('scope_type', sa.String(length=32), nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('page_id', sa.Integer(), nullable=True),
    sa.Column('component_id', sa.Integer(), nullable=True),
    sa.Column('source', sa.String(length=128), nullable=False),
    sa.Column('input_payload_json', sa.JSON(), nullable=False),
    sa.Column('message_history_json', sa.JSON(), nullable=False),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('reasoning_content', sa.Text(), nullable=True),
    sa.Column('pending_requirement_json', sa.JSON(), nullable=True),
    sa.Column('event_index', sa.Integer(), nullable=False),
    sa.Column('cancel_requested_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_code', sa.String(length=128), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['workspace_components.id'], ),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['ai_agent_sessions.session_id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('run_id')
    )
    op.create_index(op.f('ix_ai_agent_runs_agent_id'), 'ai_agent_runs', ['agent_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_runs_component_id'), 'ai_agent_runs', ['component_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_runs_page_id'), 'ai_agent_runs', ['page_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_runs_project_id'), 'ai_agent_runs', ['project_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_runs_scope_type'), 'ai_agent_runs', ['scope_type'], unique=False)
    op.create_index(op.f('ix_ai_agent_runs_session_id'), 'ai_agent_runs', ['session_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_runs_source'), 'ai_agent_runs', ['source'], unique=False)
    op.create_index(op.f('ix_ai_agent_runs_status'), 'ai_agent_runs', ['status'], unique=False)
    op.create_index(op.f('ix_ai_agent_runs_user_id'), 'ai_agent_runs', ['user_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_runs_workspace_id'), 'ai_agent_runs', ['workspace_id'], unique=False)
    op.create_table('page_version_component_dependencies',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('page_id', sa.Integer(), nullable=False),
    sa.Column('page_version_id', sa.Integer(), nullable=False),
    sa.Column('dependency_kind', sa.String(length=32), nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=True),
    sa.Column('component_version_id', sa.Integer(), nullable=True),
    sa.Column('component_code', sa.String(length=64), nullable=True),
    sa.Column('component_version_no', sa.Integer(), nullable=True),
    sa.Column('runtime_module_path', sa.String(length=255), nullable=True),
    sa.Column('runtime_kit_name', sa.String(length=128), nullable=True),
    sa.Column('runtime_kit_base_name', sa.String(length=128), nullable=True),
    sa.Column('runtime_kit_version_no', sa.Integer(), nullable=True),
    sa.Column('runtime_kit_import_path', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['workspace_components.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['component_version_id'], ['workspace_component_versions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['page_version_id'], ['page_versions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('page_version_id', 'dependency_kind', 'component_version_id', 'runtime_module_path', name='uq_page_version_component_dependencies_unique_dependency')
    )
    op.create_index('ix_pvcd_comp_id', 'page_version_component_dependencies', ['component_id'], unique=False)
    op.create_index('ix_pvcd_cver_id', 'page_version_component_dependencies', ['component_version_id'], unique=False)
    op.create_index('ix_pvcd_page_id', 'page_version_component_dependencies', ['page_id'], unique=False)
    op.create_index('ix_pvcd_pver_id', 'page_version_component_dependencies', ['page_version_id'], unique=False)
    op.create_table('page_version_component_resources',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('page_id', sa.Integer(), nullable=False),
    sa.Column('page_version_id', sa.Integer(), nullable=False),
    sa.Column('component_name', sa.String(length=128), nullable=False),
    sa.Column('resource_attr', sa.String(length=64), server_default='name', nullable=False),
    sa.Column('resource_name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['page_version_id'], ['page_versions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('page_version_id', 'component_name', 'resource_attr', 'resource_name', name='uq_page_version_component_resources_unique_resource')
    )
    op.create_index(op.f('ix_page_version_component_resources_page_id'), 'page_version_component_resources', ['page_id'], unique=False)
    op.create_index(op.f('ix_page_version_component_resources_page_version_id'), 'page_version_component_resources', ['page_version_id'], unique=False)
    op.create_index(op.f('ix_page_version_component_resources_project_id'), 'page_version_component_resources', ['project_id'], unique=False)
    op.create_table('page_version_component_usages',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('page_id', sa.Integer(), nullable=False),
    sa.Column('page_version_id', sa.Integer(), nullable=False),
    sa.Column('component_name', sa.String(length=128), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['page_version_id'], ['page_versions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('page_version_id', 'component_name', name='uq_page_version_component_usages_version_component')
    )
    op.create_index(op.f('ix_page_version_component_usages_page_id'), 'page_version_component_usages', ['page_id'], unique=False)
    op.create_index(op.f('ix_page_version_component_usages_page_version_id'), 'page_version_component_usages', ['page_version_id'], unique=False)
    op.create_index(op.f('ix_page_version_component_usages_project_id'), 'page_version_component_usages', ['project_id'], unique=False)
    op.create_table('ai_agent_member_runs',
    sa.Column('member_run_id', sa.String(length=128), nullable=False),
    sa.Column('parent_run_id', sa.String(length=128), nullable=False),
    sa.Column('session_id', sa.String(length=128), nullable=False),
    sa.Column('agent_id', sa.String(length=128), nullable=False),
    sa.Column('agent_name', sa.String(length=128), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('delegate_tool_call_id', sa.String(length=255), nullable=True),
    sa.Column('input_payload_json', sa.JSON(), nullable=False),
    sa.Column('message_history_json', sa.JSON(), nullable=False),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('reasoning_content', sa.Text(), nullable=True),
    sa.Column('pending_requirement_json', sa.JSON(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['parent_run_id'], ['ai_agent_runs.run_id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['ai_agent_sessions.session_id'], ),
    sa.PrimaryKeyConstraint('member_run_id')
    )
    op.create_index(op.f('ix_ai_agent_member_runs_agent_id'), 'ai_agent_member_runs', ['agent_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_member_runs_delegate_tool_call_id'), 'ai_agent_member_runs', ['delegate_tool_call_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_member_runs_parent_run_id'), 'ai_agent_member_runs', ['parent_run_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_member_runs_session_id'), 'ai_agent_member_runs', ['session_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_member_runs_status'), 'ai_agent_member_runs', ['status'], unique=False)
    op.create_table('ai_agent_messages',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.String(length=128), nullable=False),
    sa.Column('run_id', sa.String(length=128), nullable=True),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('reasoning_content', sa.Text(), nullable=True),
    sa.Column('message_json', sa.JSON(), nullable=True),
    sa.Column('attachments_json', sa.JSON(), nullable=False),
    sa.Column('order_index', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['ai_agent_runs.run_id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['ai_agent_sessions.session_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_agent_messages_role'), 'ai_agent_messages', ['role'], unique=False)
    op.create_index(op.f('ix_ai_agent_messages_run_id'), 'ai_agent_messages', ['run_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_messages_session_id'), 'ai_agent_messages', ['session_id'], unique=False)
    op.create_table('ai_agent_requirements',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('requirement_id', sa.String(length=128), nullable=False),
    sa.Column('session_id', sa.String(length=128), nullable=False),
    sa.Column('run_id', sa.String(length=128), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('tool_call_id', sa.String(length=255), nullable=True),
    sa.Column('tool_name', sa.String(length=128), nullable=True),
    sa.Column('member_agent_id', sa.String(length=128), nullable=True),
    sa.Column('member_agent_name', sa.String(length=128), nullable=True),
    sa.Column('member_run_id', sa.String(length=128), nullable=True),
    sa.Column('payload_json', sa.JSON(), nullable=False),
    sa.Column('resolved_payload_json', sa.JSON(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['ai_agent_runs.run_id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['ai_agent_sessions.session_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_agent_requirements_kind'), 'ai_agent_requirements', ['kind'], unique=False)
    op.create_index(op.f('ix_ai_agent_requirements_member_run_id'), 'ai_agent_requirements', ['member_run_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_requirements_requirement_id'), 'ai_agent_requirements', ['requirement_id'], unique=True)
    op.create_index(op.f('ix_ai_agent_requirements_run_id'), 'ai_agent_requirements', ['run_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_requirements_session_id'), 'ai_agent_requirements', ['session_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_requirements_status'), 'ai_agent_requirements', ['status'], unique=False)
    op.create_index(op.f('ix_ai_agent_requirements_tool_call_id'), 'ai_agent_requirements', ['tool_call_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_requirements_tool_name'), 'ai_agent_requirements', ['tool_name'], unique=False)
    op.create_table('ai_agent_run_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.String(length=128), nullable=False),
    sa.Column('run_id', sa.String(length=128), nullable=False),
    sa.Column('event_index', sa.Integer(), nullable=False),
    sa.Column('event', sa.String(length=128), nullable=False),
    sa.Column('payload_json', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['ai_agent_runs.run_id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['ai_agent_sessions.session_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'event_index', name='uq_ai_agent_run_events_run_index')
    )
    op.create_index(op.f('ix_ai_agent_run_events_event'), 'ai_agent_run_events', ['event'], unique=False)
    op.create_index(op.f('ix_ai_agent_run_events_run_id'), 'ai_agent_run_events', ['run_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_run_events_session_id'), 'ai_agent_run_events', ['session_id'], unique=False)
    op.create_table('ai_agent_tool_calls',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.String(length=128), nullable=False),
    sa.Column('run_id', sa.String(length=128), nullable=False),
    sa.Column('member_run_id', sa.String(length=128), nullable=True),
    sa.Column('tool_call_id', sa.String(length=255), nullable=True),
    sa.Column('tool_name', sa.String(length=128), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('risk_level', sa.String(length=32), nullable=True),
    sa.Column('input_payload_json', sa.JSON(), nullable=True),
    sa.Column('output_payload_json', sa.JSON(), nullable=True),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['ai_agent_runs.run_id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['ai_agent_sessions.session_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'tool_call_id', name='uq_ai_agent_tool_calls_run_tool_call')
    )
    op.create_index(op.f('ix_ai_agent_tool_calls_member_run_id'), 'ai_agent_tool_calls', ['member_run_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_tool_calls_run_id'), 'ai_agent_tool_calls', ['run_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_tool_calls_session_id'), 'ai_agent_tool_calls', ['session_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_tool_calls_status'), 'ai_agent_tool_calls', ['status'], unique=False)
    op.create_index(op.f('ix_ai_agent_tool_calls_tool_call_id'), 'ai_agent_tool_calls', ['tool_call_id'], unique=False)
    op.create_index(op.f('ix_ai_agent_tool_calls_tool_name'), 'ai_agent_tool_calls', ['tool_name'], unique=False)
    # ### Alembic 自动生成命令结束。 ###


def _20260626_0111_downgrade() -> None:
    """删除基线创建的全部对象，用于回滚空库初始化。"""
    # ### Alembic 自动生成命令，作为发布基线保留。 ###
    op.drop_index(op.f('ix_ai_agent_tool_calls_tool_name'), table_name='ai_agent_tool_calls')
    op.drop_index(op.f('ix_ai_agent_tool_calls_tool_call_id'), table_name='ai_agent_tool_calls')
    op.drop_index(op.f('ix_ai_agent_tool_calls_status'), table_name='ai_agent_tool_calls')
    op.drop_index(op.f('ix_ai_agent_tool_calls_session_id'), table_name='ai_agent_tool_calls')
    op.drop_index(op.f('ix_ai_agent_tool_calls_run_id'), table_name='ai_agent_tool_calls')
    op.drop_index(op.f('ix_ai_agent_tool_calls_member_run_id'), table_name='ai_agent_tool_calls')
    op.drop_table('ai_agent_tool_calls')
    op.drop_index(op.f('ix_ai_agent_run_events_session_id'), table_name='ai_agent_run_events')
    op.drop_index(op.f('ix_ai_agent_run_events_run_id'), table_name='ai_agent_run_events')
    op.drop_index(op.f('ix_ai_agent_run_events_event'), table_name='ai_agent_run_events')
    op.drop_table('ai_agent_run_events')
    op.drop_index(op.f('ix_ai_agent_requirements_tool_name'), table_name='ai_agent_requirements')
    op.drop_index(op.f('ix_ai_agent_requirements_tool_call_id'), table_name='ai_agent_requirements')
    op.drop_index(op.f('ix_ai_agent_requirements_status'), table_name='ai_agent_requirements')
    op.drop_index(op.f('ix_ai_agent_requirements_session_id'), table_name='ai_agent_requirements')
    op.drop_index(op.f('ix_ai_agent_requirements_run_id'), table_name='ai_agent_requirements')
    op.drop_index(op.f('ix_ai_agent_requirements_requirement_id'), table_name='ai_agent_requirements')
    op.drop_index(op.f('ix_ai_agent_requirements_member_run_id'), table_name='ai_agent_requirements')
    op.drop_index(op.f('ix_ai_agent_requirements_kind'), table_name='ai_agent_requirements')
    op.drop_table('ai_agent_requirements')
    op.drop_index(op.f('ix_ai_agent_messages_session_id'), table_name='ai_agent_messages')
    op.drop_index(op.f('ix_ai_agent_messages_run_id'), table_name='ai_agent_messages')
    op.drop_index(op.f('ix_ai_agent_messages_role'), table_name='ai_agent_messages')
    op.drop_table('ai_agent_messages')
    op.drop_index(op.f('ix_ai_agent_member_runs_status'), table_name='ai_agent_member_runs')
    op.drop_index(op.f('ix_ai_agent_member_runs_session_id'), table_name='ai_agent_member_runs')
    op.drop_index(op.f('ix_ai_agent_member_runs_parent_run_id'), table_name='ai_agent_member_runs')
    op.drop_index(op.f('ix_ai_agent_member_runs_delegate_tool_call_id'), table_name='ai_agent_member_runs')
    op.drop_index(op.f('ix_ai_agent_member_runs_agent_id'), table_name='ai_agent_member_runs')
    op.drop_table('ai_agent_member_runs')
    op.drop_index(op.f('ix_page_version_component_usages_project_id'), table_name='page_version_component_usages')
    op.drop_index(op.f('ix_page_version_component_usages_page_version_id'), table_name='page_version_component_usages')
    op.drop_index(op.f('ix_page_version_component_usages_page_id'), table_name='page_version_component_usages')
    op.drop_table('page_version_component_usages')
    op.drop_index(op.f('ix_page_version_component_resources_project_id'), table_name='page_version_component_resources')
    op.drop_index(op.f('ix_page_version_component_resources_page_version_id'), table_name='page_version_component_resources')
    op.drop_index(op.f('ix_page_version_component_resources_page_id'), table_name='page_version_component_resources')
    op.drop_table('page_version_component_resources')
    op.drop_index('ix_pvcd_pver_id', table_name='page_version_component_dependencies')
    op.drop_index('ix_pvcd_page_id', table_name='page_version_component_dependencies')
    op.drop_index('ix_pvcd_cver_id', table_name='page_version_component_dependencies')
    op.drop_index('ix_pvcd_comp_id', table_name='page_version_component_dependencies')
    op.drop_table('page_version_component_dependencies')
    op.drop_index(op.f('ix_ai_agent_runs_workspace_id'), table_name='ai_agent_runs')
    op.drop_index(op.f('ix_ai_agent_runs_user_id'), table_name='ai_agent_runs')
    op.drop_index(op.f('ix_ai_agent_runs_status'), table_name='ai_agent_runs')
    op.drop_index(op.f('ix_ai_agent_runs_source'), table_name='ai_agent_runs')
    op.drop_index(op.f('ix_ai_agent_runs_session_id'), table_name='ai_agent_runs')
    op.drop_index(op.f('ix_ai_agent_runs_scope_type'), table_name='ai_agent_runs')
    op.drop_index(op.f('ix_ai_agent_runs_project_id'), table_name='ai_agent_runs')
    op.drop_index(op.f('ix_ai_agent_runs_page_id'), table_name='ai_agent_runs')
    op.drop_index(op.f('ix_ai_agent_runs_component_id'), table_name='ai_agent_runs')
    op.drop_index(op.f('ix_ai_agent_runs_agent_id'), table_name='ai_agent_runs')
    op.drop_table('ai_agent_runs')
    op.drop_index(op.f('ix_workspace_themes_workspace_id'), table_name='workspace_themes')
    op.drop_index(op.f('ix_workspace_themes_project_icon_asset_id'), table_name='workspace_themes')
    op.drop_index(op.f('ix_workspace_themes_logo_asset_id'), table_name='workspace_themes')
    op.drop_index(op.f('ix_workspace_themes_invert_logo_asset_id'), table_name='workspace_themes')
    op.drop_index(op.f('ix_workspace_themes_heading_font_id'), table_name='workspace_themes')
    op.drop_index(op.f('ix_workspace_themes_code_font_id'), table_name='workspace_themes')
    op.drop_index(op.f('ix_workspace_themes_body_font_id'), table_name='workspace_themes')
    op.drop_table('workspace_themes')
    op.drop_index(op.f('ix_release_modules_release_id'), table_name='release_modules')
    op.drop_table('release_modules')
    op.drop_index(op.f('ix_project_routes_project_id'), table_name='project_routes')
    op.drop_index(op.f('ix_project_routes_parent_id'), table_name='project_routes')
    op.drop_index(op.f('ix_project_routes_page_id'), table_name='project_routes')
    op.drop_table('project_routes')
    op.drop_index(op.f('ix_project_build_jobs_status'), table_name='project_build_jobs')
    op.drop_index(op.f('ix_project_build_jobs_snapshot_release_id'), table_name='project_build_jobs')
    op.drop_index(op.f('ix_project_build_jobs_project_id'), table_name='project_build_jobs')
    op.drop_table('project_build_jobs')
    op.drop_index(op.f('ix_page_versions_page_id'), table_name='page_versions')
    op.drop_table('page_versions')
    op.drop_index(op.f('ix_page_screenshot_jobs_workspace_id'), table_name='page_screenshot_jobs')
    op.drop_index(op.f('ix_page_screenshot_jobs_status'), table_name='page_screenshot_jobs')
    op.drop_index(op.f('ix_page_screenshot_jobs_source'), table_name='page_screenshot_jobs')
    op.drop_index(op.f('ix_page_screenshot_jobs_project_id'), table_name='page_screenshot_jobs')
    op.drop_index(op.f('ix_page_screenshot_jobs_page_id'), table_name='page_screenshot_jobs')
    op.drop_index(op.f('ix_page_screenshot_jobs_job_group_id'), table_name='page_screenshot_jobs')
    op.drop_index(op.f('ix_page_screenshot_jobs_config_hash'), table_name='page_screenshot_jobs')
    op.drop_index('ix_page_screenshot_jobs_dedupe_active', table_name='page_screenshot_jobs')
    op.drop_table('page_screenshot_jobs')
    op.drop_index('ix_cvcr_workspace_id', table_name='component_version_component_resources')
    op.drop_index('ix_cvcr_workspace_component_resource', table_name='component_version_component_resources')
    op.drop_index('ix_cvcr_component_version_id', table_name='component_version_component_resources')
    op.drop_index('ix_cvcr_component_id', table_name='component_version_component_resources')
    op.drop_table('component_version_component_resources')
    op.drop_index('ix_cvcd_dep_cver_id', table_name='component_version_component_dependencies')
    op.drop_index('ix_cvcd_dep_comp_id', table_name='component_version_component_dependencies')
    op.drop_index('ix_cvcd_cver_id', table_name='component_version_component_dependencies')
    op.drop_index('ix_cvcd_comp_id', table_name='component_version_component_dependencies')
    op.drop_table('component_version_component_dependencies')
    op.drop_index('uq_ai_llm_slot_bindings_personal_user_slot', table_name='ai_llm_slot_bindings', sqlite_where=sa.text("scope = 'personal'"), postgresql_where=sa.text("scope = 'personal'"))
    op.drop_index('uq_ai_llm_slot_bindings_global_slot', table_name='ai_llm_slot_bindings', sqlite_where=sa.text("scope = 'global'"), postgresql_where=sa.text("scope = 'global'"))
    op.drop_index(op.f('ix_ai_llm_slot_bindings_user_id'), table_name='ai_llm_slot_bindings')
    op.drop_index(op.f('ix_ai_llm_slot_bindings_scope'), table_name='ai_llm_slot_bindings')
    op.drop_index(op.f('ix_ai_llm_slot_bindings_llm_config_id'), table_name='ai_llm_slot_bindings')
    op.drop_table('ai_llm_slot_bindings')
    op.drop_index(op.f('ix_ai_agent_sessions_workspace_id'), table_name='ai_agent_sessions')
    op.drop_index(op.f('ix_ai_agent_sessions_user_id'), table_name='ai_agent_sessions')
    op.drop_index(op.f('ix_ai_agent_sessions_source'), table_name='ai_agent_sessions')
    op.drop_index(op.f('ix_ai_agent_sessions_scope_type'), table_name='ai_agent_sessions')
    op.drop_index(op.f('ix_ai_agent_sessions_project_id'), table_name='ai_agent_sessions')
    op.drop_index(op.f('ix_ai_agent_sessions_page_id'), table_name='ai_agent_sessions')
    op.drop_index(op.f('ix_ai_agent_sessions_deleted_at'), table_name='ai_agent_sessions')
    op.drop_index(op.f('ix_ai_agent_sessions_component_id'), table_name='ai_agent_sessions')
    op.drop_index(op.f('ix_ai_agent_sessions_agent_id'), table_name='ai_agent_sessions')
    op.drop_table('ai_agent_sessions')
    op.drop_index(op.f('ix_workspace_style_suggested_components_style_id'), table_name='workspace_style_suggested_components')
    op.drop_index(op.f('ix_workspace_style_suggested_components_component_id'), table_name='workspace_style_suggested_components')
    op.drop_table('workspace_style_suggested_components')
    op.drop_index(op.f('ix_workspace_font_configs_workspace_id'), table_name='workspace_font_configs')
    op.drop_index(op.f('ix_workspace_font_configs_asset_id'), table_name='workspace_font_configs')
    op.drop_table('workspace_font_configs')
    op.drop_index(op.f('ix_workspace_component_versions_component_id'), table_name='workspace_component_versions')
    op.drop_index('ix_workspace_component_versions_component_fingerprint', table_name='workspace_component_versions')
    op.drop_table('workspace_component_versions')
    op.drop_index(op.f('ix_releases_tenant_id'), table_name='releases')
    op.drop_index(op.f('ix_releases_project_id'), table_name='releases')
    op.drop_table('releases')
    op.drop_index(op.f('ix_project_suggested_reference_assets_project_id'), table_name='project_suggested_reference_assets')
    op.drop_index(op.f('ix_project_suggested_reference_assets_asset_id'), table_name='project_suggested_reference_assets')
    op.drop_table('project_suggested_reference_assets')
    op.drop_index(op.f('ix_project_suggested_components_project_id'), table_name='project_suggested_components')
    op.drop_index(op.f('ix_project_suggested_components_component_id'), table_name='project_suggested_components')
    op.drop_table('project_suggested_components')
    op.drop_index(op.f('ix_pages_workspace_id'), table_name='pages')
    op.drop_index(op.f('ix_pages_project_id'), table_name='pages')
    op.drop_table('pages')
    op.drop_index(op.f('ix_ai_llm_configs_user_id'), table_name='ai_llm_configs')
    op.drop_index(op.f('ix_ai_llm_configs_status'), table_name='ai_llm_configs')
    op.drop_index(op.f('ix_ai_llm_configs_scope'), table_name='ai_llm_configs')
    op.drop_index(op.f('ix_ai_llm_configs_provider_config_id'), table_name='ai_llm_configs')
    op.drop_table('ai_llm_configs')
    op.drop_index(op.f('ix_ai_agent_image_attachments_workspace_id'), table_name='ai_agent_image_attachments')
    op.drop_index(op.f('ix_ai_agent_image_attachments_user_id'), table_name='ai_agent_image_attachments')
    op.drop_index(op.f('ix_ai_agent_image_attachments_tool_name'), table_name='ai_agent_image_attachments')
    op.drop_index(op.f('ix_ai_agent_image_attachments_tool_call_id'), table_name='ai_agent_image_attachments')
    op.drop_index(op.f('ix_ai_agent_image_attachments_status'), table_name='ai_agent_image_attachments')
    op.drop_index(op.f('ix_ai_agent_image_attachments_source_kind'), table_name='ai_agent_image_attachments')
    op.drop_index(op.f('ix_ai_agent_image_attachments_sha256'), table_name='ai_agent_image_attachments')
    op.drop_index(op.f('ix_ai_agent_image_attachments_session_id'), table_name='ai_agent_image_attachments')
    op.drop_index(op.f('ix_ai_agent_image_attachments_run_id'), table_name='ai_agent_image_attachments')
    op.drop_index(op.f('ix_ai_agent_image_attachments_promoted_asset_id'), table_name='ai_agent_image_attachments')
    op.drop_table('ai_agent_image_attachments')
    op.drop_index(op.f('ix_workspace_styles_workspace_id'), table_name='workspace_styles')
    op.drop_table('workspace_styles')
    op.drop_index(op.f('ix_workspace_members_workspace_id'), table_name='workspace_members')
    op.drop_index(op.f('ix_workspace_members_user_id'), table_name='workspace_members')
    op.drop_index(op.f('ix_workspace_members_status'), table_name='workspace_members')
    op.drop_table('workspace_members')
    op.drop_index(op.f('ix_workspace_components_workspace_id'), table_name='workspace_components')
    op.drop_index(op.f('ix_workspace_components_component_type'), table_name='workspace_components')
    op.drop_table('workspace_components')
    op.drop_index(op.f('ix_workspace_assets_workspace_id'), table_name='workspace_assets')
    op.drop_index(op.f('ix_workspace_assets_status'), table_name='workspace_assets')
    op.drop_index(op.f('ix_workspace_assets_source_asset_id'), table_name='workspace_assets')
    op.drop_index(op.f('ix_workspace_assets_file_hash'), table_name='workspace_assets')
    op.drop_table('workspace_assets')
    op.drop_table('user_sessions')
    op.drop_index(op.f('ix_projects_workspace_id'), table_name='projects')
    op.drop_table('projects')
    op.drop_index(op.f('ix_ai_llm_provider_configs_user_id'), table_name='ai_llm_provider_configs')
    op.drop_index(op.f('ix_ai_llm_provider_configs_status'), table_name='ai_llm_provider_configs')
    op.drop_index(op.f('ix_ai_llm_provider_configs_scope'), table_name='ai_llm_provider_configs')
    op.drop_index(op.f('ix_ai_llm_provider_configs_provider_key'), table_name='ai_llm_provider_configs')
    op.drop_table('ai_llm_provider_configs')
    op.drop_index(op.f('ix_ai_agent_user_configs_user_id'), table_name='ai_agent_user_configs')
    op.drop_index(op.f('ix_ai_agent_user_configs_agent_id'), table_name='ai_agent_user_configs')
    op.drop_table('ai_agent_user_configs')
    op.drop_index(op.f('ix_ai_agent_tool_user_configs_user_id'), table_name='ai_agent_tool_user_configs')
    op.drop_index(op.f('ix_ai_agent_tool_user_configs_tool_key'), table_name='ai_agent_tool_user_configs')
    op.drop_index(op.f('ix_ai_agent_tool_user_configs_agent_id'), table_name='ai_agent_tool_user_configs')
    op.drop_table('ai_agent_tool_user_configs')
    op.drop_table('workspaces')
    op.drop_table('users')
    # ### Alembic 自动生成命令结束。 ###

# ---- 原迁移 20260701_0100 ----

def _20260701_0100_upgrade() -> None:
    """创建资源渲染提示回填任务表。"""

    op.create_table(
        "asset_render_hint_backfill_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_group_id", sa.String(length=64), nullable=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("asset_type", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("overwrite_manual", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("current_render_metadata", sa.JSON(), nullable=True),
        sa.Column("next_render_metadata", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["workspace_assets.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_asset_render_hint_backfill_jobs_asset_id", "asset_render_hint_backfill_jobs", ["asset_id"])
    op.create_index("ix_asset_render_hint_backfill_jobs_asset_type", "asset_render_hint_backfill_jobs", ["asset_type"])
    op.create_index(
        "ix_asset_render_hint_backfill_jobs_dedupe_active",
        "asset_render_hint_backfill_jobs",
        ["asset_id", "mode", "overwrite_manual", "status"],
    )
    op.create_index("ix_asset_render_hint_backfill_jobs_job_group_id", "asset_render_hint_backfill_jobs", ["job_group_id"])
    op.create_index("ix_asset_render_hint_backfill_jobs_mode", "asset_render_hint_backfill_jobs", ["mode"])
    op.create_index("ix_asset_render_hint_backfill_jobs_source", "asset_render_hint_backfill_jobs", ["source"])
    op.create_index("ix_asset_render_hint_backfill_jobs_status", "asset_render_hint_backfill_jobs", ["status"])
    op.create_index("ix_asset_render_hint_backfill_jobs_workspace_id", "asset_render_hint_backfill_jobs", ["workspace_id"])


def _20260701_0100_downgrade() -> None:
    """删除资源渲染提示回填任务表。"""

    op.drop_index("ix_asset_render_hint_backfill_jobs_workspace_id", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_status", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_source", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_mode", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_job_group_id", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_dedupe_active", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_asset_type", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_asset_id", table_name="asset_render_hint_backfill_jobs")
    op.drop_table("asset_render_hint_backfill_jobs")

# ---- 原迁移 20260712_0500 ----

def _add_page_screenshot_job_leases() -> None:
    """增加截图任务租约、取消字段和可复用的任务组成员关系。"""

    op.add_column("page_screenshot_jobs", sa.Column("worker_id", sa.String(length=128), nullable=True))
    op.add_column("page_screenshot_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("page_screenshot_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("page_screenshot_jobs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_page_screenshot_jobs_worker_id", "page_screenshot_jobs", ["worker_id"])
    op.create_index("ix_page_screenshot_jobs_lease_expires_at", "page_screenshot_jobs", ["lease_expires_at"])

    op.create_table(
        "page_screenshot_job_groups",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_page_screenshot_job_groups_workspace_id", "page_screenshot_job_groups", ["workspace_id"])
    op.create_index("ix_page_screenshot_job_groups_project_id", "page_screenshot_job_groups", ["project_id"])
    op.create_table(
        "page_screenshot_job_group_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["page_screenshot_job_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["page_screenshot_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "job_id", name="uq_page_screenshot_job_group_items_group_job"),
    )
    op.create_index("ix_page_screenshot_job_group_items_group_id", "page_screenshot_job_group_items", ["group_id"])
    op.create_index("ix_page_screenshot_job_group_items_job_id", "page_screenshot_job_group_items", ["job_id"])

    op.execute(
        sa.text(
            """
            INSERT INTO page_screenshot_job_groups
                (id, source, workspace_id, project_id, created_by, created_at, updated_at)
            SELECT
                job_group_id,
                MIN(source),
                MIN(workspace_id),
                MIN(project_id),
                MIN(created_by),
                MIN(created_at),
                MAX(updated_at)
            FROM page_screenshot_jobs
            WHERE job_group_id IS NOT NULL
            GROUP BY job_group_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO page_screenshot_job_group_items (group_id, job_id, created_at)
            SELECT job_group_id, id, created_at
            FROM page_screenshot_jobs
            WHERE job_group_id IS NOT NULL
            """
        )
    )

    # 旧版本没有数据库租约；升级后的 running 任务应由新恢复逻辑安全重排。
    op.execute(
        sa.text(
            """
            UPDATE page_screenshot_jobs
            SET lease_expires_at = CURRENT_TIMESTAMP
            WHERE status = 'running'
            """
        )
    )

    # 建立活动任务唯一索引前，先收敛历史上可能已经重复的 pending/running 记录。
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY page_id, config_hash, viewport_width, viewport_height
                        ORDER BY created_at ASC, id ASC
                    ) AS row_no
                FROM page_screenshot_jobs
                WHERE status IN ('pending', 'running')
            )
            UPDATE page_screenshot_jobs
            SET
                status = 'failed',
                error_code = 'PAGE_SCREENSHOT_JOB_DEDUPED',
                error_message = '升级时合并了重复的活动截图任务。',
                finished_at = CURRENT_TIMESTAMP,
                lease_expires_at = NULL,
                heartbeat_at = NULL
            WHERE id IN (SELECT id FROM ranked WHERE row_no > 1)
            """
        )
    )
    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "config_hash", "viewport_width", "viewport_height"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def _create_ai_page_mutation_jobs() -> None:
    """创建带租约代次的 AI 页面变更批次、任务及相关索引。"""

    op.create_table(
        "ai_page_mutation_batches",
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("run_step", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requirement_id", sa.String(length=128), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_generation", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.PrimaryKeyConstraint("batch_id"),
        sa.UniqueConstraint("run_id", "run_step", name="uq_ai_page_mutation_batches_run_step"),
    )
    for column in ("run_id", "session_id", "status", "requirement_id", "worker_id", "lease_expires_at"):
        op.create_index(f"ix_ai_page_mutation_batches_{column}", "ai_page_mutation_batches", [column])

    op.create_table(
        "ai_page_mutation_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("tool_call_id", sa.String(length=255), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("base_version_no", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["ai_page_mutation_batches.batch_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "tool_call_id", name="uq_ai_page_mutation_jobs_run_tool_call"),
    )
    for column in (
        "job_id", "batch_id", "run_id", "session_id", "tool_call_id", "operation", "workspace_id",
        "project_id", "page_id", "status", "worker_id", "lease_expires_at",
    ):
        # ORM 为 job_id 声明了 unique=True 与 index=True；迁移保持相同的命名唯一索引结构。
        op.create_index(
            f"ix_ai_page_mutation_jobs_{column}",
            "ai_page_mutation_jobs",
            [column],
            unique=column == "job_id",
        )


def _add_page_screenshot_job_snapshot() -> None:
    """固化截图任务目标页面版本，并扩展活动任务的去重范围。"""

    op.add_column("page_screenshot_jobs", sa.Column("target_page_version_no", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE page_screenshot_jobs
            SET target_page_version_no = COALESCE(
                (
                    SELECT pages.current_version_no
                    FROM pages
                    WHERE pages.id = page_screenshot_jobs.page_id
                ),
                1
            )
            WHERE target_page_version_no IS NULL
            """
        )
    )
    with op.batch_alter_table("page_screenshot_jobs") as batch_op:
        batch_op.alter_column("target_page_version_no", existing_type=sa.Integer(), nullable=False)

    op.create_index(
        "ix_page_screenshot_jobs_target_page_version_no",
        "page_screenshot_jobs",
        ["target_page_version_no"],
    )
    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "target_page_version_no", "config_hash", "viewport_width", "viewport_height"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def _20260712_0500_upgrade() -> None:
    """一次性升级截图任务、AI 页面变更任务和页面截图指针结构。"""

    _add_page_screenshot_job_leases()
    _create_ai_page_mutation_jobs()
    _add_page_screenshot_job_snapshot()
    op.add_column("pages", sa.Column("screenshot_viewport_width", sa.Integer(), nullable=True))
    op.add_column("pages", sa.Column("screenshot_viewport_height", sa.Integer(), nullable=True))


def _20260712_0500_downgrade() -> None:
    """完整移除本次合并迁移新增的表、索引和字段。"""

    op.drop_column("pages", "screenshot_viewport_height")
    op.drop_column("pages", "screenshot_viewport_width")

    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "config_hash", "viewport_width", "viewport_height"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.drop_index("ix_page_screenshot_jobs_target_page_version_no", table_name="page_screenshot_jobs")
    with op.batch_alter_table("page_screenshot_jobs") as batch_op:
        batch_op.drop_column("target_page_version_no")

    op.drop_table("ai_page_mutation_jobs")
    op.drop_table("ai_page_mutation_batches")

    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "config_hash", "viewport_width", "viewport_height", "status"],
    )
    op.drop_index("ix_page_screenshot_job_group_items_job_id", table_name="page_screenshot_job_group_items")
    op.drop_index("ix_page_screenshot_job_group_items_group_id", table_name="page_screenshot_job_group_items")
    op.drop_table("page_screenshot_job_group_items")
    op.drop_index("ix_page_screenshot_job_groups_project_id", table_name="page_screenshot_job_groups")
    op.drop_index("ix_page_screenshot_job_groups_workspace_id", table_name="page_screenshot_job_groups")
    op.drop_table("page_screenshot_job_groups")
    op.drop_index("ix_page_screenshot_jobs_lease_expires_at", table_name="page_screenshot_jobs")
    op.drop_index("ix_page_screenshot_jobs_worker_id", table_name="page_screenshot_jobs")
    op.drop_column("page_screenshot_jobs", "cancel_requested_at")
    op.drop_column("page_screenshot_jobs", "heartbeat_at")
    op.drop_column("page_screenshot_jobs", "lease_expires_at")
    op.drop_column("page_screenshot_jobs", "worker_id")

# ---- 原迁移 20260720_0100 ----

def _20260720_0100_upgrade() -> None:
    """升级视觉模型配置与图片任务结构。"""

    op.add_column(
        "ai_llm_configs",
        sa.Column("model_type", sa.String(length=32), server_default="chat", nullable=False),
    )
    op.create_index("ix_ai_llm_configs_model_type", "ai_llm_configs", ["model_type"])
    op.add_column("ai_agent_image_attachments", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("ai_agent_image_attachments", sa.Column("height", sa.Integer(), nullable=True))

    op.create_table(
        "ai_image_generation_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("tool_call_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("model_config_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("model_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress_json", sa.JSON(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("continued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["model_config_id"], ["ai_llm_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "tool_call_id", name="uq_ai_image_generation_jobs_run_tool_call"),
    )
    for column in (
        "job_id", "run_id", "session_id", "tool_call_id", "user_id", "workspace_id",
        "project_id", "model_config_id", "operation", "status", "worker_id", "lease_expires_at", "continued_at",
    ):
        op.create_index(
            f"ix_ai_image_generation_jobs_{column}",
            "ai_image_generation_jobs",
            [column],
            unique=column == "job_id",
        )


def _20260720_0100_downgrade() -> None:
    """移除视觉模型配置与图片任务结构。"""

    op.drop_table("ai_image_generation_jobs")
    op.drop_column("ai_agent_image_attachments", "height")
    op.drop_column("ai_agent_image_attachments", "width")
    op.drop_index("ix_ai_llm_configs_model_type", table_name="ai_llm_configs")
    op.drop_column("ai_llm_configs", "model_type")

# ---- 原迁移 20260721_0100 ----

def _20260721_0100_upgrade() -> None:
    """增加外部任务标识、状态、轮询时间和安全供应商元数据。"""

    op.add_column("ai_image_generation_jobs", sa.Column("provider_task_id", sa.String(length=255), nullable=True))
    op.add_column("ai_image_generation_jobs", sa.Column("provider_status", sa.String(length=64), nullable=True))
    op.add_column("ai_image_generation_jobs", sa.Column("provider_request_id", sa.String(length=255), nullable=True))
    op.add_column("ai_image_generation_jobs", sa.Column("provider_state_json", sa.JSON(), nullable=True))
    op.add_column("ai_image_generation_jobs", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_image_generation_jobs", sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_ai_image_generation_jobs_provider_task_id", "ai_image_generation_jobs", ["provider_task_id"])
    op.create_index("ix_ai_image_generation_jobs_provider_status", "ai_image_generation_jobs", ["provider_status"])
    op.create_index("ix_ai_image_generation_jobs_next_poll_at", "ai_image_generation_jobs", ["next_poll_at"])


def _20260721_0100_downgrade() -> None:
    """移除外部供应商任务状态字段。"""

    op.drop_index("ix_ai_image_generation_jobs_next_poll_at", table_name="ai_image_generation_jobs")
    op.drop_index("ix_ai_image_generation_jobs_provider_status", table_name="ai_image_generation_jobs")
    op.drop_index("ix_ai_image_generation_jobs_provider_task_id", table_name="ai_image_generation_jobs")
    op.drop_column("ai_image_generation_jobs", "next_poll_at")
    op.drop_column("ai_image_generation_jobs", "submitted_at")
    op.drop_column("ai_image_generation_jobs", "provider_state_json")
    op.drop_column("ai_image_generation_jobs", "provider_request_id")
    op.drop_column("ai_image_generation_jobs", "provider_status")
    op.drop_column("ai_image_generation_jobs", "provider_task_id")

# ---- 原迁移 20260723_0100 ----

def _20260723_0100_upgrade() -> None:
    """增加 deferred 原始调用和可选成员运行关联。"""

    op.add_column("ai_image_generation_jobs", sa.Column("deferred_tool_call_id", sa.String(length=255), nullable=True))
    op.add_column("ai_image_generation_jobs", sa.Column("member_run_id", sa.String(length=128), nullable=True))
    op.execute("UPDATE ai_image_generation_jobs SET deferred_tool_call_id = tool_call_id")
    with op.batch_alter_table("ai_image_generation_jobs") as batch_op:
        batch_op.alter_column("deferred_tool_call_id", nullable=False)
        batch_op.create_foreign_key(
            "fk_ai_image_generation_jobs_member_run_id",
            "ai_agent_member_runs",
            ["member_run_id"],
            ["member_run_id"],
        )
    op.create_index(
        "ix_ai_image_generation_jobs_deferred_tool_call_id",
        "ai_image_generation_jobs",
        ["deferred_tool_call_id"],
    )
    op.create_index("ix_ai_image_generation_jobs_member_run_id", "ai_image_generation_jobs", ["member_run_id"])


def _20260723_0100_downgrade() -> None:
    """移除成员图片生成调用关联。"""

    op.drop_index("ix_ai_image_generation_jobs_member_run_id", table_name="ai_image_generation_jobs")
    op.drop_index("ix_ai_image_generation_jobs_deferred_tool_call_id", table_name="ai_image_generation_jobs")
    with op.batch_alter_table("ai_image_generation_jobs") as batch_op:
        batch_op.drop_constraint("fk_ai_image_generation_jobs_member_run_id", type_="foreignkey")
        batch_op.drop_column("member_run_id")
        batch_op.drop_column("deferred_tool_call_id")

# ---- 原迁移 20260728_0100 ----

def _20260728_0100_upgrade() -> None:
    """增加 run 级模型标识和运行参数快照。"""

    op.add_column("ai_agent_runs", sa.Column("llm_config_id", sa.Integer(), nullable=True))
    op.add_column("ai_agent_runs", sa.Column("llm_config_snapshot_json", sa.JSON(), nullable=True))
    op.create_index("ix_ai_agent_runs_llm_config_id", "ai_agent_runs", ["llm_config_id"])


def _20260728_0100_downgrade() -> None:
    """移除 run 级模型信息。"""

    op.drop_index("ix_ai_agent_runs_llm_config_id", table_name="ai_agent_runs")
    op.drop_column("ai_agent_runs", "llm_config_snapshot_json")
    op.drop_column("ai_agent_runs", "llm_config_id")

# ---- 原迁移 20260730_0100 ----

def _20260730_0100_upgrade() -> None:
    """新建 workspace_font_families，回填 face.family_id 与主题 family 绑定，删除旧的 font_family 列与主题 face 外键。"""

    op.create_table(
        "workspace_font_families",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_workspace_font_families_workspace_name"),
    )
    op.create_index(op.f("ix_workspace_font_families_workspace_id"), "workspace_font_families", ["workspace_id"], unique=False)

    # 按 (workspace_id, lower(trim(font_family))) 去重建 family，名称取首条（最小 id）原值。
    op.execute(
        """
        INSERT INTO workspace_font_families (workspace_id, name, created_at, updated_at)
        SELECT c.workspace_id, c.font_family, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM workspace_font_configs c
        JOIN (
            SELECT workspace_id, lower(trim(font_family)) AS normalized_name, MIN(id) AS first_id
            FROM workspace_font_configs
            GROUP BY workspace_id, lower(trim(font_family))
        ) g ON g.first_id = c.id
        """
    )

    # face 回填 family_id：先加可空列，回填完成后再收紧为 NOT NULL。
    op.add_column("workspace_font_configs", sa.Column("family_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE workspace_font_configs
        SET family_id = (
            SELECT f.id
            FROM workspace_font_families f
            WHERE f.workspace_id = workspace_font_configs.workspace_id
              AND lower(trim(f.name)) = lower(trim(workspace_font_configs.font_family))
        )
        """
    )
    with op.batch_alter_table("workspace_font_configs") as batch_op:
        batch_op.alter_column("family_id", nullable=False, existing_type=sa.Integer())
        batch_op.create_foreign_key(
            "fk_workspace_font_configs_family_id",
            "workspace_font_families",
            ["family_id"],
            ["id"],
        )
        batch_op.create_unique_constraint(
            "uq_workspace_font_configs_family_face",
            ["family_id", "font_weight", "font_style"],
        )
        batch_op.drop_column("font_family")
    op.create_index(op.f("ix_workspace_font_configs_family_id"), "workspace_font_configs", ["family_id"], unique=False)

    # 主题槽位改绑 family：新列回填自原 face 外键映射，再删除旧列。
    op.add_column("workspace_themes", sa.Column("heading_font_family_id", sa.Integer(), nullable=True))
    op.add_column("workspace_themes", sa.Column("body_font_family_id", sa.Integer(), nullable=True))
    op.add_column("workspace_themes", sa.Column("code_font_family_id", sa.Integer(), nullable=True))
    for new_column, old_column in (
        ("heading_font_family_id", "heading_font_id"),
        ("body_font_family_id", "body_font_id"),
        ("code_font_family_id", "code_font_id"),
    ):
        op.execute(
            f"""
            UPDATE workspace_themes
            SET {new_column} = (
                SELECT c.family_id
                FROM workspace_font_configs c
                WHERE c.id = workspace_themes.{old_column}
            )
            """
        )
    op.drop_index(op.f("ix_workspace_themes_heading_font_id"), table_name="workspace_themes")
    op.drop_index(op.f("ix_workspace_themes_body_font_id"), table_name="workspace_themes")
    op.drop_index(op.f("ix_workspace_themes_code_font_id"), table_name="workspace_themes")
    with op.batch_alter_table("workspace_themes") as batch_op:
        batch_op.create_foreign_key(
            "fk_workspace_themes_heading_font_family_id",
            "workspace_font_families",
            ["heading_font_family_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_workspace_themes_body_font_family_id",
            "workspace_font_families",
            ["body_font_family_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_workspace_themes_code_font_family_id",
            "workspace_font_families",
            ["code_font_family_id"],
            ["id"],
        )
        batch_op.drop_column("heading_font_id")
        batch_op.drop_column("body_font_id")
        batch_op.drop_column("code_font_id")
    op.create_index(op.f("ix_workspace_themes_heading_font_family_id"), "workspace_themes", ["heading_font_family_id"], unique=False)
    op.create_index(op.f("ix_workspace_themes_body_font_family_id"), "workspace_themes", ["body_font_family_id"], unique=False)
    op.create_index(op.f("ix_workspace_themes_code_font_family_id"), "workspace_themes", ["code_font_family_id"], unique=False)


def _20260730_0100_downgrade() -> None:
    """恢复 face 扁平 font_family 列与主题的 face 外键绑定，并删除字体族表。"""

    # 主题恢复旧列：family 映射回该 family 下最早注册的 face。
    op.add_column("workspace_themes", sa.Column("heading_font_id", sa.Integer(), nullable=True))
    op.add_column("workspace_themes", sa.Column("body_font_id", sa.Integer(), nullable=True))
    op.add_column("workspace_themes", sa.Column("code_font_id", sa.Integer(), nullable=True))
    for old_column, new_column in (
        ("heading_font_id", "heading_font_family_id"),
        ("body_font_id", "body_font_family_id"),
        ("code_font_id", "code_font_family_id"),
    ):
        op.execute(
            f"""
            UPDATE workspace_themes
            SET {old_column} = (
                SELECT MIN(c.id)
                FROM workspace_font_configs c
                WHERE c.family_id = workspace_themes.{new_column}
            )
            """
        )
    op.drop_index(op.f("ix_workspace_themes_heading_font_family_id"), table_name="workspace_themes")
    op.drop_index(op.f("ix_workspace_themes_body_font_family_id"), table_name="workspace_themes")
    op.drop_index(op.f("ix_workspace_themes_code_font_family_id"), table_name="workspace_themes")
    with op.batch_alter_table("workspace_themes") as batch_op:
        batch_op.drop_constraint("fk_workspace_themes_heading_font_family_id", type_="foreignkey")
        batch_op.drop_constraint("fk_workspace_themes_body_font_family_id", type_="foreignkey")
        batch_op.drop_constraint("fk_workspace_themes_code_font_family_id", type_="foreignkey")
        batch_op.create_foreign_key(None, "workspace_font_configs", ["heading_font_id"], ["id"])
        batch_op.create_foreign_key(None, "workspace_font_configs", ["body_font_id"], ["id"])
        batch_op.create_foreign_key(None, "workspace_font_configs", ["code_font_id"], ["id"])
        batch_op.drop_column("heading_font_family_id")
        batch_op.drop_column("body_font_family_id")
        batch_op.drop_column("code_font_family_id")
    op.create_index(op.f("ix_workspace_themes_heading_font_id"), "workspace_themes", ["heading_font_id"], unique=False)
    op.create_index(op.f("ix_workspace_themes_body_font_id"), "workspace_themes", ["body_font_id"], unique=False)
    op.create_index(op.f("ix_workspace_themes_code_font_id"), "workspace_themes", ["code_font_id"], unique=False)

    # face 恢复扁平 font_family 字符串。
    op.add_column("workspace_font_configs", sa.Column("font_family", sa.String(length=255), nullable=True))
    op.execute(
        """
        UPDATE workspace_font_configs
        SET font_family = (
            SELECT f.name
            FROM workspace_font_families f
            WHERE f.id = workspace_font_configs.family_id
        )
        """
    )
    op.drop_index(op.f("ix_workspace_font_configs_family_id"), table_name="workspace_font_configs")
    with op.batch_alter_table("workspace_font_configs") as batch_op:
        batch_op.alter_column("font_family", nullable=False, existing_type=sa.String(length=255))
        batch_op.drop_constraint("uq_workspace_font_configs_family_face", type_="unique")
        batch_op.drop_constraint("fk_workspace_font_configs_family_id", type_="foreignkey")
        batch_op.drop_column("family_id")

    op.drop_index(op.f("ix_workspace_font_families_workspace_id"), table_name="workspace_font_families")
    op.drop_table("workspace_font_families")
