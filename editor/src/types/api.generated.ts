/**
 * 文件功能：由 OpenAPI 生成的 Editor API 类型镜像（生成物，勿手改）。
 * 
 * 生成命令：pnpm run codegen:editor-api
 * 事实源：Backend /openapi.json → scripts/codegen/generate-editor-api-types.mjs
 */

/* eslint-disable */

/** 当前会话最近一次智能体运行状态。 */
export interface AgentActiveRunItem {
  "run_id": string
  "session_id": string
  "agent_id": string
  "status": "pending" | "running" | "paused" | "waiting_external" | "cancelling" | "completed" | "cancelled" | "failed"
  "focus": AgentScopeContext
  "work_scope_mode"?: "workspace" | "selected_projects"
  "allowed_project_ids"?: number[]
  "focus_version"?: number
  "pending_requirement"?: AgentPendingRequirement | null
  "content"?: string | null
  "created_at"?: string | null
  "updated_at"?: string | null
  "cancel_requested_at"?: string | null
  "event_index"?: number
  "llm"?: Record<string, unknown> | null
  "error_code"?: string | null
  "error_message"?: string | null
}

/** 中断一个仍在执行中的 run 的请求体。 */
export interface AgentCancelRunRequest {
  "force"?: boolean
  "tool_call_id"?: string | null
}

/** 返回给 Editor 的 run 中断结果。 */
export interface AgentCancelRunResponse {
  "run_id": string
  "session_id": string
  "cancel_requested"?: boolean
}

/** 内置智能体目录项，包含默认完整提示词与工具目录。 */
export interface AgentCatalogItem {
  "id": string
  "name": string
  "icon": string
  "summary": string
  "default_session_name": string
  "capabilities"?: string[]
  "scope_type": "workspace" | "project" | "page" | "component"
  "entry_kind"?: "agent" | "team"
  "llm_slot": string
  "default_description": string
  "description": string
  "description_override"?: string | null
  "description_customized"?: boolean
  "role": string
  "system_prompt": string
  "default_prompt": string
  "tool_groups"?: AgentToolGroupConfigItem[]
}

/** 返回某个 Agent 页面或组件代码规范的系统默认与当前生效内容。 */
export interface AgentCodeStandardConfigItem {
  "agent_id": string
  "standard_type": "page" | "component"
  "default_content": string
  "content": string
  "content_override"?: string | null
  "customized"?: boolean
  "source"?: "system_default" | "user_custom"
}

/** 更新某个 Agent 页面或组件代码规范的整类型 Markdown 覆盖。 */
export interface AgentCodeStandardUpdateRequest {
  "content_override"?: string | null
  "restore_default"?: boolean
}

/** 当前用户对某个智能体的有效配置。 */
export interface AgentConfigItem {
  "id": string
  "name": string
  "icon": string
  "summary": string
  "default_session_name": string
  "capabilities"?: string[]
  "scope_type": "workspace" | "project" | "page" | "component"
  "entry_kind"?: "agent" | "team"
  "llm_slot": string
  "default_description": string
  "description": string
  "description_override"?: string | null
  "description_customized"?: boolean
  "role": string
  "system_prompt": string
  "default_prompt": string
  "tool_groups"?: AgentToolGroupConfigItem[]
  "prompt_override"?: string | null
  "effective_prompt": string
  "prompt_customized"?: boolean
  "enabled_tool_count"?: number
  "disabled_tool_count"?: number
}

/** 更新智能体描述或完整提示词的请求。 */
export interface AgentConfigUpdateRequest {
  "description_override"?: string | null
  "prompt_override"?: string | null
  "restore_default"?: boolean
}

/** Agent 会话上下文预算、压缩状态与摘要详情。 */
export interface AgentContextStatusItem {
  "session_id": string
  "agent_id": string
  "compression_enabled": boolean
  "compression_required": boolean
  "compression_status"?: "idle" | "compressing" | "compressed" | "failed"
  "compression_method"?: "none" | "model" | "deterministic_fallback"
  "compression_error_message"?: string | null
  "summary_available": boolean
  "summary"?: string | null
  "topics"?: string[]
  "summary_updated_at"?: string | null
  "budget_policy_version": string
  "context_window_tokens": number
  "required_model_context_tokens": number
  "request_output_tokens": number
  "runtime_headroom_tokens": number
  "compression_trigger_tokens": number
  "max_output_tokens": number
  "history_token_ratio": number
  "compression_target_ratio": number
  "safety_margin_tokens": number
  "current_input_tokens": number
  "fixed_context_tokens": number
  "history_budget_tokens": number
  "compression_target_tokens": number
  "estimated_history_tokens": number
  "retained_recent_history_tokens": number
  "retained_recent_message_count": number
  "context_input_budget_tokens": number
  "context_used_tokens": number
  "context_remaining_tokens": number
  "last_input_tokens": number
  "last_output_tokens": number
  "last_total_tokens": number
  "last_reasoning_tokens": number
}

/** 继续一个已暂停 run 的请求体。 */
export interface AgentContinueRunRequest {
  "decision"?: "confirm" | "reject" | null
  "note"?: string | null
  "tool_execution"?: Record<string, unknown>
  "feedback_selections"?: (Record<string, unknown>)[]
}

/** 返回给 Editor 的 Agent 描述信息。 */
export interface AgentDescriptor {
  "id": string
  "name": string
  "icon": string
  "summary": string
  "default_session_name": string
  "capabilities"?: string[]
  "scope_type": "workspace" | "project" | "page" | "component"
  "entry_kind"?: "agent" | "team"
  "available"?: boolean
  "unavailable_reason"?: string | null
  "llm_slot"?: string | null
  "llm_binding_ready"?: boolean
  "bound_llm_name"?: string | null
  "bound_provider_label"?: string | null
  "supports_image_input"?: boolean
  "image_analysis_available"?: boolean
  "image_analysis_unavailable_reason"?: string | null
  "image_generation_available"?: boolean
  "image_generation_unavailable_reason"?: string | null
  "prompt_customized"?: boolean
  "enabled_tool_count"?: number
  "disabled_tool_count"?: number
  "scope": AgentScopeContext
}

/** 描述 Editor 当前路由提供给下一次 Run 的候选焦点。 */
export interface AgentFocusRequest {
  "scope_type"?: "workspace" | "project" | "page" | "component"
  "project_id"?: number | null
  "page_id"?: number | null
  "component_id"?: number | null
  "source"?: string
}

/** 返回给 Editor 的会话图片附件信息。 */
export interface AgentImageAttachmentItem {
  "id": number
  "session_id": string
  "source_kind"?: "user_upload" | "tool_output"
  "original_name": string
  "content_type": string
  "file_size": number
  "width"?: number | null
  "height"?: number | null
  "sha256": string
  "url": string
  "preview_available"?: boolean
  "promoted_asset_id"?: number | null
  "promotion_status"?: "never" | "promoted" | "deleted"
  "status": string
  "created_at"?: string | null
}

/** 将会话图片附件保存为工作空间资源的请求体。 */
export interface AgentImageAttachmentPromoteRequest {
  "name"?: string | null
  "description"?: string | null
  "tags"?: string[]
  "overwrite"?: boolean
}

/** 会话历史消息中展示的图片附件摘要。 */
export interface AgentMessageAttachmentItem {
  "id": number
  "source_kind"?: "user_upload" | "tool_output"
  "original_name": string
  "content_type": string
  "file_size": number
  "width"?: number | null
  "height"?: number | null
  "url": string
  "preview_available"?: boolean
  "promoted_asset_id"?: number | null
  "promotion_status"?: "never" | "promoted" | "deleted"
}

/** Agent 会话消息项，统一给 Editor 渲染消息流。 */
export interface AgentMessageItem {
  "id": string
  "run_id"?: string | null
  "role": "user" | "assistant" | "tool"
  "content": string
  "reasoning_content"?: string | null
  "created_at"?: string | null
  "tool_name"?: string | null
  "tool_call_id"?: string | null
  "tool_args"?: unknown | null
  "tool_call_error"?: boolean | null
  "tool_calls"?: (Record<string, unknown>)[]
  "attachments"?: AgentMessageAttachmentItem[]
}

/** 表示当前 run 等待用户决策或后台外部任务的动作。 */
export interface AgentPendingRequirement {
  "id"?: string | null
  "kind"?: "confirmation" | "user_feedback" | "external_job"
  "run_id": string
  "session_id": string
  "tool_name"?: string | null
  "tool_execution"?: Record<string, unknown>
  "suggested_patch"?: AgentSuggestedPatch | null
  "user_feedback_schema"?: (Record<string, unknown>)[]
  "note"?: string | null
}

/** 描述每轮 Run 固化的焦点与项目工作范围。 */
export interface AgentRunContextSummary {
  "focus": AgentScopeContext
  "work_scope_mode"?: "workspace" | "selected_projects"
  "allowed_projects"?: AgentRunProjectSummary[]
  "focus_version"?: number
}

/** 描述 Run 项目工作集中的单个项目，名称用于界面与模型上下文展示。 */
export interface AgentRunProjectSummary {
  "id": number
  "name"?: string | null
}

/** 向 Agent 发送消息并启动一次 run 的请求体。 */
export interface AgentRunRequest {
  "run_id"?: string | null
  "message"?: string
  "image_attachment_ids"?: number[]
  "llm_config_id"?: number | null
  "reasoning"?: ReasoningPolicy
  "focus": AgentFocusRequest
}

/** 启动后台 run 后返回给 Editor 的订阅游标。 */
export interface AgentRunStartResponse {
  "run_id": string
  "session_id": string
  "status"?: "pending" | "running"
  "event_index"?: number
}

/** 描述单次 Run 固化的业务焦点。 */
export interface AgentScopeContext {
  "scope_type"?: "workspace" | "project" | "page" | "component"
  "workspace_id": number
  "project_id"?: number | null
  "page_id"?: number | null
  "component_id"?: number | null
  "workspace_name"?: string | null
  "project_name"?: string | null
  "page_title"?: string | null
  "component_name"?: string | null
  "source"?: string
}

/** Agent 会话列表项。 */
export interface AgentSessionItem {
  "session_id": string
  "agent_id": string
  "workspace_id": number
  "session_name"?: string | null
  "focus_mode"?: "follow_route" | "pinned_project" | "workspace"
  "pinned_project_id"?: number | null
  "work_scope_mode"?: "workspace" | "selected_projects"
  "allowed_project_ids"?: number[]
  "focus_version"?: number
  "created_at"?: string | null
  "updated_at"?: string | null
  "metadata"?: Record<string, unknown>
}

/** 会话运行时快照，供 Editor 刷新和切会话后一次性恢复状态。 */
export interface AgentSessionRuntimeSnapshot {
  "session": AgentSessionItem
  "timeline_items"?: AgentTimelineItem[]
  "context_status": AgentContextStatusItem
  "active_run"?: AgentActiveRunItem | null
  "last_run"?: AgentActiveRunItem | null
  "pending_requirement"?: AgentPendingRequirement | null
  "event_index"?: number
  "pending_attachments"?: AgentImageAttachmentItem[]
}

/** 待确认写入动作附带的页面改动建议。 */
export interface AgentSuggestedPatch {
  "tool_name": string
  "target_page_id": number
  "change_note"?: string | null
  "proposed_content": string
  "unified_diff": string
}

/** 按 session/run/event_index 派生的会话时间线项。 */
export interface AgentTimelineItem {
  "id": string
  "session_id": string
  "run_id": string
  "kind": "run_context" | "message" | "reasoning" | "tool" | "run_status" | "requirement"
  "role"?: "user" | "assistant" | null
  "event_index"?: number | null
  "order_index": number
  "content"?: string | null
  "status"?: string | null
  "tool"?: AgentTimelineToolItem | null
  "run_context"?: AgentRunContextSummary | null
  "attachments"?: AgentMessageAttachmentItem[]
  "source": "message" | "event" | "synthetic"
  "created_at"?: string | null
}

/** 时间线中的工具调用详情，独立于 assistant 消息存在。 */
export interface AgentTimelineToolItem {
  "tool_call_id"?: string | null
  "tool_name": string
  "status": "running" | "waiting_external" | "completed" | "error" | "cancelled" | "interrupted"
  "input_payload"?: unknown | null
  "output_payload"?: unknown | null
  "message"?: string
  "progress"?: Record<string, unknown> | null
  "input_attachments"?: AgentMessageAttachmentItem[]
  "output_attachments"?: AgentMessageAttachmentItem[]
}

/** 返回给 Editor 的单个工具有效配置。 */
export interface AgentToolConfigItem {
  "key": string
  "label": string
  "group_key": string
  "group_label": string
  "default_description": string
  "description": string
  "description_override"?: string | null
  "default_instructions"?: string | null
  "instructions"?: string | null
  "instructions_override"?: string | null
  "enabled"?: boolean
  "configurable"?: boolean
  "requires_confirmation"?: boolean
  "risk_level"?: "system" | "read" | "write" | "danger"
  "agent_guide": AgentToolGuideItem
}

/** 更新单个工具开关或工具提示词覆盖的请求。 */
export interface AgentToolConfigUpdateRequest {
  "enabled"?: boolean | null
  "description_override"?: string | null
  "instructions_override"?: string | null
  "restore_default"?: boolean
}

/** 按工具组返回工具配置，供前端分组展示。 */
export interface AgentToolGroupConfigItem {
  "key": string
  "label": string
  "description": string
  "tools"?: AgentToolConfigItem[]
}

/** 返回给 Editor 的面向 Agent 工具调用说明。 */
export interface AgentToolGuideItem {
  "tool_name": string
  "effective_description": string
  "system_description": string
  "instructions"?: string | null
  "parameters_schema"?: Record<string, unknown> | null
  "call_example"?: Record<string, unknown> | null
  "response_example"?: unknown | null
  "response_notes"?: string | null
  "required_context_fields"?: string[]
  "runtime_disclosure_groups"?: string[]
  "requires_confirmation"?: boolean
  "risk_level"?: "system" | "read" | "write" | "danger"
}

/** 大模型配置归属范围。 */
export type AiLlmConfigScope = "global" | "personal"

/** Web 控制台创建个人访问令牌请求。 */
export interface ApiAccessTokenCreateRequest {
  "name": string
  "workspace_ids"?: number[]
  "all_workspaces"?: boolean
  "scopes": string[]
  "expires_in_days"?: number | null
}

/** 创建个人访问令牌响应（仅此一次返回明文 Token）。 */
export interface ApiAccessTokenCreateResponse {
  "id": number
  "name": string
  "token_public_id": string
  "token": string
  "expires_at": string | null
  "all_workspaces": boolean
  "workspace_ids": number[]
  "scopes": string[]
  "created_at": string
}

/** 个人访问令牌列表项及详情模型。 */
export interface ApiAccessTokenItem {
  "id": number
  "name": string
  "token_public_id": string
  "token_masked": string
  "expires_at": string | null
  "revoked_at": string | null
  "last_used_at": string | null
  "last_used_ip": string | null
  "is_active": boolean
  "all_workspaces": boolean
  "workspace_ids": number[]
  "scopes": string[]
  "created_at": string
}

/** 个人访问令牌列表响应。 */
export interface ApiAccessTokenListResponse {
  "items": ApiAccessTokenItem[]
  "total": number
  "max_active_tokens": number
}

/** Web 控制台更新个人访问令牌配置请求。 */
export interface ApiAccessTokenUpdateRequest {
  "name"?: string | null
  "workspace_ids"?: number[] | null
  "all_workspaces"?: boolean | null
  "scopes"?: string[] | null
  "expires_in_days"?: number | null
}

/** 资产机器分析结构化元数据。 */
export interface AssetAnalysisMetadata {
  "schema_version"?: number
  "kind"?: string
  "icon": AssetIconAnalysisPayload
}

/** 归档资源的请求体。 */
export interface AssetArchiveRequest {
  "archive_reason"?: string | null
}

/** 批量归档资源的请求体。 */
export interface AssetBatchArchiveRequest {
  "asset_ids": number[]
  "archive_reason"?: string | null
}

/** 批量删除资源的请求体。 */
export interface AssetBatchDeleteRequest {
  "asset_ids": number[]
}

/** 批量资源操作中单个资源失败的明细。 */
export interface AssetBatchOperationFailure {
  "asset_id": number
  "code": string
  "detail": string
}

/** 批量资源操作结果汇总，保留逐项失败原因。 */
export interface AssetBatchOperationResponse {
  "requested_count": number
  "succeeded_count": number
  "failed_count": number
  "asset_ids"?: number[]
  "failures"?: AssetBatchOperationFailure[]
}

