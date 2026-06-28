"""文件功能：创建当前发布数据库完整基线结构。

Revision ID: 20260626_0111
Revises:
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260626_0111'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
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