/** 批量恢复归档资源的请求体。 */
export interface AssetBatchRestoreRequest {
  "asset_ids": number[]
  "restore_reason"?: string | null
}

/** 通过文本内容创建可编辑资源的请求体。 */
export interface AssetContentCreateRequest {
  "asset_type": AssetType
  "name": string
  "original_name": string
  "content": string
  "description"?: string | null
  "tags"?: string[]
  "approx_aspect_ratio"?: string | null
}

/** 预览资源内容改动的请求体。 */
export interface AssetContentPreviewRequest {
  "content": string
}

/** 资源内容改动预览结果。 */
export interface AssetContentPreviewResponse {
  "asset_id": number
  "asset_name": string
  "changed": boolean
  "unified_diff": string
}

/** 返回可编辑资源的文本内容。 */
export interface AssetContentResponse {
  "asset": AssetResponse
  "content": string
}

/** 替换可编辑资源内容的请求体。 */
export interface AssetContentUpdateRequest {
  "content": string
  "change_note"?: string | null
}

/** 复制资源记录的请求体。 */
export interface AssetCopyRequest {
  "name"?: string | null
  "original_name"?: string | null
  "description"?: string | null
  "tags"?: string[] | null
  "status"?: RecordStatus
  "archive_reason"?: string | null
}

/** 资产列表中携带的字体配置摘要。 */
export interface AssetFontConfigSummary {
  "id": number
  "asset_id": number
  "asset_name": string
  "font_family": string
  "font_format": string
  "font_weight": string
  "font_style": string
  "font_display": string
  "status": RecordStatus
}

/** 图标资产分析结果的结构化载荷。 */
export interface AssetIconAnalysisPayload {
  "format"?: "svg" | "image" | "unknown"
  "render_mode"?: "inline_svg" | "image"
  "style"?: "stroke" | "fill" | "mixed" | "complex" | "unknown"
  "inline_safe"?: boolean
  "stroke_width_editable"?: boolean
  "analysis_status"?: "analyzed" | "unsupported" | "error"
  "reasons"?: string[]
}

/** 资源离线包导出的请求体。 */
export interface AssetPackageExportRequest {
  "asset_ids": number[]
}

/** 资源离线包导入中单个资源失败的明细。 */
export interface AssetPackageImportFailure {
  "name": string
  "code": string
  "detail": string
}

/** 资源离线包导入后单个资源的处理结果。 */
export interface AssetPackageImportItem {
  "name": string
  "original_name": string
  "asset_type": AssetType
  "file_hash": string
  "action": "create" | "update_metadata" | "reuse"
  "asset_id"?: number | null
}

/** 资源离线包导入汇总结果。 */
export interface AssetPackageImportResult {
  "imported_count"?: number
  "updated_count"?: number
  "reused_count"?: number
  "failed_count"?: number
  "assets"?: AssetPackageImportItem[]
  "failures"?: AssetPackageImportFailure[]
}

/** 描述资源当前被哪些业务对象引用。 */
export interface AssetReferenceSummary {
  "theme_count"?: number
  "font_count"?: number
  "page_count"?: number
  "component_count"?: number
  "component_version_count"?: number
  "references"?: (Record<string, unknown>)[]
  "has_references": boolean
}

/** 资源渲染提示回填失败明细。 */
export interface AssetRenderHintBackfillFailure {
  "asset_id": number
  "asset_name"?: string | null
  "code": string
  "detail": string
}

/** 创建资源渲染提示回填任务组请求。 */
export interface AssetRenderHintBackfillJobCreateRequest {
  "asset_types"?: ("image" | "video" | "drawio" | "mermaid" | "formula")[] | null
  "asset_ids"?: number[] | null
  "mode"?: "preview" | "apply"
  "overwrite_manual"?: boolean
}

/** 资源渲染提示回填任务组聚合响应。 */
export interface AssetRenderHintBackfillJobGroupResponse {
  "job_group_id": string
  "status": "pending" | "running" | "succeeded" | "failed" | "partial"
  "requested_count": number
  "pending_count": number
  "running_count": number
  "succeeded_count": number
  "failed_count": number
  "skipped_count": number
  "asset_ids"?: number[]
  "jobs"?: AssetRenderHintBackfillJobResponse[]
  "failures"?: AssetRenderHintBackfillFailure[]
}

/** 资源渲染提示回填任务响应。 */
export interface AssetRenderHintBackfillJobResponse {
  "id": number
  "job_group_id": string | null
  "workspace_id": number
  "asset_id": number
  "asset_name"?: string | null
  "asset_type": AssetType
  "source": string
  "mode": "preview" | "apply"
  "overwrite_manual": boolean
  "status": "pending" | "running" | "succeeded" | "failed" | "skipped"
  "attempt_count": number
  "current_render_metadata"?: Record<string, unknown> | null
  "next_render_metadata"?: Record<string, unknown> | null
  "current_approx_aspect_ratio"?: string | null
  "next_approx_aspect_ratio"?: string | null
  "error_code"?: string | null
  "error_message"?: string | null
  "created_by": number | null
  "created_at": string
  "updated_at": string
  "started_at": string | null
  "finished_at": string | null
}

/** 公开静态资源返回模型。 */
export interface AssetResponse {
  "id": number
  "workspace_id": number
  "name": string
  "file_name": string
  "original_name": string
  "description"?: string | null
  "file_size": number
  "file_hash": string
  "content_type"?: string | null
  "asset_type": AssetType
  "asset_role"?: AssetRole
  "render_type"?: AssetType
  "tags"?: string[]
  "analysis_metadata"?: AssetAnalysisMetadata | null
  "render_metadata"?: Record<string, unknown> | null
  "approx_aspect_ratio"?: string | null
  "approx_aspect_ratio_value"?: number | null
  "aspect_ratio_source"?: string | null
  "status"?: RecordStatus
  "archived_at"?: string | null
  "archive_reason"?: string | null
  "source_asset_id"?: number | null
  "history_kind"?: string | null
  "content_editable"?: boolean
  "url"?: string | null
  "font_config"?: AssetFontConfigSummary | null
  "rename_block_reason"?: string | null
  "delete_block_reason"?: string | null
  "archive_block_reason"?: string | null
  "archive_warning_reasons"?: string[]
  "created_at": string
  "updated_at": string
}

/** 恢复归档资源的请求体。 */
export interface AssetRestoreRequest {
  "restore_reason"?: string | null
}

/** 资源在平台内的职责分组。 */
export type AssetRole = "foundation" | "content"

/** 资源库静态资源大类枚举。 */
export type AssetType = "icon" | "font" | "image" | "video" | "drawio" | "mermaid" | "chart" | "formula"

/** 更新静态资源（如改名或修改标签）。 */
export interface AssetUpdateRequest {
  "name"?: string | null
  "original_name"?: string | null
  "description"?: string | null
  "tags"?: string[] | null
  "approx_aspect_ratio"?: string | null
}

/** 当前登录用户信息。 */
export interface AuthUser {
  "id": number
  "username": string
  "display_name": string
  "role": UserRole
  "status": RecordStatus
  "last_login_at": string | null
  "preview_size_presets": PreviewSizePreset[]
}

export interface Body_create_project_template_package_preview_artifact_api_workspaces__workspace_id__template_packages_preview_artifact_post {
  "archive": string
}

export interface Body_import_component_package_api_components_import_package_post {
  "workspace_id": number
  "archive": string
}

export interface Body_import_project_template_package_api_workspaces__workspace_id__template_packages_import_post {
  "archive": string
}

export interface Body_import_workspace_asset_package_api_workspaces__workspace_id__assets_import_package_post {
  "archive": string
}

export interface Body_import_workspace_style_package_api_workspaces__workspace_id__styles_import_package_post {
  "archive": string
}

export interface Body_replace_workspace_asset_file_api_workspaces__workspace_id__assets__asset_id__replace_post {
  "file": string
}

export interface Body_upload_agent_image_attachment_api_ai_sessions__session_id__attachments_images_post {
  "file": string
}

export interface Body_upload_asset_api_v1_assets_post {
  "file": string
  "asset_type": AssetType
  "name"?: string | null
  "description"?: string | null
  "tags"?: string | null
  "overwrite"?: boolean
}

export interface Body_upload_asset_file_api_workspaces__workspace_id__assets_upload_post {
  "file": string
  "asset_type"?: AssetType
  "tags"?: string
  "name"?: string | null
  "description"?: string | null
  "overwrite"?: boolean
}

export interface Body_validate_component_package_import_api_components_import_package_validate_post {
  "workspace_id": number
  "archive": string
}

export interface Body_validate_project_template_package_import_api_workspaces__workspace_id__template_packages_import_validate_post {
  "archive": string
}

export interface Body_validate_workspace_style_package_import_api_workspaces__workspace_id__styles_import_package_validate_post {
  "archive": string
}

/** Runtime Build Worker 领取构建任务的内部请求。 */
export interface BuildJobClaimRequest {
  "worker_id": string
}

/** 领取结果：任务载荷与本次 attempt 的限权令牌；无任务时 job_id 为空。 */
export interface BuildJobClaimResponse {
  "job_id"?: number | null
  "project_id"?: number | null
  "snapshot_release_id"?: string | null
  "base_url"?: string | null
  "workspace_id"?: number | null
  "attempt_id"?: string | null
  "lease_owner"?: string | null
  "lease_expires_at"?: string | null
  "deadline_at"?: string | null
  "build_token"?: string | null
  "service_token"?: string | null
  "message"?: string
}

/** Runtime Build Worker 上报构建终态的内部请求。 */
export interface BuildJobCompleteRequest {
  "success": boolean
  "error_message"?: string | null
}

/** 修改密码入参，要求同时提供旧密码与新密码。 */
export interface ChangePasswordRequest {
  "old_password": string
  "new_password": string
}

/** 聊天槽位绑定状态。 */
export interface ChatBindingItem {
  "slot": string
  "model_config_id"?: number | null
  "model_name"?: string | null
  "provider_config_id"?: number | null
  "provider_config_name"?: string | null
  "provider_key"?: string | null
  "provider_name"?: string | null
  "model_id"?: string | null
  "supports_image_input"?: boolean
  "binding_ready": boolean
  "inherited_from_global"?: boolean
}

/** 更新聊天槽位模型；运行策略在发起会话时选择。 */
export interface ChatBindingUpdate {
  "model_config_id"?: number | null
  "scope"?: AiLlmConfigScope
}

/** 单个聊天模型的目录能力事实。 */
export interface ChatModelCatalogItem {
  "provider_key": string
  "model_id": string
  "name": string
  "protocol_key": string
  "family"?: string | null
  "status"?: string | null
  "release_date"?: string | null
  "last_updated"?: string | null
  "context_tokens"?: number | null
  "input_tokens"?: number | null
  "output_tokens"?: number | null
  "input_modalities"?: string[]
  "output_modalities"?: string[]
  "supports_tool_call"?: boolean
  "supports_structured_output"?: boolean
  "supports_attachment"?: boolean
  "supports_reasoning"?: boolean
  "reasoning_options"?: Record<string, unknown>
  "catalog_version": string
  "synced_at"?: string | null
}

/** 创建聊天模型配置。 */
export interface ChatModelConfigCreate {
  "name": string
  "scope"?: AiLlmConfigScope
  "provider_config_id": number
  "model_id": string
  "capability_override"?: Record<string, unknown>
  "advanced_config"?: Record<string, unknown>
}

/** 聊天模型及合并后能力。 */
export interface ChatModelConfigItem {
  "id": number
  "scope": string
  "editable": boolean
  "name": string
  "provider_config_id": number
  "provider_name": string
  "provider_key": string
  "protocol_key": string
  "model_id": string
  "catalog_version"?: string | null
  "capability": Record<string, unknown>
  "capability_override": Record<string, unknown>
  "advanced_config": Record<string, unknown>
  "status": string
}

/** 更新聊天模型配置。 */
export interface ChatModelConfigUpdate {
  "name"?: string | null
  "provider_config_id"?: number | null
  "model_id"?: string | null
  "capability_override"?: Record<string, unknown> | null
  "advanced_config"?: Record<string, unknown> | null
  "status"?: "active" | "archived" | null
}

/** 前端可选择的 Models.dev 聊天供应商。 */
export interface ChatProviderCatalogItem {
  "provider_key": string
  "name": string
  "api_url"?: string | null
  "docs_url"?: string | null
  "default_base_url"?: string | null
  "protocol_key": string
  "catalog_version": string
  "synced_at"?: string | null
}

/** 创建聊天供应商连接。 */
export interface ChatProviderConfigCreate {
  "name": string
  "scope"?: AiLlmConfigScope
  "catalog_provider_key"?: string | null
  "custom"?: boolean
  "base_url"?: string | null
  "api_key"?: string | null
}

/** 聊天供应商连接响应。 */
export interface ChatProviderConfigItem {
  "id": number
  "scope": string
  "editable": boolean
  "name": string
  "provider_key": string
  "catalog_provider_key"?: string | null
  "provider_name": string
  "protocol_key": string
  "base_url"?: string | null
  "has_api_key": boolean
  "api_key_masked"?: string | null
  "status": string
}

/** 更新聊天供应商连接；供应商身份和协议不可修改。 */
export interface ChatProviderConfigUpdate {
  "name"?: string | null
  "base_url"?: string | null
  "api_key"?: string | null
  "status"?: "active" | "archived" | null
}

/** 浏览器端错误日志上报载荷，只允许错误排障所需的有限字段。 */
export interface ClientErrorLogRequest {
  "source": "editor" | "runtime-browser"
  "message": string
  "error_name"?: string | null
  "stack"?: string | null
  "route"?: string | null
  "url"?: string | null
  "component"?: string | null
  "trace_id"?: string | null
  "artifact_id"?: string | null
  "context"?: Record<string, unknown>
}

/** 组件预览 artifact 创建选项。 */
export interface ComponentPreviewOptions {
  "page"?: ComponentPreviewPageOptions
  "placement"?: ComponentPreviewPlacementOptions
}

/** 组件预览页面配置，直接决定 Runtime 页面尺寸与主题。 */
export interface ComponentPreviewPageOptions {
  "width"?: number
  "height"?: number
  "base_font_size"?: string
  "icon_default_stroke_width"?: number
  "theme_key"?: string | null
  "theme_config_yaml"?: string | null
}

/** 组件在预览页面中的占位与对齐配置。 */
export interface ComponentPreviewPlacementOptions {
  "width_mode"?: "auto" | "percent" | "fixed"
  "width_value"?: number | null
  "height_mode"?: "auto" | "percent" | "fixed"
  "height_value"?: number | null
  "horizontal_align"?: "start" | "center" | "end"
  "vertical_align"?: "start" | "center" | "end"
  "padding"?: number
}

/** 组件分享包导出预检中的资源摘要。 */
export interface ComponentShareExportAssetSummary {
  "name": string
  "original_name": string
  "asset_type": string
  "file_hash": string
  "source"?: string
}

/** 组件分享包导出预检中的组件摘要。 */
export interface ComponentShareExportComponentSummary {
  "source_component_code": string
  "source_version_no": number
  "name": string
  "import_name": string
  "has_dynamic_resources"?: boolean
  "missing_static_asset_names"?: string[]
}

/** 组件分享包导出预检结果。 */
export interface ComponentShareExportValidationResult {
  "can_export"?: boolean
  "components"?: ComponentShareExportComponentSummary[]
  "automatic_assets"?: ComponentShareExportAssetSummary[]
  "manual_assets"?: ComponentShareExportAssetSummary[]
  "fonts"?: ComponentSharePackageFontSummary[]
  "warnings"?: string[]
  "missing_static_asset_names"?: string[]
  "missing_manual_asset_names"?: string[]
  "dynamic_resource_components"?: string[]
}

/** 组件分享包正式导入结果。 */
export interface ComponentShareImportResult {
  "imported_components"?: WorkspaceComponentItem[]
  "components"?: ComponentSharePackageComponentSummary[]
  "assets"?: ComponentSharePackageAssetSummary[]
  "fonts"?: ComponentSharePackageFontSummary[]
  "warnings"?: string[]
}

/** 组件分享包导入预检结果。 */
export interface ComponentShareImportValidationResult {
  "valid": boolean
  "schema_version"?: number | null
  "runtime_kit_manifest_version"?: string | null
  "components"?: ComponentSharePackageComponentSummary[]
  "assets"?: ComponentSharePackageAssetSummary[]
  "fonts"?: ComponentSharePackageFontSummary[]
  "errors"?: string[]
  "warnings"?: string[]
}

/** 分享包内资源摘要，用于展示导入动作。 */
export interface ComponentSharePackageAssetSummary {
  "name": string
  "original_name": string
  "asset_type": string
  "file_hash": string
  "action"?: string
}

/** 分享包内组件摘要，用于预检和导入结果展示。 */
export interface ComponentSharePackageComponentSummary {
  "source_component_code": string
  "source_version_no": number
  "name": string
  "import_name": string
  "component_type": string
  "dependencies"?: string[]
  "component_fingerprint"?: string | null
  "matched_component_id"?: number | null
  "matched_component_code"?: string | null
  "action"?: string
  "match_reason"?: string | null
}

/** 分享包内字体配置摘要，用于展示导入动作。 */
export interface ComponentSharePackageFontSummary {
  "asset_name": string
  "font_family": string
  "font_format": string
  "font_weight": string
  "font_style": string
  "font_display": string
  "status": string
  "action"?: string
}

/** 创建 Agent 会话的请求体。 */
export interface CreateAgentSessionRequest {
  "agent_id"?: string
  "session_name"?: string | null
  "workspace_id": number
  "focus_mode"?: "follow_route" | "pinned_project" | "workspace"
  "pinned_project_id"?: number | null
  "work_scope_mode"?: "workspace" | "selected_projects"
  "allowed_project_ids"?: number[]
  "llm_config_id"?: number | null
}

/** External API 文本资源创建请求。 */
export interface ExternalAssetContentCreateRequest {
  "asset_type": string
  "name": string
  "original_name": string
  "content": string
  "description"?: string | null
  "tags"?: string[]
  "approx_aspect_ratio"?: string | null
}

/** External API 文本资源差异预览请求。 */
export interface ExternalAssetContentPreviewRequest {
  "content": string
}

/** External API 文本资源内容更新请求。 */
export interface ExternalAssetContentUpdateRequest {
  "content": string
  "change_note"?: string | null
}

/** External API 资源复制请求。 */
export interface ExternalAssetCopyRequest {
  "name"?: string | null
  "original_name"?: string | null
  "description"?: string | null
  "tags"?: string[] | null
}

/** 批量归档请求模型。 */
export interface ExternalBatchArchiveRequest {
  "ids": number[]
  "reason"?: string | null
}

/** 批量归档响应模型。 */
export interface ExternalBatchArchiveResponse {
  "archived_ids": number[]
  "failed_ids": number[]
  "total": number
}

/** 能力发现响应模型。 */
export interface ExternalCapabilitiesResponse {
  "version"?: string
  "workspace_id": number
  "scopes": string[]
  "operations": string[]
}

/** 组件结构化编辑异步 Mutation 任务请求。 */
export interface ExternalComponentApplyEditsMutationRequest {
  "component_id": number
  "base_version_no": number
  "base_draft_hash"?: string | null
  "edits": (Record<string, unknown>)[]
}

/** 组件创建异步 Mutation 任务请求。 */
export interface ExternalComponentCreateMutationRequest {
  "workspace_id": number
  "import_name": string
  "name": string
  "component_type"?: string
  "source_code": string
  "description"?: string | null
  "preview_schema"?: Record<string, unknown> | null
}

/** External API 组件重校验元数据 Mutation 请求。 */
export interface ExternalComponentMetadataMutationRequest {
  "component_id": number
  "base_version_no"?: number | null
  "base_draft_hash"?: string | null
  "name"?: string | null
  "import_name"?: string | null
  "component_type"?: string | null
  "summary"?: string | null
  "preview_schema"?: Record<string, unknown> | null
  "change_note"?: string | null
}

/** External API 组件轻量元数据更新请求，结构与源码字段继续走 Mutation。 */
export interface ExternalComponentMetadataUpdateRequest {
  "name"?: string | null
  "summary"?: string | null
}

/** External API 页面/组件当前或候选内容校验请求。 */
export interface ExternalEntityValidationRequest {
  "entity_type": "page" | "component"
  "entity_id"?: number | null
  "mode"?: "current" | "content" | "edits"
  "source_code"?: string | null
  "edits"?: (Record<string, unknown>)[] | null
  "preview_schema"?: Record<string, unknown> | null
  "detail"?: boolean
}

/** External API 页面/组件校验结果。 */
export interface ExternalEntityValidationResponse {
  "entity_type": "page" | "component"
  "entity_id"?: number | null
  "mode": "current" | "content" | "edits"
  "valid": boolean
  "status"?: string | null
  "retryable"?: boolean
  "error_code"?: string | null
  "summary": string
  "errors"?: string[]
  "warnings"?: string[]
  "imports"?: string[]
  "diagnostics"?: (Record<string, unknown>)[]
}

/** External API 统一错误响应模型。 */
export interface ExternalErrorDetail {
  "code": string
  "message": string
  "retryable"?: boolean
  "details"?: Record<string, unknown> | null
}

/** 异步变更任务状态响应模型。 */
export interface ExternalMutationJobResponse {
  "job_id": string
  "job_type": string
  "workspace_id": number
  "target_id"?: number | null
  "status": "pending" | "running" | "succeeded" | "failed" | "canceled"
  "attempt_count": number
  "max_attempts": number
  "next_attempt_at"?: string | null
  "last_error_code"?: string | null
  "cancel_requested_at"?: string | null
  "retry_of_job_id"?: string | null
  "result"?: Record<string, unknown> | null
  "error"?: ExternalErrorDetail | null
  "created_at": string
  "started_at"?: string | null
  "finished_at"?: string | null
}

/** 页面结构化编辑异步 Mutation 任务请求。 */
export interface ExternalPageApplyEditsMutationRequest {
  "page_id": number
  "base_version_no": number
  "edits": (Record<string, unknown>)[]
}

/** External API 页面复制请求。 */
export interface ExternalPageCopyRequest {
  "target_project_id": number
  "title"?: string | null
  "summary"?: string | null
  "route_placement"?: "none" | "root" | "group"
  "parent_route_id"?: number | null
  "route"?: string | null
}

/** 页面创建异步 Mutation 任务请求。 */
export interface ExternalPageCreateMutationRequest {
  "project_id": number
  "name": string
  "source_code": string
  "description"?: string | null
}

/** External API 页面轻量元数据更新请求，禁止绕过 Mutation 写入源码。 */
export interface ExternalPageMetadataUpdateRequest {
  "title"?: string | null
  "summary"?: string | null
  "speaker_notes"?: string | null
}

/** External API 项目预览 artifact 创建请求。 */
export interface ExternalPreviewArtifactCreateRequest {
  "route"?: string | null
}

/** External API 将样式方案应用到项目的请求。 */
export interface ExternalProjectApplyStyleRequest {
  "style_id": number
}

/** External API 项目额外资源配置更新请求。 */
export interface ExternalProjectBuildAssetsRequest {
  "build_extra_assets_json"?: Record<string, unknown>
}

/** External API 项目配置读取响应。 */
export interface ExternalProjectConfigurationResponse {
  "project_id": number
  "workspace_id": number
  "presentation": Record<string, unknown>
  "suggested_components"?: (Record<string, unknown>)[]
  "build_extra_assets_json"?: Record<string, unknown>
}

/** External API 项目配置整体更新请求。 */
export interface ExternalProjectConfigurationUpdateRequest {
  "configuration"?: Record<string, unknown>
  "build_extra_assets_json"?: Record<string, unknown> | null
}

/** External API 项目创建请求（workspace_id 优先使用 Header 中的 X-Workspace-ID）。 */
export interface ExternalProjectCreateRequest {
  "name": string
  "description"?: string | null
  "status"?: string
  "configuration"?: ProjectDefaultConfiguration | ProjectStyleConfiguration | ProjectCustomConfiguration
  "build_extra_assets_json"?: Record<string, unknown> | null
}

/** 标准规范响应。 */
export interface ExternalStandardResponse {
  "standard_type": string
  "markdown": string
}

/** External API 样式创建请求，兼容嵌套配置与详情响应的扁平字段。 */
export interface ExternalStyleCreateRequest {
  "name": string
  "key"?: string | null
  "description"?: string | null
  "configuration"?: StyleConfiguration
  "page_width"?: number | null
  "page_height"?: number | null
  "base_font_size"?: string | null
  "icon_default_stroke_width"?: number | null
  "show_pdf_export_button"?: boolean | null
  "menu_mode"?: "text" | "preview" | "bottom-preview" | null
  "theme_key"?: string | null
  "style_spec_markdown"?: string | null
}

/** 系统健康状态响应。 */
export interface ExternalSystemHealthResponse {
  "status"?: string
  "database"?: boolean
  "redis"?: boolean
}

/** 系统版本信息响应。 */
export interface ExternalSystemVersionResponse {
  "version": string
  "api_version"?: string
  "app_name": string
}

/** External API 主题创建请求（palette 缺省时自动填充默认调色板）。 */
export interface ExternalThemeCreateRequest {
  "key": string
  "name": string
  "description"?: string | null
  "palette"?: Record<string, unknown> | null
}

/** 当前鉴权身份与授权工作空间。 */
export interface ExternalWhoAmIResponse {
  "user": Record<string, unknown>
  "token"?: Record<string, unknown> | null
  "workspaces"?: (Record<string, unknown>)[]
}

export interface HTTPValidationError {
  "detail"?: ValidationError[]
}

/** 图片生成槽位绑定状态。 */
export interface ImageBindingItem {
  "slot"?: string
  "model_config_id"?: number | null
  "model_name"?: string | null
  "provider_config_id"?: number | null
  "provider_config_name"?: string | null
  "provider_key"?: string | null
  "provider_name"?: string | null
  "model_id"?: string | null
  "binding_ready": boolean
  "inherited_from_global"?: boolean
}

/** 更新图片生成槽位。 */
export interface ImageBindingUpdate {
  "model_config_id"?: number | null
  "scope"?: AiLlmConfigScope
}

/** 创建图片模型配置。 */
export interface ImageModelConfigCreate {
  "name": string
  "scope"?: AiLlmConfigScope
  "provider_config_id": number
  "model_id": string
  "advanced_config"?: Record<string, unknown>
}

/** 图片模型配置响应。 */
export interface ImageModelConfigItem {
  "id": number
  "scope": string
  "editable": boolean
  "name": string
  "provider_config_id": number
  "provider_name": string
  "provider_key": string
  "model_id": string
  "capability": Record<string, unknown>
  "advanced_config": Record<string, unknown>
  "status": string
}

/** 更新图片模型配置。 */
export interface ImageModelConfigUpdate {
  "name"?: string | null
  "provider_config_id"?: number | null
  "model_id"?: string | null
  "advanced_config"?: Record<string, unknown> | null
  "status"?: "active" | "archived" | null
}

/** 代码注册的图片供应商和模型。 */
export interface ImageProviderCatalogItem {
  "provider_key": string
  "name": string
  "docs_url": string
  "default_base_url"?: string | null
  "requires_base_url": boolean
  "models": (Record<string, unknown>)[]
}

/** 创建图片供应商连接。 */
export interface ImageProviderConfigCreate {
  "name": string
  "scope"?: AiLlmConfigScope
  "provider_key": string
  "base_url"?: string | null
  "api_key"?: string | null
}

/** 图片供应商连接响应。 */
export interface ImageProviderConfigItem {
  "id": number
  "scope": string
  "editable": boolean
  "name": string
  "provider_key": string
  "provider_name": string
  "base_url"?: string | null
  "has_api_key": boolean
  "api_key_masked"?: string | null
  "status": string
}

/** 更新图片供应商连接。 */
export interface ImageProviderConfigUpdate {
  "name"?: string | null
  "base_url"?: string | null
  "api_key"?: string | null
  "status"?: "active" | "archived" | null
}

export type JsonValue = unknown

/** 用户登录入参，包含用户名和密码。 */
export interface LoginRequest {
  "username": string
  "password": string
}

/** 登录成功后的响应内容。 */
export interface LoginResponse {
  "user": AuthUser
}

/** 简单操作响应，用于删除、登出等无需复杂数据的场景。 */
export interface MessageResponse {
  "message": string
}

/** 目录同步可观测状态。 */
export interface ModelCatalogSyncItem {
  "catalog_version"?: string | null
  "last_attempt_at"?: string | null
  "last_success_at"?: string | null
  "last_error"?: string | null
  "syncing"?: boolean
}

/** 页面组件资源索引项，记录组件的参数名和值。 */
export interface PageComponentResourceItem {
  "component_name": string
  "resource_attr": string
  "resource_name": string
}

/** 页面复制到目标项目的入参。 */
export interface PageCopyToProjectRequest {
  "target_project_id": number
  "title"?: string | null
  "summary"?: string | null
  "route_placement"?: "none" | "root" | "group"
  "parent_route_id"?: number | null
  "route"?: string | null
}

/** 创建页面资源入参，code 由后端自动生成。 */
export interface PageCreateRequest {
  "page_content": string
  "file_type"?: PageFileType
  "title": string
  "summary"?: string | null
  "speaker_notes"?: string | null
  "status"?: RecordStatus
  "workspace_id"?: number | null
  "project_id"?: number | null
}

/** 页面当前版本的组件索引响应，包含组件集合与资源集合。 */
export interface PageCurrentComponentIndex {
  "page_id": number
  "current_version_no": number
  "page_version_id": number | null
  "components": string[]
  "resources": PageComponentResourceItem[]
}

/** 页面当前版本的源码依赖索引响应。 */
export interface PageCurrentModuleDependencies {
  "page_id": number
  "current_version_no": number
  "page_version_id": number | null
  "dependencies": PageModuleDependencyItem[]
}

/** 页面文件类型枚举，用于约束页面源码下发时的文件扩展名。 */
export type PageFileType = "vue" | "ts" | "js" | "json" | "md" | "txt" | "yaml"

/** 页面资源响应模型，返回全局资源库所需字段。 */
export interface PageItem {
  "id": number
  "code": string
  "page_content": string
  "current_version_no": number
  "file_type": PageFileType
  "title": string
  "summary": string | null
  "speaker_notes"?: string | null
  "status": RecordStatus
  "workspace_id": number | null
  "workspace_name"?: string | null
  "project_id": number | null
  "project_name"?: string | null
  "created_at": string
  "updated_at": string
  "created_by": number | null
  "updated_by": number | null
  "screenshot_url"?: string | null
  "screenshot_version_no"?: number | null
  "screenshot_config_hash"?: string | null
  "screenshot_viewport_width"?: number | null
  "screenshot_viewport_height"?: number | null
  "screenshot_is_latest"?: boolean
  "screenshot_updated_at"?: string | null
  "is_in_project_route"?: boolean | null
  "route_bindings"?: ProjectRoutePageBinding[]
}

/** 页面当前版本的源码依赖项。 */
export interface PageModuleDependencyItem {
  "dependency_kind": string
  "component_code"?: string | null
  "component_version_no"?: number | null
  "runtime_module_path"?: string | null
  "runtime_kit_name"?: string | null
  "runtime_kit_base_name"?: string | null
  "runtime_kit_version_no"?: number | null
  "runtime_kit_import_path"?: string | null
}

/** 批量下载页面截图请求。 */
export interface PageScreenshotBatchDownloadRequest {
  "page_ids": number[]
}

/** 批量刷新截图中单页失败明细。 */
export interface PageScreenshotBatchFailure {
  "page_id": number
  "code": string
  "detail": string
}

/** 批量刷新页面截图请求。 */
export interface PageScreenshotBatchRefreshRequest {
  "project_id": number
}

/** 批量刷新截图结果汇总。 */
export interface PageScreenshotBatchRefreshResponse {
  "requested_count": number
  "succeeded_count": number
  "failed_count": number
  "page_ids"?: number[]
  "failures"?: PageScreenshotBatchFailure[]
}

/** 页面截图任务组聚合响应。 */
export interface PageScreenshotJobGroupResponse {
  "job_group_id": string
  "status": "pending" | "running" | "succeeded" | "failed" | "partial" | "cancelled"
  "requested_count": number
  "pending_count": number
  "running_count": number
  "succeeded_count": number
  "failed_count": number
  "skipped_count": number
  "cancelled_count": number
  "page_ids"?: number[]
  "jobs"?: PageScreenshotJobResponse[]
  "failures"?: PageScreenshotBatchFailure[]
}

/** 创建单页截图任务请求，允许显式传入本次截图视口。 */
export interface PageScreenshotJobRequest {
  "viewport_width"?: number | null
  "viewport_height"?: number | null
}

/** 页面截图任务响应。 */
export interface PageScreenshotJobResponse {
  "id": number
  "job_group_id": string | null
  "source": string
  "page_id": number
  "workspace_id": number | null
  "project_id": number | null
  "viewport_width": number
  "viewport_height": number
  "target_page_version_no": number
  "config_hash": string
  "status": "pending" | "running" | "succeeded" | "failed" | "skipped" | "cancelled"
  "attempt_count": number
  "error_code": string | null
  "error_message": string | null
  "created_by": number | null
  "created_at": string
  "updated_at": string
  "started_at": string | null
  "finished_at": string | null
  "cancel_requested_at": string | null
}

/** 页面截图请求，允许显式传入本次截图视口。 */
export interface PageScreenshotRequest {
  "viewport_width"?: number | null
  "viewport_height"?: number | null
}

/** 创建或升级重点快照的入参。 */
export interface PageSnapshotCreateRequest {
  "snapshot_name"?: string | null
}

/** 更新页面资源入参，支持元数据级别的局部变更（code 不可修改）。 */
export interface PageUpdateRequest {
  "page_content"?: string | null
  "file_type"?: PageFileType | null
  "change_note"?: string | null
  "title"?: string | null
  "summary"?: string | null
  "speaker_notes"?: string | null
  "status"?: RecordStatus | null
  "workspace_id"?: number | null
  "project_id"?: number | null
}

/** 单个页面版本的完整内容响应。 */
export interface PageVersionContent {
  "page_id": number
  "version_no": number
  "version_label": string
  "file_type": PageFileType
  "storage_type": PageVersionStorageType
  "is_important": boolean
  "snapshot_name": string | null
  "change_note": string | null
  "speaker_notes"?: string | null
  "content_mode": "full" | "diff"
  "content": string
  "resolved_content": string
  "created_at": string
  "created_by": number | null
}

/** 页面版本列表项，描述一个可供查看或恢复的历史节点。 */
export interface PageVersionListItem {
  "id": number
  "page_id": number
  "version_no": number
  "version_label": string
  "file_type": PageFileType
  "storage_type": PageVersionStorageType
  "is_important": boolean
  "is_current": boolean
  "snapshot_name": string | null
  "change_note": string | null
  "content_size": number
  "created_at": string
  "created_by": number | null
}

/** 恢复历史版本时允许附带的备注信息。 */
export interface PageVersionRestoreRequest {
  "change_note"?: string | null
}

/** 页面版本存储类型，区分完整快照与基于最新链路的向后 diff。 */
export type PageVersionStorageType = "snapshot" | "diff"

/** 描述 AST 改写或候选源码检查返回的公开保存诊断。 */
export interface PageVisualEditApplyDiagnostic {
  "severity": "error" | "warning" | "info"
  "source": string
  "code": string
  "message": string
  "node_id"?: string | null
  "binding_id"?: string | null
}

/** 批量应用页面可视化编辑操作的公开接口入参。 */
export interface PageVisualEditApplyRequest {
  "protocolVersion": number
  "artifactId": string
  "baseVersionNo": number
  "sourceHash": string
  "operations": (PageVisualEditSetValueOperation | PageVisualEditSetJsonOperation | PageVisualEditSetRichTextOperation | PageVisualEditSetTailwindTokensOperation | PageVisualEditDuplicateNodeOperation | PageVisualEditDeleteNodeOperation)[]
  "changeNote"?: string | null
}

/** 页面可视化编辑成功保存后的公开接口响应。 */
export interface PageVisualEditApplyResponse {
  "protocol_version": number
  "success"?: boolean
  "page_id": number
  "previous_version_no": number
  "current_version_no": number
  "source_hash": string
  "operations_applied": number
  "canonical_diff": string
  "diagnostics"?: PageVisualEditApplyDiagnostic[]
  "refresh_required"?: boolean
}

/** 描述模板中一个可展示在属性面板的文本、class 或 prop 绑定。 */
export interface PageVisualEditBinding {
  "binding_id": string
  "node_id": string
  "kind": "text" | "rich_text" | "class" | "prop" | "json"
  "name"?: string | null
  "value_type": "string" | "number" | "boolean" | "null" | "json" | "unknown"
  "value"?: JsonValue
  "expression"?: string | null
  "source_range": PageVisualEditSourceRange
  "editable": boolean
  "readonly_reason"?: "SFC_PARSE_ERROR" | "TEMPLATE_UNSUPPORTED" | "DYNAMIC_EXPRESSION" | "DYNAMIC_SCRIPT_SOURCE" | "SCRIPT_SOURCE_NOT_FOUND" | "LOOP_SOURCE_UNSUPPORTED" | "NESTED_LOOP_UNSUPPORTED" | "LOOP_MEMBER_UNSUPPORTED" | "MEMBER_NOT_FOUND" | "MEMBER_VALUE_DYNAMIC" | "ATTRIBUTE_VALUE_MISSING" | "RICH_TEXT_DYNAMIC_CONTENT" | "RICH_TEXT_UNSUPPORTED_STRUCTURE" | "RICH_TEXT_SOURCE_RANGE_UNRESOLVED" | "STRUCTURE_ROOT_UNSUPPORTED" | "STRUCTURE_CONTROL_FLOW_UNSUPPORTED" | "STRUCTURE_LOOP_INSTANCE_REQUIRED" | null
  "source"?: PageVisualEditScriptArrayBindingSource | PageVisualEditTemplateBindingSource | PageVisualEditTemplateRichTextBindingSource | PageVisualEditJsonBindingSource | null
}

/** 描述 visual edit 属性面板可安全消费的单个 previewSchema prop。 */
export interface PageVisualEditComponentPropField {
  "type": "string" | "textarea" | "number" | "boolean" | "select" | "json"
  "label"?: string | null
  "description"?: string | null
  "required"?: boolean | null
  "default"?: JsonValue
  "placeholder"?: string | null
  "options"?: PageVisualEditComponentSelectOption[] | null
}

/** 绑定页面本地组件标签、真实导入来源和钉住版本的 props UI 元数据。 */
export interface PageVisualEditComponentSchema {
  "source": "workspace_component" | "runtime_kit"
  "import_path": string
  "component_code": string
  "version_no": number
  "props"?: Record<string, unknown> | null
}

/** 描述组件 select 参数的一个有限选项。 */
export interface PageVisualEditComponentSelectOption {
  "label": string
  "value": string | number | number | boolean
}

/** 删除模板节点、循环模板或携带实例路径的循环数组项。 */
export interface PageVisualEditDeleteNodeOperation {
  "nodeId": string
  "instancePath"?: PageVisualEditInstancePathSegment[]
  "type": string
}

/** 描述 SFC 分析产生的稳定错误或只读警告。 */
export interface PageVisualEditDiagnostic {
  "severity": "warning" | "error"
  "code": "SFC_PARSE_ERROR" | "TEMPLATE_UNSUPPORTED" | "DYNAMIC_EXPRESSION" | "DYNAMIC_SCRIPT_SOURCE" | "SCRIPT_SOURCE_NOT_FOUND" | "LOOP_SOURCE_UNSUPPORTED" | "NESTED_LOOP_UNSUPPORTED" | "LOOP_MEMBER_UNSUPPORTED" | "MEMBER_NOT_FOUND" | "MEMBER_VALUE_DYNAMIC" | "ATTRIBUTE_VALUE_MISSING" | "RICH_TEXT_DYNAMIC_CONTENT" | "RICH_TEXT_UNSUPPORTED_STRUCTURE" | "RICH_TEXT_SOURCE_RANGE_UNRESOLVED" | "STRUCTURE_ROOT_UNSUPPORTED" | "STRUCTURE_CONTROL_FLOW_UNSUPPORTED" | "STRUCTURE_LOOP_INSTANCE_REQUIRED"
  "message": string
  "source_range"?: PageVisualEditSourceRange | null
}

/** 复制普通模板节点或携带实例路径的循环数组项。 */
export interface PageVisualEditDuplicateNodeOperation {
  "nodeId": string
  "instancePath"?: PageVisualEditInstancePathSegment[]
  "type": string
}

/** 定位一个 v-for 运行实例，公开写协议首期只接受字符串或整数 key。 */
export interface PageVisualEditInstancePathSegment {
  "loopNodeId": string
  "key"?: string | number | null
  "index"?: number | null
}

/** 标识 binding 引用 Manifest 中去重的整块 JSON 源。 */
export interface PageVisualEditJsonBindingSource {
  "kind": string
  "source_id": string
}

/** 描述可由 set_json 原子替换的静态 JSON 字面量。 */
export interface PageVisualEditJsonSource {
  "source_id": string
  "kind": "const" | "ref" | "reactive" | "template-expression"
  "name"?: string | null
  "value": JsonValue
  "source_range": PageVisualEditSourceRange
  "editable": boolean
}

/** 描述模板节点上的单层 v-for 静态语义。 */
export interface PageVisualEditLoopContext {
  "loop_node_id": string
  "source_expression": string
  "source_binding"?: string | null
  "item_alias": string
  "index_alias"?: string | null
  "key_expression"?: string | null
  "key_member"?: string | null
  "editable": boolean
  "readonly_reason"?: "SFC_PARSE_ERROR" | "TEMPLATE_UNSUPPORTED" | "DYNAMIC_EXPRESSION" | "DYNAMIC_SCRIPT_SOURCE" | "SCRIPT_SOURCE_NOT_FOUND" | "LOOP_SOURCE_UNSUPPORTED" | "NESTED_LOOP_UNSUPPORTED" | "LOOP_MEMBER_UNSUPPORTED" | "MEMBER_NOT_FOUND" | "MEMBER_VALUE_DYNAMIC" | "ATTRIBUTE_VALUE_MISSING" | "RICH_TEXT_DYNAMIC_CONTENT" | "RICH_TEXT_UNSUPPORTED_STRUCTURE" | "RICH_TEXT_SOURCE_RANGE_UNRESOLVED" | "STRUCTURE_ROOT_UNSUPPORTED" | "STRUCTURE_CONTROL_FLOW_UNSUPPORTED" | "STRUCTURE_LOOP_INSTANCE_REQUIRED" | null
}

/** 描述节点所在循环的数据项级复制、删除能力。 */
export interface PageVisualEditLoopItemActions {
  "can_duplicate": boolean
  "can_delete": boolean
  "loop_node_id": string
  "collection_name": string
  "key_member": string
  "instances": PageVisualEditLoopItemLocation[]
  "readonly_reason"?: "SFC_PARSE_ERROR" | "TEMPLATE_UNSUPPORTED" | "DYNAMIC_EXPRESSION" | "DYNAMIC_SCRIPT_SOURCE" | "SCRIPT_SOURCE_NOT_FOUND" | "LOOP_SOURCE_UNSUPPORTED" | "NESTED_LOOP_UNSUPPORTED" | "LOOP_MEMBER_UNSUPPORTED" | "MEMBER_NOT_FOUND" | "MEMBER_VALUE_DYNAMIC" | "ATTRIBUTE_VALUE_MISSING" | "RICH_TEXT_DYNAMIC_CONTENT" | "RICH_TEXT_UNSUPPORTED_STRUCTURE" | "RICH_TEXT_SOURCE_RANGE_UNRESOLVED" | "STRUCTURE_ROOT_UNSUPPORTED" | "STRUCTURE_CONTROL_FLOW_UNSUPPORTED" | "STRUCTURE_LOOP_INSTANCE_REQUIRED" | null
}

/** 描述可由稳定 key 定位的循环数组项。 */
export interface PageVisualEditLoopItemLocation {
  "index": number
  "key": string | number
}

/** 与 Runtime VisualEditSfcManifest 完全对齐的单页源码分析结果。 */
export interface PageVisualEditManifest {
  "protocol_version": number
  "module_path": string
  "source_hash": string
  "root": PageVisualEditNode
  "diagnostics"?: PageVisualEditDiagnostic[]
  "tailwind_catalog": PageVisualEditTailwindCatalog
  "json_sources": PageVisualEditJsonSource[]
}

/** 描述保留 Vue 模板容器和组件语义的节点树。 */
export interface PageVisualEditNode {
  "node_id": string
  "kind": "root" | "element" | "component"
  "tag": string
  "source_range": PageVisualEditSourceRange
  "loop_context"?: PageVisualEditLoopContext | null
  "template_actions": PageVisualEditTemplateActions
  "loop_item_actions"?: PageVisualEditLoopItemActions | null
  "bindings"?: PageVisualEditBinding[]
  "children"?: PageVisualEditNode[]
}

/** 创建页面可视化编辑预览 artifact 的公开接口入参。 */
export interface PageVisualEditPreviewArtifactCreateRequest {
  "protocolVersion": number
  "baseVersionNo": number
}

/** 创建页面可视化编辑预览 artifact 的公开接口响应。 */
export interface PageVisualEditPreviewArtifactResponse {
  "preview_url": string
  "artifact_id": string
  "preview_kind": string
  "entry_descriptor": PageVisualEditPreviewEntryDescriptor
  "viewport_width": number
  "viewport_height": number
  "project_id": number
  "workspace_id": number
  "visual_edit": PageVisualEditPreviewContext
}

/** 描述可视化预览 artifact 绑定的页面版本与源码 Manifest。 */
export interface PageVisualEditPreviewContext {
  "protocol_version": number
  "page_id": number
  "base_version_no": number
  "source_hash": string
  "module_path": string
  "manifest": PageVisualEditManifest
  "component_schemas": Record<string, unknown>
  "warnings"?: PageVisualEditDiagnostic[]
}

/** 限制可视化编辑 artifact 只能使用页面模块入口。 */
export interface PageVisualEditPreviewEntryDescriptor {
  "entry_type": string
  "module_path": string
  "route"?: null
}

/** 描述模板成员绑定与 const/ref/reactive 数组字面量的静态关系。 */
export interface PageVisualEditScriptArrayBindingSource {
  "kind": string
  "collection_name": string
  "collection_kind": "const-array" | "ref-array" | "reactive-array"
  "item_alias": string
  "member": string
  "key_member"?: string | null
  "locations"?: PageVisualEditScriptMemberLocation[]
}

/** 描述 script setup 数组中单个成员的静态写入位置。 */
export interface PageVisualEditScriptMemberLocation {
  "index": number
  "key"?: string | number | null
  "value"?: string | number | number | boolean | null
  "source_range"?: PageVisualEditSourceRange | null
  "editable": boolean
  "readonly_reason"?: "SFC_PARSE_ERROR" | "TEMPLATE_UNSUPPORTED" | "DYNAMIC_EXPRESSION" | "DYNAMIC_SCRIPT_SOURCE" | "SCRIPT_SOURCE_NOT_FOUND" | "LOOP_SOURCE_UNSUPPORTED" | "NESTED_LOOP_UNSUPPORTED" | "LOOP_MEMBER_UNSUPPORTED" | "MEMBER_NOT_FOUND" | "MEMBER_VALUE_DYNAMIC" | "ATTRIBUTE_VALUE_MISSING" | "RICH_TEXT_DYNAMIC_CONTENT" | "RICH_TEXT_UNSUPPORTED_STRUCTURE" | "RICH_TEXT_SOURCE_RANGE_UNRESOLVED" | "STRUCTURE_ROOT_UNSUPPORTED" | "STRUCTURE_CONTROL_FLOW_UNSUPPORTED" | "STRUCTURE_LOOP_INSTANCE_REQUIRED" | null
}

/** 原子替换 Manifest 中一个去重的静态 JSON 源。 */
export interface PageVisualEditSetJsonOperation {
  "type": string
  "sourceId": string
  "value": JsonValue
}

/** 设置文本容器内部的受限语义化 HTML。 */
export interface PageVisualEditSetRichTextOperation {
  "nodeId": string
  "instancePath"?: PageVisualEditInstancePathSegment[]
  "bindingId": string
  "type": string
  "html": string
}

/** 通过受控样式组批量更新一个 class 绑定。 */
export interface PageVisualEditSetTailwindTokensOperation {
  "nodeId": string
  "instancePath"?: PageVisualEditInstancePathSegment[]
  "bindingId": string
  "type": string
  "changes": PageVisualEditTailwindTokenChange[]
}

/** 设置静态文本、简单组件参数或静态数组成员的字面量。 */
export interface PageVisualEditSetValueOperation {
  "nodeId": string
  "instancePath"?: PageVisualEditInstancePathSegment[]
  "bindingId": string
  "type": string
  "value": string | number | number | boolean | null
}

/** 描述节点或绑定在 Vue SFC 中的 UTF-16 半开偏移区间。 */
export interface PageVisualEditSourceRange {
  "start": number
  "end": number
}

/** 描述 Runtime 提供的版本化 Tailwind 可视化编辑白名单。 */
export interface PageVisualEditTailwindCatalog {
  "version": number
  "groups"?: PageVisualEditTailwindGroup[]
}

/** 描述一个互斥 Tailwind 样式组及其可视化选项。 */
export interface PageVisualEditTailwindGroup {
  "key": string
  "label": string
  "options"?: PageVisualEditTailwindOption[]
}

/** 描述可视化样式面板允许选择的单个 Tailwind class。 */
export interface PageVisualEditTailwindOption {
  "class_name": string
  "label": string
}

/** 按互斥样式组设置或移除一个受支持的 Tailwind class。 */
export interface PageVisualEditTailwindTokenChange {
  "group": string
  "className"?: string | null
}

/** 描述节点模板级复制、删除能力。 */
export interface PageVisualEditTemplateActions {
  "can_duplicate": boolean
  "can_delete": boolean
  "readonly_reason"?: "SFC_PARSE_ERROR" | "TEMPLATE_UNSUPPORTED" | "DYNAMIC_EXPRESSION" | "DYNAMIC_SCRIPT_SOURCE" | "SCRIPT_SOURCE_NOT_FOUND" | "LOOP_SOURCE_UNSUPPORTED" | "NESTED_LOOP_UNSUPPORTED" | "LOOP_MEMBER_UNSUPPORTED" | "MEMBER_NOT_FOUND" | "MEMBER_VALUE_DYNAMIC" | "ATTRIBUTE_VALUE_MISSING" | "RICH_TEXT_DYNAMIC_CONTENT" | "RICH_TEXT_UNSUPPORTED_STRUCTURE" | "RICH_TEXT_SOURCE_RANGE_UNRESOLVED" | "STRUCTURE_ROOT_UNSUPPORTED" | "STRUCTURE_CONTROL_FLOW_UNSUPPORTED" | "STRUCTURE_LOOP_INSTANCE_REQUIRED" | null
}

/** 标识绑定值直接来自 Vue template 字面量。 */
export interface PageVisualEditTemplateBindingSource {
  "kind": string
}

/** 标识绑定覆盖模板元素内部的受限富文本片段。 */
export interface PageVisualEditTemplateRichTextBindingSource {
  "kind": string
}

export interface PagedResponse_AssetResponse_ {
  "items": AssetResponse[]
  "total": number
  "page": number
  "page_size": number
}

export interface PagedResponse_PageItem_ {
  "items": PageItem[]
  "total": number
  "page": number
  "page_size": number
}

export interface PagedResponse_ProjectItem_ {
  "items": ProjectItem[]
  "total": number
  "page": number
  "page_size": number
}

export interface PagedResponse_Union_WorkspaceComponentItem__SuggestedComponentItem__ {
  "items": (WorkspaceComponentItem | SuggestedComponentItem)[]
  "total": number
  "page": number
  "page_size": number
}

export interface PagedResponse_WorkspaceComponentItem_ {
  "items": WorkspaceComponentItem[]
  "total": number
  "page": number
  "page_size": number
}

export interface PagedResponse_WorkspaceFontConfigResponse_ {
  "items": WorkspaceFontConfigResponse[]
  "total": number
  "page": number
  "page_size": number
}

export interface PagedResponse_WorkspaceFontFamilyResponse_ {
  "items": WorkspaceFontFamilyResponse[]
  "total": number
  "page": number
  "page_size": number
}

export interface PagedResponse_WorkspaceItem_ {
  "items": WorkspaceItem[]
  "total": number
  "page": number
  "page_size": number
}

export interface PagedResponse_WorkspaceStyleItem_ {
  "items": WorkspaceStyleItem[]
  "total": number
  "page": number
  "page_size": number
}

export interface PagedResponse_WorkspaceThemeItem_ {
  "items": WorkspaceThemeItem[]
  "total": number
  "page": number
  "page_size": number
}

/** 项目和样式持久化时共用的完整展示配置。 */
export interface PresentationConfig {
  "page_width"?: number
  "page_height"?: number
  "base_font_size"?: string
  "icon_default_stroke_width"?: number
  "show_pdf_export_button"?: boolean
  "menu_mode"?: "text" | "preview" | "bottom-preview"
  "theme_key"?: string | null
  "style_spec_markdown"?: string
}

/** 展示配置部分更新；显式 null 仅允许用于 theme_key。 */
export interface PresentationConfigPatch {
  "page_width"?: number | null
  "page_height"?: number | null
  "base_font_size"?: string | null
  "icon_default_stroke_width"?: number | null
  "show_pdf_export_button"?: boolean | null
  "menu_mode"?: "text" | "preview" | "bottom-preview" | null
  "theme_key"?: string | null
  "style_spec_markdown"?: string | null
}

/** 项目/页面预览 artifact 创建请求。 */
export interface PreviewArtifactCreateRequest {
  "entry_descriptor"?: PreviewEntryDescriptor | null
}

/** 统一的预览 artifact 创建响应。 */
export interface PreviewArtifactResponse {
  "preview_url": string
  "artifact_id": string
  "preview_kind": "project" | "page" | "component" | "asset"
  "entry_descriptor": PreviewEntryDescriptor
  "viewport_width": number
  "viewport_height": number
  "project_id"?: number | null
  "workspace_id"?: number | null
  "component_preview_mode"?: "saved" | "draft" | null
  "component_source"?: "workspace_component" | "runtime_kit" | null
  "component_code"?: string | null
  "component_version_no"?: number | null
  "runtime_kit_component_name"?: string | null
  "runtime_kit_manifest_version"?: string | null
  "asset_id"?: number | null
  "asset_name"?: string | null
}

/** 预览入口描述，用于区分项目路由、单页面模块和组件宿主页。 */
export interface PreviewEntryDescriptor {
  "entry_type": "route" | "module" | "component_host" | "asset_host"
  "route"?: string | null
  "module_path"?: string | null
}

/** Runtime 用 PreviewContextToken 换取短期服务令牌的内部请求。 */
export interface PreviewServiceTokenExchangeRequest {
  "preview_token": string
}

/** 换票结果：artifact 作用域的短期 Runtime 服务令牌。 */
export interface PreviewServiceTokenExchangeResponse {
  "service_token": string
  "token_type"?: string
  "expires_in": number
  "artifact_id": string
  "scope"?: string
}

/** 用户可维护的预览尺寸规格预设。 */
export interface PreviewSizePreset {
  "name": string
  "width": number
  "height": number
  "base_font_size"?: string
  "icon_default_stroke_width"?: number
}

/** 更新当前登录用户预设尺寸的入参。 */
export interface PreviewSizePresetUpdateRequest {
  "presets"?: PreviewSizePreset[]
}

/** 项目当前构建资源引用摘要，用于前端区分自动包含资源和额外资源。 */
export interface ProjectBuildAssetSummary {
  "automatic_asset_names"?: string[]
  "extra_asset_names"?: string[]
  "included_asset_names"?: string[]
  "dynamic_module_paths"?: string[]
}

/** 创建项目整包构建任务的请求。 */
export interface ProjectBuildCreateRequest {
  "base_url"?: string
}

/** 项目级构建额外资源配置，供整包构建补充动态资源依赖。 */
export interface ProjectBuildExtraAssetsConfig {
  "asset_names"?: string[]
}

/** 项目整包构建任务响应。 */
export interface ProjectBuildJobResponse {
  "id": number
  "project_id": number
  "snapshot_release_id": number
  "base_url": string
  "status": "pending" | "running" | "succeeded" | "failed"
  "error_message": string | null
  "artifact_storage_key": string | null
  "artifact_download_url": string | null
  "artifact_proxy_url"?: string | null
  "artifact_entry_file": string | null
  "artifact_sha256": string | null
  "artifact_size_bytes": number | null
  "created_by": number | null
  "created_at": string
  "updated_at": string
  "started_at": string | null
  "finished_at": string | null
  "attempt_id"?: string | null
  "attempt_count"?: number | null
  "max_attempts"?: number | null
}

/** 创建项目入参，展示配置通过明确初始化来源生成。 */
export interface ProjectCreateRequest {
  "workspace_id": number
  "name": string
  "description"?: string | null
  "status"?: RecordStatus
  "configuration"?: ProjectDefaultConfiguration | ProjectStyleConfiguration | ProjectCustomConfiguration
  "build_extra_assets_json"?: ProjectBuildExtraAssetsConfig
}

/** 使用显式完整配置初始化项目。 */
export interface ProjectCustomConfiguration {
  "presentation"?: PresentationConfig
  "suggested_components"?: SuggestedComponentsSelection
  "mode": string
}

/** 使用工作空间 default 样式初始化项目。 */
export interface ProjectDefaultConfiguration {
  "mode"?: string
}

/** 项目响应模型，同时返回所属工作空间信息。 */
export interface ProjectItem {
  "id": number
  "workspace_id": number
  "workspace_name": string
  "code": string
  "name": string
  "description": string | null
  "is_system_managed"?: boolean
  "status": RecordStatus
  "archived_at": string | null
  "page_width": number
  "page_height": number
  "base_font_size": string
  "icon_default_stroke_width": number
  "show_pdf_export_button": boolean
  "menu_mode": "text" | "preview" | "bottom-preview"
  "theme_key": string | null
  "style_spec_markdown": string
  "build_extra_assets_json": ProjectBuildExtraAssetsConfig
  "routed_page_count"?: number
  "total_page_count"?: number
  "first_page_title"?: string | null
  "first_page_screenshot_url"?: string | null
  "created_at": string
  "updated_at": string
  "created_by": number | null
  "updated_by": number | null
}

/** 部分修改项目已有样式快照。 */
export interface ProjectPatchConfiguration {
  "presentation"?: PresentationConfigPatch | null
  "suggested_components"?: SuggestedComponentsSelection | null
  "mode": string
}

/** 项目路由子页面响应模型。 */
export interface ProjectRouteChildItem {
  "id": number
  "route_type"?: string
  "route": string
  "order": number
  "hidden"?: boolean
  "page_id": number
  "page_code": string
  "page_title": string
  "display_title": string
}

/** 分组子页面路由写入模型，只允许绑定具体页面。 */
export interface ProjectRouteChildWrite {
  "route": string
  "order": number
  "hidden"?: boolean
  "page_id": number
}

/** 项目顶层路由写入模型，支持独立页面或页面分组。 */
export interface ProjectRouteItemWrite {
  "route_type": "group" | "page"
  "route": string
  "order": number
  "hidden"?: boolean
  "group_title"?: string | null
  "page_id"?: number | null
  "children"?: ProjectRouteChildWrite[]
}

/** 页面被项目路由引用时的路径绑定摘要。 */
export interface ProjectRoutePageBinding {
  "route_id": number
  "parent_route"?: string | null
  "route": string
  "full_path": string
  "parent_order"?: number | null
  "order": number
}

/** 项目顶层路由响应模型。 */
export interface ProjectRouteTreeItem {
  "id": number
  "route_type": "group" | "page"
  "route": string
  "order": number
  "hidden"?: boolean
  "group_title"?: string | null
  "page_id"?: number | null
  "page_code"?: string | null
  "page_title"?: string | null
  "display_title": string
  "children"?: ProjectRouteChildItem[]
}

/** 项目路由树查询响应。 */
export interface ProjectRouteTreeResponse {
  "routes"?: ProjectRouteTreeItem[]
}

/** 项目路由整树覆盖写入请求。 */
export interface ProjectRouteTreeWriteRequest {
  "routes"?: ProjectRouteItemWrite[]
}

/** 使用指定工作空间样式初始化或覆盖项目。 */
export interface ProjectStyleConfiguration {
  "mode": string
  "style_id": number
}

/** 项目建议引用资源摘要，避免向 AI 默认上下文暴露 URL 与标签。 */
export interface ProjectSuggestedReferenceAssetItem {
  "id": number
  "name": string
  "original_name": string
  "description"?: string | null
  "asset_type": AssetType
  "content_editable"?: boolean
  "approx_aspect_ratio"?: string | null
  "approx_aspect_ratio_value"?: number | null
  "aspect_ratio_source"?: string | null
}

/** 项目建议引用资源列表响应。 */
export interface ProjectSuggestedReferenceAssetsResponse {
  "items"?: ProjectSuggestedReferenceAssetItem[]
}

/** 覆盖保存项目建议引用资源的请求体。 */
export interface ProjectSuggestedReferenceAssetsUpdateRequest {
  "asset_ids"?: number[]
}

/** 导出项目模板包的请求。 */
export interface ProjectTemplateExportRequest {
  "metadata"?: ProjectTemplateMetadataPayload
  "cover_page_id"?: number | null
  "manual_asset_names"?: string[]
  "refresh_screenshots"?: boolean
}

/** 项目模板包导出预检结果。 */
export interface ProjectTemplateExportValidationResult {
  "can_export"?: boolean
  "project": ProjectTemplatePackageProjectSummary
  "pages"?: ProjectTemplatePackagePageSummary[]
  "components"?: ComponentShareExportComponentSummary[]
  "automatic_assets"?: ComponentShareExportAssetSummary[]
  "manual_assets"?: ComponentShareExportAssetSummary[]
  "themes"?: WorkspaceStylePackageThemeSummary[]
  "fonts"?: ComponentSharePackageFontSummary[]
  "screenshots"?: ProjectTemplateScreenshotSummary
  "warnings"?: string[]
  "errors"?: string[]
  "missing_static_asset_names"?: string[]
  "missing_manual_asset_names"?: string[]
  "dynamic_resource_modules"?: string[]
}

/** 项目模板包正式导入结果。 */
export interface ProjectTemplateImportResult {
  "project_id": number
  "project_code": string
  "project_name": string
  "page_ids"?: number[]
  "pages"?: ProjectTemplatePackagePageSummary[]
  "components"?: ComponentSharePackageComponentSummary[]
  "assets"?: ComponentSharePackageAssetSummary[]
  "themes"?: WorkspaceStylePackageThemeSummary[]
  "fonts"?: ComponentSharePackageFontSummary[]
  "warnings"?: string[]
}

/** 项目模板包导入预检结果。 */
export interface ProjectTemplateImportValidationResult {
  "valid": boolean
  "schema_version"?: number | null
  "runtime_kit_manifest_version"?: string | null
  "template"?: Record<string, unknown>
  "project"?: ProjectTemplatePackageProjectSummary | null
  "pages"?: ProjectTemplatePackagePageSummary[]
  "components"?: ComponentSharePackageComponentSummary[]
  "assets"?: ComponentSharePackageAssetSummary[]
  "themes"?: WorkspaceStylePackageThemeSummary[]
  "fonts"?: ComponentSharePackageFontSummary[]
  "screenshots"?: ProjectTemplateScreenshotSummary
  "errors"?: string[]
  "warnings"?: string[]
}

/** 模板展示元数据，只允许覆盖当前项目实际存在或可派生的展示字段。 */
export interface ProjectTemplateMetadataPayload {
  "slug"?: string | null
  "name"?: string | null
  "summary"?: string | null
  "description"?: string | null
}

/** 模板包中的页面摘要。 */
export interface ProjectTemplatePackagePageSummary {
  "source_page_code": string
  "title": string
  "summary"?: string | null
  "file_type": PageFileType
  "action"?: string
}

/** 模板包中的项目摘要。 */
export interface ProjectTemplatePackageProjectSummary {
  "source_project_code": string
  "name": string
  "description"?: string | null
  "page_width": number
  "page_height": number
  "base_font_size": string
  "icon_default_stroke_width": number
  "show_pdf_export_button": boolean
  "menu_mode": "text" | "preview" | "bottom-preview"
  "theme_key"?: string | null
  "style_spec_markdown"?: string
}

/** 模板截图摘要。 */
export interface ProjectTemplateScreenshotItem {
  "path": string
  "width": number
  "height": number
  "source_page_code"?: string | null
  "title"?: string | null
  "order"?: number | null
}

/** 模板包截图摘要，包含封面和页面截图数量。 */
export interface ProjectTemplateScreenshotSummary {
  "cover"?: ProjectTemplateScreenshotItem | null
  "pages"?: ProjectTemplateScreenshotItem[]
}

/** 更新项目入参，项目专属字段与共享样式配置明确分层。 */
export interface ProjectUpdateRequest {
  "workspace_id"?: number | null
  "name"?: string | null
  "description"?: string | null
  "status"?: RecordStatus | null
  "configuration"?: ProjectPatchConfiguration | ProjectStyleConfiguration | null
  "build_extra_assets_json"?: ProjectBuildExtraAssetsConfig | null
}

/** 单次聊天 Run 的推理策略。 */
export interface ReasoningPolicy {
  "mode"?: "auto" | "disabled" | "effort" | "budget_tokens"
  "value"?: string | number | null
}

/** 业务资源状态，用于控制启用与归档展示。 */
export type RecordStatus = "active" | "archived"

/** 重命名或自动命名 Agent 会话的请求体。 */
export interface RenameAgentSessionRequest {
  "session_name"?: string | null
  "autogenerate"?: boolean
}

/** Runtime Kit 内建能力目录项。 */
export interface RuntimeKitCapabilityItem {
  "kind": "component" | "composable" | "util" | "type"
  "base_name": string
  "version_no": number
  "name": string
  "import_path": string
  "category": string
  "description": string
  "display_name": string
  "summary": string
  "tags": string[]
  "previewable": boolean
  "preview_schema"?: Record<string, unknown> | null
  "preview_options"?: Record<string, unknown> | null
  "usage": string[]
  "returns"?: string | null
  "return_example": string[]
  "constraints": string[]
  "audiences": ("backend" | "agent")[]
  "manifest_version": string
}

/** Runtime Kit 内建能力列表响应。 */
export interface RuntimeKitCapabilityListResponse {
  "items": RuntimeKitCapabilityItem[]
  "total": number
  "manifest_version"?: string | null
}

/** 创建 Runtime Kit 内建组件预览 artifact 的入参。 */
export interface RuntimeKitComponentPreviewRequest {
  "workspace_id": number
  "preview_options"?: ComponentPreviewOptions | null
}

/** Runtime 批量读取 artifact 模块的内部请求。 */
export interface RuntimeModuleBatchRequest {
  "paths": string[]
}

/** 完整样式快照，供样式创建和项目自定义初始化使用。 */
export interface StyleConfiguration {
  "presentation"?: PresentationConfig
  "suggested_components"?: SuggestedComponentsSelection
}

/** 样式快照补丁；建议组件一旦出现即执行完整替换。 */
export interface StyleConfigurationPatch {
  "presentation"?: PresentationConfigPatch | null
  "suggested_components"?: SuggestedComponentsSelection | null
}

/** 建议组件摘要，用于样式关联、项目快照和内容助手组件查询。 */
export interface SuggestedComponentItem {
  "id": number
  "code": string
  "name": string
  "import_name": string
  "component_type": WorkspaceComponentType
  "summary": string | null
  "current_version_no": number
  "available"?: boolean
  "unavailable_reason"?: string | null
}

/** 建议组件列表响应。 */
export interface SuggestedComponentsResponse {
  "items"?: SuggestedComponentItem[]
}

/** 有序建议组件选择；空数组表示清空。 */
export interface SuggestedComponentsSelection {
  "component_ids"?: number[]
}

/** 主题背景色板。 */
export interface ThemeBackgroundPalette {
  "default": string
  "invert": string
}

/** 主题边框色板。 */
export interface ThemeBorderPalette {
  "default": string
  "subtle": string
}

/** 主题链接色板。 */
export interface ThemeLinkPalette {
  "default": string
  "hover": string
  "visited": string
}

/** 主题总色板结构。 */
export interface ThemePalette {
  "text": ThemeTextPalette
  "background": ThemeBackgroundPalette
  "border": ThemeBorderPalette
  "link": ThemeLinkPalette
  "accent": string[]
}

/** 主题文字色板。 */
export interface ThemeTextPalette {
  "primary": string
  "secondary": string
  "invert": string
}

/** 更新只影响后续 Run 的会话焦点与项目工作集偏好。 */
export interface UpdateAgentSessionPreferencesRequest {
  "focus_mode": "follow_route" | "pinned_project" | "workspace"
  "pinned_project_id"?: number | null
  "work_scope_mode": "workspace" | "selected_projects"
  "allowed_project_ids"?: number[]
}

/** 平台管理员创建用户的请求。 */
export interface UserCreateRequest {
  "username": string
  "password": string
  "display_name": string
  "role"?: UserRole
  "status"?: RecordStatus
}

/** 平台用户列表与详情响应。 */
export interface UserItem {
  "id": number
  "username": string
  "display_name": string
  "role": UserRole
  "status": RecordStatus
  "last_login_at": string | null
  "created_at": string
  "updated_at": string
}

/** 平台管理员重置用户密码的请求。 */
export interface UserResetPasswordRequest {
  "new_password": string
}

/** 平台账号角色，用于区分平台治理与普通工作空间用户。 */
export type UserRole = "platform_admin" | "workspace_user"

/** 平台管理员更新用户资料、角色或状态的请求。 */
export interface UserUpdateRequest {
  "display_name"?: string | null
  "role"?: UserRole | null
  "status"?: RecordStatus | null
}

export interface ValidationError {
  "loc": (string | number)[]
  "msg": string
  "type": string
  "input"?: unknown
  "ctx"?: Record<string, unknown>
}

/** 组件当前发布版本对另一个工作空间组件的直接引用项。 */
export interface WorkspaceComponentComponentReferenceItem {
  "component_id": number
  "component_code": string
  "component_name": string
  "current_version_no": number
  "component_version_id": number
  "referenced_component_version_no": number
  "has_unpublished_changes": boolean
  "draft_referenced_component_version_no"?: number | null
  "draft_is_current_version": boolean
  "is_current_version": boolean
  "can_upgrade": boolean
}

/** 创建工作空间组件入参，code 由后端自动生成。 */
export interface WorkspaceComponentCreateRequest {
  "workspace_id": number
  "content": string
  "file_type"?: PageFileType
  "name": string
  "import_name": string
  "component_type"?: WorkspaceComponentType
  "summary"?: string | null
  "preview_schema"?: string | null
  "status"?: RecordStatus
  "change_note"?: string | null
}

/** 工作空间组件当前版本依赖索引响应。 */
export interface WorkspaceComponentCurrentDependencies {
  "component_id": number
  "current_version_no": number
  "component_version_id": number | null
  "dependencies": WorkspaceComponentDependencyItem[]
}

/** 组件或页面当前版本的源码依赖项。 */
export interface WorkspaceComponentDependencyItem {
  "dependency_kind": string
  "component_code"?: string | null
  "component_version_no"?: number | null
  "runtime_module_path"?: string | null
  "runtime_kit_name"?: string | null
  "runtime_kit_base_name"?: string | null
  "runtime_kit_version_no"?: number | null
  "runtime_kit_import_path"?: string | null
}

/** 导出工作空间组件离线分享包的入参。 */
export interface WorkspaceComponentExportPackageRequest {
  "workspace_id": number
  "component_ids": number[]
  "manual_asset_names"?: string[]
}

/** 工作空间组件响应模型，当前源码字段表示可编辑草稿。 */
export interface WorkspaceComponentItem {
  "id": number
  "workspace_id": number
  "workspace_name"?: string | null
  "code": string
  "content": string
  "draft_hash"?: string | null
  "preview_schema": string | null
  "current_version_no": number
  "draft_base_version_no": number
  "has_unpublished_changes": boolean
  "published_at": string | null
  "file_type": PageFileType
  "name": string
  "import_name": string
  "component_type": WorkspaceComponentType
  "summary": string | null
  "status": RecordStatus
  "created_at": string
  "updated_at": string
  "created_by": number | null
  "updated_by": number | null
}

/** 页面当前版本对工作空间组件的直接引用项。 */
export interface WorkspaceComponentPageReferenceItem {
  "page_id": number
  "page_code": string
  "page_title": string
  "project_id"?: number | null
  "project_name"?: string | null
  "current_version_no": number
  "page_version_id": number
  "referenced_component_version_no": number
  "is_current_version": boolean
  "can_upgrade": boolean
}

/** 组件草稿发布入参，发布后生成可被外部引用的不可变版本。 */
export interface WorkspaceComponentPublishRequest {
  "release_name"?: string | null
  "change_note"?: string | null
}

/** 组件草稿引用升级成功项。 */
export interface WorkspaceComponentReferenceUpgradeComponentItem {
  "component_id": number
  "component_code": string
  "component_name": string
  "current_version_no": number
  "draft_referenced_component_version_no": number
}

/** 批量引用升级中的跳过或失败明细。 */
export interface WorkspaceComponentReferenceUpgradeIssue {
  "kind": string
  "id": number
  "code": string
  "detail": string
}

/** 页面引用升级成功项。 */
export interface WorkspaceComponentReferenceUpgradePageItem {
  "page_id": number
  "page_code": string
  "page_title": string
  "previous_version_no": number
  "current_version_no": number
}

/** 批量升级组件引用到目标组件当前发布版本的入参。 */
export interface WorkspaceComponentReferenceUpgradeRequest {
  "page_ids"?: number[]
  "component_ids"?: number[]
}

/** 批量升级组件引用的结果汇总。 */
export interface WorkspaceComponentReferenceUpgradeResponse {
  "updated_pages"?: WorkspaceComponentReferenceUpgradePageItem[]
  "updated_components"?: WorkspaceComponentReferenceUpgradeComponentItem[]
  "skipped"?: WorkspaceComponentReferenceUpgradeIssue[]
  "failures"?: WorkspaceComponentReferenceUpgradeIssue[]
}

/** 工作空间组件被页面与组件直接引用的当前索引汇总。 */
export interface WorkspaceComponentReferences {
  "component_id": number
  "component_code": string
  "current_version_no": number
  "page_references": WorkspaceComponentPageReferenceItem[]
  "component_references": WorkspaceComponentComponentReferenceItem[]
}

/** 将指定发布版本恢复为草稿时的入参。 */
export interface WorkspaceComponentRestoreDraftRequest {
  "change_note"?: string | null
}

/** 基于未保存源码生成组件草稿预览的入参。 */
export interface WorkspaceComponentSourcePreviewRequest {
  "workspace_id": number
  "component_id"?: number | null
  "component_name"?: string | null
  "content": string
  "preview_schema"?: string | null
  "preview_options"?: ComponentPreviewOptions | null
  "file_type"?: PageFileType
}

/** 工作空间组件固定分类，用于约束组件库筛选与元数据维护。 */
export type WorkspaceComponentType = "页面组件" | "内容组件" | "原子组件"

/** 更新工作空间组件入参，支持元数据和源码局部更新。 */
export interface WorkspaceComponentUpdateRequest {
  "workspace_id"?: number | null
  "content"?: string | null
  "file_type"?: PageFileType | null
  "name"?: string | null
  "import_name"?: string | null
  "component_type"?: WorkspaceComponentType | null
  "summary"?: string | null
  "preview_schema"?: string | null
  "status"?: RecordStatus | null
  "change_note"?: string | null
}

/** 工作空间组件发布版本完整内容。 */
export interface WorkspaceComponentVersionContent {
  "component_id": number
  "version_no": number
  "version_label": string
  "release_name": string | null
  "file_type": PageFileType
  "is_current": boolean
  "content": string
  "preview_schema": string | null
  "change_note": string | null
  "created_at": string
  "created_by": number | null
}

/** 工作空间组件发布版本列表项。 */
export interface WorkspaceComponentVersionListItem {
  "id": number
  "component_id": number
  "version_no": number
  "version_label": string
  "release_name": string | null
  "file_type": PageFileType
  "is_current": boolean
  "content_size": number
  "change_note": string | null
  "created_at": string
  "created_by": number | null
}

/** 创建工作空间入参，code 由后端自动生成。 */
export interface WorkspaceCreateRequest {
  "name": string
  "description"?: string | null
  "status"?: RecordStatus
  "default_theme_key"?: string | null
}

/** 创建字体文件配置的请求模型，按 family 名归属（不存在时自动创建）。 */
export interface WorkspaceFontConfigCreateRequest {
  "asset_id": number
  "family_name": string
  "font_format"?: string | null
  "font_weight"?: string
  "font_style"?: string
  "font_display"?: string
  "status"?: RecordStatus
}

/** 字体文件配置响应模型，font_family 由所属字体族名派生。 */
export interface WorkspaceFontConfigResponse {
  "id": number
  "workspace_id": number
  "family_id": number
  "asset_id": number
  "asset_name": string
  "font_family": string
  "font_format": string
  "font_weight": string
  "font_style": string
  "font_display": string
  "status": RecordStatus
  "asset_url"?: string | null
  "created_at": string
  "updated_at": string
}

/** 更新字体文件配置的请求模型；修改 family_name 即把 face 移动到目标字体族。 */
export interface WorkspaceFontConfigUpdateRequest {
  "family_name"?: string | null
  "font_format"?: string | null
  "font_weight"?: string | null
  "font_style"?: string | null
  "font_display"?: string | null
  "status"?: RecordStatus | null
}

/** 字体族响应模型，内嵌该族全部字体文件（face）。 */
export interface WorkspaceFontFamilyResponse {
  "id": number
  "workspace_id": number
  "name": string
  "faces"?: WorkspaceFontConfigResponse[]
  "created_at": string
  "updated_at": string
}

/** 重命名字体族的请求模型。 */
export interface WorkspaceFontFamilyUpdateRequest {
  "name": string
}

/** 工作空间响应模型，包含常用列表字段。 */
export interface WorkspaceItem {
  "id": number
  "code": string
  "name": string
  "description": string | null
  "status": RecordStatus
  "last_opened_at": string | null
  "default_theme_key": string | null
  "created_at": string
  "updated_at": string
  "created_by": number | null
  "updated_by": number | null
}

/** 复制样式请求。 */
export interface WorkspaceStyleCopyRequest {
  "key"?: string | null
  "name"?: string | null
}

/** 创建样式请求。 */
export interface WorkspaceStyleCreateRequest {
  "key": string
  "name": string
  "description"?: string | null
  "configuration"?: StyleConfiguration
}

/** 样式离线包导出预检中的资源摘要。 */
export interface WorkspaceStyleExportAssetSummary {
  "name": string
  "original_name": string
  "asset_type": string
  "file_hash": string
  "source"?: string
}

/** 导出样式离线包请求。 */
export interface WorkspaceStyleExportPackageRequest {
  "style_ids": number[]
  "manual_asset_names"?: string[]
}

/** 样式离线包导出预检结果。 */
export interface WorkspaceStyleExportValidationResult {
  "can_export"?: boolean
  "automatic_assets"?: WorkspaceStyleExportAssetSummary[]
  "manual_assets"?: WorkspaceStyleExportAssetSummary[]
  "fonts"?: WorkspaceStylePackageFontSummary[]
  "warnings"?: string[]
  "missing_static_asset_names"?: string[]
  "missing_manual_asset_names"?: string[]
  "dynamic_resource_components"?: string[]
}

/** 样式离线包正式导入结果。 */
export interface WorkspaceStyleImportResult {
  "styles"?: WorkspaceStylePackageStyleSummary[]
  "themes"?: WorkspaceStylePackageThemeSummary[]
  "assets"?: WorkspaceStylePackageAssetSummary[]
  "fonts"?: WorkspaceStylePackageFontSummary[]
  "components"?: WorkspaceStylePackageComponentSummary[]
  "warnings"?: string[]
}

/** 样式离线包导入预检结果。 */
export interface WorkspaceStyleImportValidationResult {
  "valid": boolean
  "schema_version"?: number | null
  "styles"?: WorkspaceStylePackageStyleSummary[]
  "themes"?: WorkspaceStylePackageThemeSummary[]
  "assets"?: WorkspaceStylePackageAssetSummary[]
  "fonts"?: WorkspaceStylePackageFontSummary[]
  "components"?: WorkspaceStylePackageComponentSummary[]
  "errors"?: string[]
  "warnings"?: string[]
}

/** 工作空间样式响应模型。 */
export interface WorkspaceStyleItem {
  "id": number
  "workspace_id": number
  "key": string
  "name": string
  "description": string | null
  "page_width": number
  "page_height": number
  "base_font_size": string
  "icon_default_stroke_width": number
  "show_pdf_export_button": boolean
  "menu_mode": "text" | "preview" | "bottom-preview"
  "theme_key": string | null
  "style_spec_markdown": string
  "created_at": string
  "updated_at": string
  "created_by": number | null
  "updated_by": number | null
}

/** 样式离线包中的资源摘要。 */
export interface WorkspaceStylePackageAssetSummary {
  "name": string
  "original_name": string
  "asset_type": string
  "file_hash": string
  "action"?: string
}

/** 样式离线包中的组件摘要。 */
export interface WorkspaceStylePackageComponentSummary {
  "source_component_code": string
  "source_version_no": number
  "name": string
  "import_name": string
  "component_type": string
  "dependencies"?: string[]
  "component_fingerprint"?: string | null
  "matched_component_id"?: number | null
  "matched_component_code"?: string | null
  "action"?: string
  "match_reason"?: string | null
}

/** 样式离线包中的字体配置摘要。 */
export interface WorkspaceStylePackageFontSummary {
  "asset_name": string
  "font_family": string
  "font_format": string
  "font_weight": string
  "font_style": string
  "font_display": string
  "status": string
  "action"?: string
}

/** 样式离线包中的样式摘要。 */
export interface WorkspaceStylePackageStyleSummary {
  "key": string
  "name": string
  "theme_key"?: string | null
  "page_width": number
  "page_height": number
  "base_font_size": string
  "icon_default_stroke_width": number
  "show_pdf_export_button": boolean
  "menu_mode": "text" | "preview" | "bottom-preview"
  "style_spec_markdown"?: string
  "action"?: string
}

/** 样式离线包中的主题摘要。 */
export interface WorkspaceStylePackageThemeSummary {
  "key": string
  "name": string
  "action"?: string
}

/** 更新样式请求，key 创建后不可修改。 */
export interface WorkspaceStyleUpdateRequest {
  "name"?: string | null
  "description"?: string | null
  "configuration"?: StyleConfigurationPatch | null
}

/** 主题响应中的资产摘要。 */
export interface WorkspaceThemeAssetSummary {
  "id": number
  "name": string
  "original_name": string
  "asset_type": string
  "analysis_metadata"?: AssetAnalysisMetadata | null
  "url"?: string | null
}

/** 复制主题请求。 */
export interface WorkspaceThemeCopyRequest {
  "key"?: string | null
  "name"?: string | null
}

/** 创建主题请求。 */
export interface WorkspaceThemeCreateRequest {
  "key": string
  "name": string
  "description"?: string | null
  "logo_asset_id"?: number | null
  "invert_logo_asset_id"?: number | null
  "project_icon_asset_id"?: number | null
  "heading_font_family_id"?: number | null
  "body_font_family_id"?: number | null
  "code_font_family_id"?: number | null
  "heading_font_preset"?: string | null
  "body_font_preset"?: string | null
  "code_font_preset"?: string | null
  "palette": ThemePalette
}

/** 主题响应中的字体族摘要。 */
export interface WorkspaceThemeFontFamilySummary {
  "id": number
  "name": string
}

/** 工作空间主题响应模型。 */
export interface WorkspaceThemeItem {
  "id": number
  "workspace_id": number
  "key": string
  "name": string
  "description": string | null
  "logo_asset_id": number | null
  "invert_logo_asset_id": number | null
  "project_icon_asset_id": number | null
  "project_icon_name": string | null
  "heading_font_family_id": number | null
  "body_font_family_id": number | null
  "code_font_family_id": number | null
  "heading_font_label"?: string | null
  "body_font_label"?: string | null
  "code_font_label"?: string | null
  "heading_font_preset"?: string | null
  "body_font_preset"?: string | null
  "code_font_preset"?: string | null
  "palette": ThemePalette
  "logo_asset"?: WorkspaceThemeAssetSummary | null
  "invert_logo_asset"?: WorkspaceThemeAssetSummary | null
  "project_icon_asset"?: WorkspaceThemeAssetSummary | null
  "heading_font_family"?: WorkspaceThemeFontFamilySummary | null
  "body_font_family"?: WorkspaceThemeFontFamilySummary | null
  "code_font_family"?: WorkspaceThemeFontFamilySummary | null
  "resolved_theme_config_yaml": string
  "created_at": string
  "updated_at": string
  "created_by": number | null
  "updated_by": number | null
}

/** 更新主题请求。 */
export interface WorkspaceThemeUpdateRequest {
  "key"?: string | null
  "name"?: string | null
  "description"?: string | null
  "logo_asset_id"?: number | null
  "invert_logo_asset_id"?: number | null
  "project_icon_asset_id"?: number | null
  "heading_font_family_id"?: number | null
  "body_font_family_id"?: number | null
  "code_font_family_id"?: number | null
  "heading_font_preset"?: string | null
  "body_font_preset"?: string | null
  "code_font_preset"?: string | null
  "palette"?: ThemePalette | null
}

/** 更新工作空间入参，允许局部更新核心元数据（code 不可修改）。 */
export interface WorkspaceUpdateRequest {
  "name"?: string | null
  "description"?: string | null
  "status"?: RecordStatus | null
  "default_theme_key"?: string | null
}

export type GeneratedApiSchemaName = "AgentActiveRunItem" | "AgentCancelRunRequest" | "AgentCancelRunResponse" | "AgentCatalogItem" | "AgentCodeStandardConfigItem" | "AgentCodeStandardUpdateRequest" | "AgentConfigItem" | "AgentConfigUpdateRequest" | "AgentContextStatusItem" | "AgentContinueRunRequest" | "AgentDescriptor" | "AgentFocusRequest" | "AgentImageAttachmentItem" | "AgentImageAttachmentPromoteRequest" | "AgentMessageAttachmentItem" | "AgentMessageItem" | "AgentPendingRequirement" | "AgentRunContextSummary" | "AgentRunProjectSummary" | "AgentRunRequest" | "AgentRunStartResponse" | "AgentScopeContext" | "AgentSessionItem" | "AgentSessionRuntimeSnapshot" | "AgentSuggestedPatch" | "AgentTimelineItem" | "AgentTimelineToolItem" | "AgentToolConfigItem" | "AgentToolConfigUpdateRequest" | "AgentToolGroupConfigItem" | "AgentToolGuideItem" | "AiLlmConfigScope" | "ApiAccessTokenCreateRequest" | "ApiAccessTokenCreateResponse" | "ApiAccessTokenItem" | "ApiAccessTokenListResponse" | "ApiAccessTokenUpdateRequest" | "AssetAnalysisMetadata" | "AssetArchiveRequest" | "AssetBatchArchiveRequest" | "AssetBatchDeleteRequest" | "AssetBatchOperationFailure" | "AssetBatchOperationResponse" | "AssetBatchRestoreRequest" | "AssetContentCreateRequest" | "AssetContentPreviewRequest" | "AssetContentPreviewResponse" | "AssetContentResponse" | "AssetContentUpdateRequest" | "AssetCopyRequest" | "AssetFontConfigSummary" | "AssetIconAnalysisPayload" | "AssetPackageExportRequest" | "AssetPackageImportFailure" | "AssetPackageImportItem" | "AssetPackageImportResult" | "AssetReferenceSummary" | "AssetRenderHintBackfillFailure" | "AssetRenderHintBackfillJobCreateRequest" | "AssetRenderHintBackfillJobGroupResponse" | "AssetRenderHintBackfillJobResponse" | "AssetResponse" | "AssetRestoreRequest" | "AssetRole" | "AssetType" | "AssetUpdateRequest" | "AuthUser" | "Body_create_project_template_package_preview_artifact_api_workspaces__workspace_id__template_packages_preview_artifact_post" | "Body_import_component_package_api_components_import_package_post" | "Body_import_project_template_package_api_workspaces__workspace_id__template_packages_import_post" | "Body_import_workspace_asset_package_api_workspaces__workspace_id__assets_import_package_post" | "Body_import_workspace_style_package_api_workspaces__workspace_id__styles_import_package_post" | "Body_replace_workspace_asset_file_api_workspaces__workspace_id__assets__asset_id__replace_post" | "Body_upload_agent_image_attachment_api_ai_sessions__session_id__attachments_images_post" | "Body_upload_asset_api_v1_assets_post" | "Body_upload_asset_file_api_workspaces__workspace_id__assets_upload_post" | "Body_validate_component_package_import_api_components_import_package_validate_post" | "Body_validate_project_template_package_import_api_workspaces__workspace_id__template_packages_import_validate_post" | "Body_validate_workspace_style_package_import_api_workspaces__workspace_id__styles_import_package_validate_post" | "BuildJobClaimRequest" | "BuildJobClaimResponse" | "BuildJobCompleteRequest" | "ChangePasswordRequest" | "ChatBindingItem" | "ChatBindingUpdate" | "ChatModelCatalogItem" | "ChatModelConfigCreate" | "ChatModelConfigItem" | "ChatModelConfigUpdate" | "ChatProviderCatalogItem" | "ChatProviderConfigCreate" | "ChatProviderConfigItem" | "ChatProviderConfigUpdate" | "ClientErrorLogRequest" | "ComponentPreviewOptions" | "ComponentPreviewPageOptions" | "ComponentPreviewPlacementOptions" | "ComponentShareExportAssetSummary" | "ComponentShareExportComponentSummary" | "ComponentShareExportValidationResult" | "ComponentShareImportResult" | "ComponentShareImportValidationResult" | "ComponentSharePackageAssetSummary" | "ComponentSharePackageComponentSummary" | "ComponentSharePackageFontSummary" | "CreateAgentSessionRequest" | "ExternalAssetContentCreateRequest" | "ExternalAssetContentPreviewRequest" | "ExternalAssetContentUpdateRequest" | "ExternalAssetCopyRequest" | "ExternalBatchArchiveRequest" | "ExternalBatchArchiveResponse" | "ExternalCapabilitiesResponse" | "ExternalComponentApplyEditsMutationRequest" | "ExternalComponentCreateMutationRequest" | "ExternalComponentMetadataMutationRequest" | "ExternalComponentMetadataUpdateRequest" | "ExternalEntityValidationRequest" | "ExternalEntityValidationResponse" | "ExternalErrorDetail" | "ExternalMutationJobResponse" | "ExternalPageApplyEditsMutationRequest" | "ExternalPageCopyRequest" | "ExternalPageCreateMutationRequest" | "ExternalPageMetadataUpdateRequest" | "ExternalPreviewArtifactCreateRequest" | "ExternalProjectApplyStyleRequest" | "ExternalProjectBuildAssetsRequest" | "ExternalProjectConfigurationResponse" | "ExternalProjectConfigurationUpdateRequest" | "ExternalProjectCreateRequest" | "ExternalStandardResponse" | "ExternalStyleCreateRequest" | "ExternalSystemHealthResponse" | "ExternalSystemVersionResponse" | "ExternalThemeCreateRequest" | "ExternalWhoAmIResponse" | "HTTPValidationError" | "ImageBindingItem" | "ImageBindingUpdate" | "ImageModelConfigCreate" | "ImageModelConfigItem" | "ImageModelConfigUpdate" | "ImageProviderCatalogItem" | "ImageProviderConfigCreate" | "ImageProviderConfigItem" | "ImageProviderConfigUpdate" | "JsonValue" | "LoginRequest" | "LoginResponse" | "MessageResponse" | "ModelCatalogSyncItem" | "PageComponentResourceItem" | "PageCopyToProjectRequest" | "PageCreateRequest" | "PageCurrentComponentIndex" | "PageCurrentModuleDependencies" | "PageFileType" | "PageItem" | "PageModuleDependencyItem" | "PageScreenshotBatchDownloadRequest" | "PageScreenshotBatchFailure" | "PageScreenshotBatchRefreshRequest" | "PageScreenshotBatchRefreshResponse" | "PageScreenshotJobGroupResponse" | "PageScreenshotJobRequest" | "PageScreenshotJobResponse" | "PageScreenshotRequest" | "PageSnapshotCreateRequest" | "PageUpdateRequest" | "PageVersionContent" | "PageVersionListItem" | "PageVersionRestoreRequest" | "PageVersionStorageType" | "PageVisualEditApplyDiagnostic" | "PageVisualEditApplyRequest" | "PageVisualEditApplyResponse" | "PageVisualEditBinding" | "PageVisualEditComponentPropField" | "PageVisualEditComponentSchema" | "PageVisualEditComponentSelectOption" | "PageVisualEditDeleteNodeOperation" | "PageVisualEditDiagnostic" | "PageVisualEditDuplicateNodeOperation" | "PageVisualEditInstancePathSegment" | "PageVisualEditJsonBindingSource" | "PageVisualEditJsonSource" | "PageVisualEditLoopContext" | "PageVisualEditLoopItemActions" | "PageVisualEditLoopItemLocation" | "PageVisualEditManifest" | "PageVisualEditNode" | "PageVisualEditPreviewArtifactCreateRequest" | "PageVisualEditPreviewArtifactResponse" | "PageVisualEditPreviewContext" | "PageVisualEditPreviewEntryDescriptor" | "PageVisualEditScriptArrayBindingSource" | "PageVisualEditScriptMemberLocation" | "PageVisualEditSetJsonOperation" | "PageVisualEditSetRichTextOperation" | "PageVisualEditSetTailwindTokensOperation" | "PageVisualEditSetValueOperation" | "PageVisualEditSourceRange" | "PageVisualEditTailwindCatalog" | "PageVisualEditTailwindGroup" | "PageVisualEditTailwindOption" | "PageVisualEditTailwindTokenChange" | "PageVisualEditTemplateActions" | "PageVisualEditTemplateBindingSource" | "PageVisualEditTemplateRichTextBindingSource" | "PagedResponse_AssetResponse_" | "PagedResponse_PageItem_" | "PagedResponse_ProjectItem_" | "PagedResponse_Union_WorkspaceComponentItem__SuggestedComponentItem__" | "PagedResponse_WorkspaceComponentItem_" | "PagedResponse_WorkspaceFontConfigResponse_" | "PagedResponse_WorkspaceFontFamilyResponse_" | "PagedResponse_WorkspaceItem_" | "PagedResponse_WorkspaceStyleItem_" | "PagedResponse_WorkspaceThemeItem_" | "PresentationConfig" | "PresentationConfigPatch" | "PreviewArtifactCreateRequest" | "PreviewArtifactResponse" | "PreviewEntryDescriptor" | "PreviewServiceTokenExchangeRequest" | "PreviewServiceTokenExchangeResponse" | "PreviewSizePreset" | "PreviewSizePresetUpdateRequest" | "ProjectBuildAssetSummary" | "ProjectBuildCreateRequest" | "ProjectBuildExtraAssetsConfig" | "ProjectBuildJobResponse" | "ProjectCreateRequest" | "ProjectCustomConfiguration" | "ProjectDefaultConfiguration" | "ProjectItem" | "ProjectPatchConfiguration" | "ProjectRouteChildItem" | "ProjectRouteChildWrite" | "ProjectRouteItemWrite" | "ProjectRoutePageBinding" | "ProjectRouteTreeItem" | "ProjectRouteTreeResponse" | "ProjectRouteTreeWriteRequest" | "ProjectStyleConfiguration" | "ProjectSuggestedReferenceAssetItem" | "ProjectSuggestedReferenceAssetsResponse" | "ProjectSuggestedReferenceAssetsUpdateRequest" | "ProjectTemplateExportRequest" | "ProjectTemplateExportValidationResult" | "ProjectTemplateImportResult" | "ProjectTemplateImportValidationResult" | "ProjectTemplateMetadataPayload" | "ProjectTemplatePackagePageSummary" | "ProjectTemplatePackageProjectSummary" | "ProjectTemplateScreenshotItem" | "ProjectTemplateScreenshotSummary" | "ProjectUpdateRequest" | "ReasoningPolicy" | "RecordStatus" | "RenameAgentSessionRequest" | "RuntimeKitCapabilityItem" | "RuntimeKitCapabilityListResponse" | "RuntimeKitComponentPreviewRequest" | "RuntimeModuleBatchRequest" | "StyleConfiguration" | "StyleConfigurationPatch" | "SuggestedComponentItem" | "SuggestedComponentsResponse" | "SuggestedComponentsSelection" | "ThemeBackgroundPalette" | "ThemeBorderPalette" | "ThemeLinkPalette" | "ThemePalette" | "ThemeTextPalette" | "UpdateAgentSessionPreferencesRequest" | "UserCreateRequest" | "UserItem" | "UserResetPasswordRequest" | "UserRole" | "UserUpdateRequest" | "ValidationError" | "WorkspaceComponentComponentReferenceItem" | "WorkspaceComponentCreateRequest" | "WorkspaceComponentCurrentDependencies" | "WorkspaceComponentDependencyItem" | "WorkspaceComponentExportPackageRequest" | "WorkspaceComponentItem" | "WorkspaceComponentPageReferenceItem" | "WorkspaceComponentPublishRequest" | "WorkspaceComponentReferenceUpgradeComponentItem" | "WorkspaceComponentReferenceUpgradeIssue" | "WorkspaceComponentReferenceUpgradePageItem" | "WorkspaceComponentReferenceUpgradeRequest" | "WorkspaceComponentReferenceUpgradeResponse" | "WorkspaceComponentReferences" | "WorkspaceComponentRestoreDraftRequest" | "WorkspaceComponentSourcePreviewRequest" | "WorkspaceComponentType" | "WorkspaceComponentUpdateRequest" | "WorkspaceComponentVersionContent" | "WorkspaceComponentVersionListItem" | "WorkspaceCreateRequest" | "WorkspaceFontConfigCreateRequest" | "WorkspaceFontConfigResponse" | "WorkspaceFontConfigUpdateRequest" | "WorkspaceFontFamilyResponse" | "WorkspaceFontFamilyUpdateRequest" | "WorkspaceItem" | "WorkspaceStyleCopyRequest" | "WorkspaceStyleCreateRequest" | "WorkspaceStyleExportAssetSummary" | "WorkspaceStyleExportPackageRequest" | "WorkspaceStyleExportValidationResult" | "WorkspaceStyleImportResult" | "WorkspaceStyleImportValidationResult" | "WorkspaceStyleItem" | "WorkspaceStylePackageAssetSummary" | "WorkspaceStylePackageComponentSummary" | "WorkspaceStylePackageFontSummary" | "WorkspaceStylePackageStyleSummary" | "WorkspaceStylePackageThemeSummary" | "WorkspaceStyleUpdateRequest" | "WorkspaceThemeAssetSummary" | "WorkspaceThemeCopyRequest" | "WorkspaceThemeCreateRequest" | "WorkspaceThemeFontFamilySummary" | "WorkspaceThemeItem" | "WorkspaceThemeUpdateRequest" | "WorkspaceUpdateRequest"

export const GENERATED_API_SCHEMA_NAMES: readonly GeneratedApiSchemaName[] = [
  "AgentActiveRunItem",
  "AgentCancelRunRequest",
  "AgentCancelRunResponse",
  "AgentCatalogItem",
  "AgentCodeStandardConfigItem",
  "AgentCodeStandardUpdateRequest",
  "AgentConfigItem",
  "AgentConfigUpdateRequest",
  "AgentContextStatusItem",
  "AgentContinueRunRequest",
  "AgentDescriptor",
  "AgentFocusRequest",
  "AgentImageAttachmentItem",
  "AgentImageAttachmentPromoteRequest",
  "AgentMessageAttachmentItem",
  "AgentMessageItem",
  "AgentPendingRequirement",
  "AgentRunContextSummary",
  "AgentRunProjectSummary",
  "AgentRunRequest",
  "AgentRunStartResponse",
  "AgentScopeContext",
  "AgentSessionItem",
  "AgentSessionRuntimeSnapshot",
  "AgentSuggestedPatch",
  "AgentTimelineItem",
  "AgentTimelineToolItem",
  "AgentToolConfigItem",
  "AgentToolConfigUpdateRequest",
  "AgentToolGroupConfigItem",
  "AgentToolGuideItem",
  "AiLlmConfigScope",
  "ApiAccessTokenCreateRequest",
  "ApiAccessTokenCreateResponse",
  "ApiAccessTokenItem",
  "ApiAccessTokenListResponse",
  "ApiAccessTokenUpdateRequest",
  "AssetAnalysisMetadata",
  "AssetArchiveRequest",
  "AssetBatchArchiveRequest",
  "AssetBatchDeleteRequest",
  "AssetBatchOperationFailure",
  "AssetBatchOperationResponse",
  "AssetBatchRestoreRequest",
  "AssetContentCreateRequest",
  "AssetContentPreviewRequest",
  "AssetContentPreviewResponse",
  "AssetContentResponse",
  "AssetContentUpdateRequest",
  "AssetCopyRequest",
  "AssetFontConfigSummary",
  "AssetIconAnalysisPayload",
  "AssetPackageExportRequest",
  "AssetPackageImportFailure",
  "AssetPackageImportItem",
  "AssetPackageImportResult",
  "AssetReferenceSummary",
  "AssetRenderHintBackfillFailure",
  "AssetRenderHintBackfillJobCreateRequest",
  "AssetRenderHintBackfillJobGroupResponse",
  "AssetRenderHintBackfillJobResponse",
  "AssetResponse",
  "AssetRestoreRequest",
  "AssetRole",
  "AssetType",
  "AssetUpdateRequest",
  "AuthUser",
  "Body_create_project_template_package_preview_artifact_api_workspaces__workspace_id__template_packages_preview_artifact_post",
  "Body_import_component_package_api_components_import_package_post",
  "Body_import_project_template_package_api_workspaces__workspace_id__template_packages_import_post",
  "Body_import_workspace_asset_package_api_workspaces__workspace_id__assets_import_package_post",
  "Body_import_workspace_style_package_api_workspaces__workspace_id__styles_import_package_post",
  "Body_replace_workspace_asset_file_api_workspaces__workspace_id__assets__asset_id__replace_post",
  "Body_upload_agent_image_attachment_api_ai_sessions__session_id__attachments_images_post",
  "Body_upload_asset_api_v1_assets_post",
  "Body_upload_asset_file_api_workspaces__workspace_id__assets_upload_post",
  "Body_validate_component_package_import_api_components_import_package_validate_post",
  "Body_validate_project_template_package_import_api_workspaces__workspace_id__template_packages_import_validate_post",
  "Body_validate_workspace_style_package_import_api_workspaces__workspace_id__styles_import_package_validate_post",
  "BuildJobClaimRequest",
  "BuildJobClaimResponse",
  "BuildJobCompleteRequest",
  "ChangePasswordRequest",
  "ChatBindingItem",
  "ChatBindingUpdate",
  "ChatModelCatalogItem",
  "ChatModelConfigCreate",
  "ChatModelConfigItem",
  "ChatModelConfigUpdate",
  "ChatProviderCatalogItem",
  "ChatProviderConfigCreate",
  "ChatProviderConfigItem",
  "ChatProviderConfigUpdate",
  "ClientErrorLogRequest",
  "ComponentPreviewOptions",
  "ComponentPreviewPageOptions",
  "ComponentPreviewPlacementOptions",
  "ComponentShareExportAssetSummary",
  "ComponentShareExportComponentSummary",
  "ComponentShareExportValidationResult",
  "ComponentShareImportResult",
  "ComponentShareImportValidationResult",
  "ComponentSharePackageAssetSummary",
  "ComponentSharePackageComponentSummary",
  "ComponentSharePackageFontSummary",
  "CreateAgentSessionRequest",
  "ExternalAssetContentCreateRequest",
  "ExternalAssetContentPreviewRequest",
  "ExternalAssetContentUpdateRequest",
  "ExternalAssetCopyRequest",
  "ExternalBatchArchiveRequest",
  "ExternalBatchArchiveResponse",
  "ExternalCapabilitiesResponse",
  "ExternalComponentApplyEditsMutationRequest",
  "ExternalComponentCreateMutationRequest",
  "ExternalComponentMetadataMutationRequest",
  "ExternalComponentMetadataUpdateRequest",
  "ExternalEntityValidationRequest",
  "ExternalEntityValidationResponse",
  "ExternalErrorDetail",
  "ExternalMutationJobResponse",
  "ExternalPageApplyEditsMutationRequest",
  "ExternalPageCopyRequest",
  "ExternalPageCreateMutationRequest",
  "ExternalPageMetadataUpdateRequest",
  "ExternalPreviewArtifactCreateRequest",
  "ExternalProjectApplyStyleRequest",
  "ExternalProjectBuildAssetsRequest",
  "ExternalProjectConfigurationResponse",
  "ExternalProjectConfigurationUpdateRequest",
  "ExternalProjectCreateRequest",
  "ExternalStandardResponse",
  "ExternalStyleCreateRequest",
  "ExternalSystemHealthResponse",
  "ExternalSystemVersionResponse",
  "ExternalThemeCreateRequest",
  "ExternalWhoAmIResponse",
  "HTTPValidationError",
  "ImageBindingItem",
  "ImageBindingUpdate",
  "ImageModelConfigCreate",
  "ImageModelConfigItem",
  "ImageModelConfigUpdate",
  "ImageProviderCatalogItem",
  "ImageProviderConfigCreate",
  "ImageProviderConfigItem",
  "ImageProviderConfigUpdate",
  "JsonValue",
  "LoginRequest",
  "LoginResponse",
  "MessageResponse",
  "ModelCatalogSyncItem",
  "PageComponentResourceItem",
  "PageCopyToProjectRequest",
  "PageCreateRequest",
  "PageCurrentComponentIndex",
  "PageCurrentModuleDependencies",
  "PageFileType",
  "PageItem",
  "PageModuleDependencyItem",
  "PageScreenshotBatchDownloadRequest",
  "PageScreenshotBatchFailure",
  "PageScreenshotBatchRefreshRequest",
  "PageScreenshotBatchRefreshResponse",
  "PageScreenshotJobGroupResponse",
  "PageScreenshotJobRequest",
  "PageScreenshotJobResponse",
  "PageScreenshotRequest",
  "PageSnapshotCreateRequest",
  "PageUpdateRequest",
  "PageVersionContent",
  "PageVersionListItem",
  "PageVersionRestoreRequest",
  "PageVersionStorageType",
  "PageVisualEditApplyDiagnostic",
  "PageVisualEditApplyRequest",
  "PageVisualEditApplyResponse",
  "PageVisualEditBinding",
  "PageVisualEditComponentPropField",
  "PageVisualEditComponentSchema",
  "PageVisualEditComponentSelectOption",
  "PageVisualEditDeleteNodeOperation",
  "PageVisualEditDiagnostic",
  "PageVisualEditDuplicateNodeOperation",
  "PageVisualEditInstancePathSegment",
  "PageVisualEditJsonBindingSource",
  "PageVisualEditJsonSource",
  "PageVisualEditLoopContext",
  "PageVisualEditLoopItemActions",
  "PageVisualEditLoopItemLocation",
  "PageVisualEditManifest",
  "PageVisualEditNode",
  "PageVisualEditPreviewArtifactCreateRequest",
  "PageVisualEditPreviewArtifactResponse",
  "PageVisualEditPreviewContext",
  "PageVisualEditPreviewEntryDescriptor",
  "PageVisualEditScriptArrayBindingSource",
  "PageVisualEditScriptMemberLocation",
  "PageVisualEditSetJsonOperation",
  "PageVisualEditSetRichTextOperation",
  "PageVisualEditSetTailwindTokensOperation",
  "PageVisualEditSetValueOperation",
  "PageVisualEditSourceRange",
  "PageVisualEditTailwindCatalog",
  "PageVisualEditTailwindGroup",
  "PageVisualEditTailwindOption",
  "PageVisualEditTailwindTokenChange",
  "PageVisualEditTemplateActions",
  "PageVisualEditTemplateBindingSource",
  "PageVisualEditTemplateRichTextBindingSource",
  "PagedResponse_AssetResponse_",
  "PagedResponse_PageItem_",
  "PagedResponse_ProjectItem_",
  "PagedResponse_Union_WorkspaceComponentItem__SuggestedComponentItem__",
  "PagedResponse_WorkspaceComponentItem_",
  "PagedResponse_WorkspaceFontConfigResponse_",
  "PagedResponse_WorkspaceFontFamilyResponse_",
  "PagedResponse_WorkspaceItem_",
  "PagedResponse_WorkspaceStyleItem_",
  "PagedResponse_WorkspaceThemeItem_",
  "PresentationConfig",
  "PresentationConfigPatch",
  "PreviewArtifactCreateRequest",
  "PreviewArtifactResponse",
  "PreviewEntryDescriptor",
  "PreviewServiceTokenExchangeRequest",
  "PreviewServiceTokenExchangeResponse",
  "PreviewSizePreset",
  "PreviewSizePresetUpdateRequest",
  "ProjectBuildAssetSummary",
  "ProjectBuildCreateRequest",
  "ProjectBuildExtraAssetsConfig",
  "ProjectBuildJobResponse",
  "ProjectCreateRequest",
  "ProjectCustomConfiguration",
  "ProjectDefaultConfiguration",
  "ProjectItem",
  "ProjectPatchConfiguration",
  "ProjectRouteChildItem",
  "ProjectRouteChildWrite",
  "ProjectRouteItemWrite",
  "ProjectRoutePageBinding",
  "ProjectRouteTreeItem",
  "ProjectRouteTreeResponse",
  "ProjectRouteTreeWriteRequest",
  "ProjectStyleConfiguration",
  "ProjectSuggestedReferenceAssetItem",
  "ProjectSuggestedReferenceAssetsResponse",
  "ProjectSuggestedReferenceAssetsUpdateRequest",
  "ProjectTemplateExportRequest",
  "ProjectTemplateExportValidationResult",
  "ProjectTemplateImportResult",
  "ProjectTemplateImportValidationResult",
  "ProjectTemplateMetadataPayload",
  "ProjectTemplatePackagePageSummary",
  "ProjectTemplatePackageProjectSummary",
  "ProjectTemplateScreenshotItem",
  "ProjectTemplateScreenshotSummary",
  "ProjectUpdateRequest",
  "ReasoningPolicy",
  "RecordStatus",
  "RenameAgentSessionRequest",
  "RuntimeKitCapabilityItem",
  "RuntimeKitCapabilityListResponse",
  "RuntimeKitComponentPreviewRequest",
  "RuntimeModuleBatchRequest",
  "StyleConfiguration",
  "StyleConfigurationPatch",
  "SuggestedComponentItem",
  "SuggestedComponentsResponse",
  "SuggestedComponentsSelection",
  "ThemeBackgroundPalette",
  "ThemeBorderPalette",
  "ThemeLinkPalette",
  "ThemePalette",
  "ThemeTextPalette",
  "UpdateAgentSessionPreferencesRequest",
  "UserCreateRequest",
  "UserItem",
  "UserResetPasswordRequest",
  "UserRole",
  "UserUpdateRequest",
  "ValidationError",
  "WorkspaceComponentComponentReferenceItem",
  "WorkspaceComponentCreateRequest",
  "WorkspaceComponentCurrentDependencies",
  "WorkspaceComponentDependencyItem",
  "WorkspaceComponentExportPackageRequest",
  "WorkspaceComponentItem",
  "WorkspaceComponentPageReferenceItem",
  "WorkspaceComponentPublishRequest",
  "WorkspaceComponentReferenceUpgradeComponentItem",
  "WorkspaceComponentReferenceUpgradeIssue",
  "WorkspaceComponentReferenceUpgradePageItem",
  "WorkspaceComponentReferenceUpgradeRequest",
  "WorkspaceComponentReferenceUpgradeResponse",
  "WorkspaceComponentReferences",
  "WorkspaceComponentRestoreDraftRequest",
  "WorkspaceComponentSourcePreviewRequest",
  "WorkspaceComponentType",
  "WorkspaceComponentUpdateRequest",
  "WorkspaceComponentVersionContent",
  "WorkspaceComponentVersionListItem",
  "WorkspaceCreateRequest",
  "WorkspaceFontConfigCreateRequest",
  "WorkspaceFontConfigResponse",
  "WorkspaceFontConfigUpdateRequest",
  "WorkspaceFontFamilyResponse",
  "WorkspaceFontFamilyUpdateRequest",
  "WorkspaceItem",
  "WorkspaceStyleCopyRequest",
  "WorkspaceStyleCreateRequest",
  "WorkspaceStyleExportAssetSummary",
  "WorkspaceStyleExportPackageRequest",
  "WorkspaceStyleExportValidationResult",
  "WorkspaceStyleImportResult",
  "WorkspaceStyleImportValidationResult",
  "WorkspaceStyleItem",
  "WorkspaceStylePackageAssetSummary",
  "WorkspaceStylePackageComponentSummary",
  "WorkspaceStylePackageFontSummary",
  "WorkspaceStylePackageStyleSummary",
  "WorkspaceStylePackageThemeSummary",
  "WorkspaceStyleUpdateRequest",
  "WorkspaceThemeAssetSummary",
  "WorkspaceThemeCopyRequest",
  "WorkspaceThemeCreateRequest",
  "WorkspaceThemeFontFamilySummary",
  "WorkspaceThemeItem",
  "WorkspaceThemeUpdateRequest",
  "WorkspaceUpdateRequest",
] as const
