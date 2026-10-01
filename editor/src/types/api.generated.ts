/** 文件功能：由 Backend OpenAPI 生成的 API 类型，勿手改；运行 pnpm run codegen:editor-api。 */

export type AgentActiveRunItem = {
  "run_id": string
  "session_id": string
  "agent_id": string
  "status": "pending" | "running" | "paused" | "waiting_external" | "cancelling" | "completed" | "cancelled" | "failed"
  "focus": AgentScopeContext
  "work_scope_mode"?: "workspace" | "selected_projects"
  "allowed_project_ids"?: (number)[]
  "focus_version"?: number
  "pending_requirement"?: (AgentPendingRequirement) | (null)
  "content"?: (string) | (null)
  "created_at"?: (string) | (null)
  "updated_at"?: (string) | (null)
  "cancel_requested_at"?: (string) | (null)
  "event_index"?: number
  "llm"?: (Record<string, unknown>) | (null)
  "error_code"?: (string) | (null)
  "error_message"?: (string) | (null)
}

export type AgentCancelRunRequest = {
  "force"?: boolean
  "tool_call_id"?: (string) | (null)
}

export type AgentCancelRunResponse = {
  "run_id": string
  "session_id": string
  "cancel_requested"?: boolean
}

export type AgentCatalogItem = {
  "id": string
  "name": string
  "icon": string
  "summary": string
  "default_session_name": string
  "capabilities"?: (string)[]
  "scope_type": "workspace" | "project" | "page" | "component"
  "entry_kind"?: "agent" | "team"
  "llm_slot": string
  "default_description": string
  "description": string
  "description_override"?: (string) | (null)
  "description_customized"?: boolean
  "role": string
  "system_prompt": string
  "default_prompt": string
  "tool_groups"?: (AgentToolGroupConfigItem)[]
}

export type AgentCodeStandardConfigItem = {
  "agent_id": string
  "standard_type": "page" | "component"
  "default_content": string
  "content": string
  "content_override"?: (string) | (null)
  "customized"?: boolean
  "source"?: "system_default" | "user_custom"
}

export type AgentCodeStandardUpdateRequest = {
  "content_override"?: (string) | (null)
  "restore_default"?: boolean
}

export type AgentConfigItem = {
  "id": string
  "name": string
  "icon": string
  "summary": string
  "default_session_name": string
  "capabilities"?: (string)[]
  "scope_type": "workspace" | "project" | "page" | "component"
  "entry_kind"?: "agent" | "team"
  "llm_slot": string
  "default_description": string
  "description": string
  "description_override"?: (string) | (null)
  "description_customized"?: boolean
  "role": string
  "system_prompt": string
  "default_prompt": string
  "tool_groups"?: (AgentToolGroupConfigItem)[]
  "prompt_override"?: (string) | (null)
  "effective_prompt": string
  "prompt_customized"?: boolean
  "enabled_tool_count"?: number
  "disabled_tool_count"?: number
}

export type AgentConfigUpdateRequest = {
  "description_override"?: (string) | (null)
  "prompt_override"?: (string) | (null)
  "restore_default"?: boolean
}

export type AgentContextStatusItem = {
  "session_id": string
  "agent_id": string
  "compression_enabled": boolean
  "compression_required": boolean
  "compression_status"?: "idle" | "compressing" | "compressed" | "failed"
  "compression_method"?: "none" | "model" | "deterministic_fallback"
  "compression_error_message"?: (string) | (null)
  "summary_available": boolean
  "summary"?: (string) | (null)
  "topics"?: (string)[]
  "summary_updated_at"?: (string) | (null)
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

export type AgentContinueRunRequest = {
  "decision"?: ("confirm" | "reject") | (null)
  "note"?: (string) | (null)
  "tool_execution"?: Record<string, unknown>
  "feedback_selections"?: (Record<string, unknown>)[]
}

export type AgentDescriptor = {
  "id": string
  "name": string
  "icon": string
  "summary": string
  "default_session_name": string
  "capabilities"?: (string)[]
  "scope_type": "workspace" | "project" | "page" | "component"
  "entry_kind"?: "agent" | "team"
  "available"?: boolean
  "unavailable_reason"?: (string) | (null)
  "llm_slot"?: (string) | (null)
  "llm_binding_ready"?: boolean
  "bound_llm_name"?: (string) | (null)
  "bound_provider_label"?: (string) | (null)
  "supports_image_input"?: boolean
  "image_analysis_available"?: boolean
  "image_analysis_unavailable_reason"?: (string) | (null)
  "image_generation_available"?: boolean
  "image_generation_unavailable_reason"?: (string) | (null)
  "prompt_customized"?: boolean
  "enabled_tool_count"?: number
  "disabled_tool_count"?: number
  "scope": AgentScopeContext
}

export type AgentFocusRequest = {
  "scope_type"?: "workspace" | "project" | "page" | "component"
  "project_id"?: (number) | (null)
  "page_id"?: (number) | (null)
  "component_id"?: (number) | (null)
  "source"?: string
}

export type AgentImageAttachmentItem = {
  "id": number
  "session_id": string
  "source_kind"?: "user_upload" | "tool_output"
  "original_name": string
  "content_type": string
  "file_size": number
  "width"?: (number) | (null)
  "height"?: (number) | (null)
  "sha256": string
  "url": string
  "preview_available"?: boolean
  "promoted_asset_id"?: (number) | (null)
  "promotion_status"?: "never" | "promoted" | "deleted"
  "status": string
  "created_at"?: (string) | (null)
}

export type AgentImageAttachmentPromoteRequest = {
  "name"?: (string) | (null)
  "description"?: (string) | (null)
  "tags"?: (string)[]
  "overwrite"?: boolean
}

export type AgentMessageAttachmentItem = {
  "id": number
  "source_kind"?: "user_upload" | "tool_output"
  "original_name": string
  "content_type": string
  "file_size": number
  "width"?: (number) | (null)
  "height"?: (number) | (null)
  "url": string
  "preview_available"?: boolean
  "promoted_asset_id"?: (number) | (null)
  "promotion_status"?: "never" | "promoted" | "deleted"
}

export type AgentMessageItem = {
  "id": string
  "run_id"?: (string) | (null)
  "role": "user" | "assistant" | "tool"
  "content": string
  "reasoning_content"?: (string) | (null)
  "created_at"?: (string) | (null)
  "tool_name"?: (string) | (null)
  "tool_call_id"?: (string) | (null)
  "tool_args"?: (unknown) | (null)
  "tool_call_error"?: (boolean) | (null)
  "tool_calls"?: (Record<string, unknown>)[]
  "attachments"?: (AgentMessageAttachmentItem)[]
}

export type AgentPendingRequirement = {
  "id"?: (string) | (null)
  "kind"?: "confirmation" | "user_feedback" | "external_job"
  "run_id": string
  "session_id": string
  "tool_name"?: (string) | (null)
  "tool_execution"?: Record<string, unknown>
  "suggested_patch"?: (AgentSuggestedPatch) | (null)
  "user_feedback_schema"?: (Record<string, unknown>)[]
  "note"?: (string) | (null)
}

export type AgentRunContextSummary = {
  "focus": AgentScopeContext
  "work_scope_mode"?: "workspace" | "selected_projects"
  "allowed_projects"?: (AgentRunProjectSummary)[]
  "focus_version"?: number
}

export type AgentRunProjectSummary = {
  "id": number
  "name"?: (string) | (null)
}

export type AgentRunRequest = {
  "run_id"?: (string) | (null)
  "message"?: string
  "image_attachment_ids"?: (number)[]
  "llm_config_id"?: (number) | (null)
  "reasoning"?: ReasoningPolicy
  "focus": AgentFocusRequest
}

export type AgentRunStartResponse = {
  "run_id": string
  "session_id": string
  "status"?: "pending" | "running"
  "event_index"?: number
}

export type AgentScopeContext = {
  "scope_type"?: "workspace" | "project" | "page" | "component"
  "workspace_id": number
  "project_id"?: (number) | (null)
  "page_id"?: (number) | (null)
  "component_id"?: (number) | (null)
  "workspace_name"?: (string) | (null)
  "project_name"?: (string) | (null)
  "page_title"?: (string) | (null)
  "component_name"?: (string) | (null)
  "source"?: string
}

export type AgentSessionItem = {
  "session_id": string
  "agent_id": string
  "workspace_id": number
  "session_name"?: (string) | (null)
  "focus_mode"?: "follow_route" | "pinned_project" | "workspace"
  "pinned_project_id"?: (number) | (null)
  "work_scope_mode"?: "workspace" | "selected_projects"
  "allowed_project_ids"?: (number)[]
  "focus_version"?: number
  "created_at"?: (string) | (null)
  "updated_at"?: (string) | (null)
  "metadata"?: Record<string, unknown>
}

export type AgentSessionRuntimeSnapshot = {
  "session": AgentSessionItem
  "timeline_items"?: (AgentTimelineItem)[]
  "context_status": AgentContextStatusItem
  "active_run"?: (AgentActiveRunItem) | (null)
  "last_run"?: (AgentActiveRunItem) | (null)
  "pending_requirement"?: (AgentPendingRequirement) | (null)
  "event_index"?: number
  "pending_attachments"?: (AgentImageAttachmentItem)[]
}

export type AgentSuggestedPatch = {
  "tool_name": string
  "target_page_id": number
  "change_note"?: (string) | (null)
  "proposed_content": string
  "unified_diff": string
}

export type AgentTimelineItem = {
  "id": string
  "session_id": string
  "run_id": string
  "kind": "run_context" | "message" | "reasoning" | "tool" | "run_status" | "requirement"
  "role"?: ("user" | "assistant") | (null)
  "event_index"?: (number) | (null)
  "order_index": number
  "content"?: (string) | (null)
  "status"?: (string) | (null)
  "tool"?: (AgentTimelineToolItem) | (null)
  "run_context"?: (AgentRunContextSummary) | (null)
  "attachments"?: (AgentMessageAttachmentItem)[]
  "source": "message" | "event" | "synthetic"
  "created_at"?: (string) | (null)
}

export type AgentTimelineToolItem = {
  "tool_call_id"?: (string) | (null)
  "tool_name": string
  "status": "running" | "waiting_external" | "completed" | "error" | "cancelled" | "interrupted"
  "input_payload"?: (unknown) | (null)
  "output_payload"?: (unknown) | (null)
  "message"?: string
  "progress"?: (Record<string, unknown>) | (null)
  "input_attachments"?: (AgentMessageAttachmentItem)[]
  "output_attachments"?: (AgentMessageAttachmentItem)[]
}

export type AgentToolConfigItem = {
  "key": string
  "label": string
  "group_key": string
  "group_label": string
  "default_description": string
  "description": string
  "description_override"?: (string) | (null)
  "default_instructions"?: (string) | (null)
  "instructions"?: (string) | (null)
  "instructions_override"?: (string) | (null)
  "enabled"?: boolean
  "configurable"?: boolean
  "requires_confirmation"?: boolean
  "risk_level"?: "system" | "read" | "write" | "danger"
  "agent_guide": AgentToolGuideItem
}

export type AgentToolConfigUpdateRequest = {
  "enabled"?: (boolean) | (null)
  "description_override"?: (string) | (null)
  "instructions_override"?: (string) | (null)
  "restore_default"?: boolean
}

export type AgentToolGroupConfigItem = {
  "key": string
  "label": string
  "description": string
  "tools"?: (AgentToolConfigItem)[]
}

export type AgentToolGuideItem = {
  "tool_name": string
  "effective_description": string
  "system_description": string
  "instructions"?: (string) | (null)
  "parameters_schema"?: (Record<string, unknown>) | (null)
  "call_example"?: (Record<string, unknown>) | (null)
  "response_example"?: (unknown) | (null)
  "response_notes"?: (string) | (null)
  "required_context_fields"?: (string)[]
  "runtime_disclosure_groups"?: (string)[]
  "requires_confirmation"?: boolean
  "risk_level"?: "system" | "read" | "write" | "danger"
}

export type AiLlmConfigScope = "global" | "personal"

export type ApiAccessTokenCreateRequest = {
  "name": string
  "workspace_ids"?: (number)[]
  "all_workspaces"?: boolean
  "scopes": (string)[]
  "expires_in_days"?: (number) | (null)
}

export type ApiAccessTokenCreateResponse = {
  "id": number
  "name": string
  "token_public_id": string
  "token": string
  "expires_at": (string) | (null)
  "all_workspaces": boolean
  "workspace_ids": (number)[]
  "scopes": (string)[]
  "created_at": string
}

export type ApiAccessTokenItem = {
  "id": number
  "name": string
  "token_public_id": string
  "token_masked": string
  "expires_at": (string) | (null)
  "revoked_at": (string) | (null)
  "last_used_at": (string) | (null)
  "last_used_ip": (string) | (null)
  "is_active": boolean
  "all_workspaces": boolean
  "workspace_ids": (number)[]
  "scopes": (string)[]
  "created_at": string
}

export type ApiAccessTokenListResponse = {
  "items": (ApiAccessTokenItem)[]
  "total": number
  "max_active_tokens": number
}

export type ApiAccessTokenUpdateRequest = {
  "name"?: (string) | (null)
  "workspace_ids"?: ((number)[]) | (null)
  "all_workspaces"?: (boolean) | (null)
  "scopes"?: ((string)[]) | (null)
  "expires_in_days"?: (number) | (null)
}

export type AssetAnalysisMetadata = {
  "schema_version"?: number
  "kind"?: "icon"
  "icon": AssetIconAnalysisPayload
}

export type AssetArchiveRequest = {
  "archive_reason"?: (string) | (null)
}

export type AssetBatchArchiveRequest = {
  "asset_ids": (number)[]
  "archive_reason"?: (string) | (null)
}

export type AssetBatchDeleteRequest = {
  "asset_ids": (number)[]
}

export type AssetBatchOperationFailure = {
  "asset_id": number
  "code": string
  "detail": string
}

export type AssetBatchOperationResponse = {
  "requested_count": number
  "succeeded_count": number
  "failed_count": number
  "asset_ids"?: (number)[]
  "failures"?: (AssetBatchOperationFailure)[]
}

export type AssetBatchRestoreRequest = {
  "asset_ids": (number)[]
  "restore_reason"?: (string) | (null)
}

export type AssetContentCreateRequest = {
  "asset_type": AssetType
  "name": string
  "original_name": string
  "content": string
  "description"?: (string) | (null)
  "tags"?: (string)[]
  "approx_aspect_ratio"?: (string) | (null)
}

export type AssetContentPreviewRequest = {
  "content": string
}

export type AssetContentPreviewResponse = {
  "asset_id": number
  "asset_name": string
  "changed": boolean
  "unified_diff": string
}

export type AssetContentResponse = {
  "asset": AssetResponse
  "content": string
}

export type AssetContentUpdateRequest = {
  "content": string
  "change_note"?: (string) | (null)
}

export type AssetCopyRequest = {
  "name"?: (string) | (null)
  "original_name"?: (string) | (null)
  "description"?: (string) | (null)
  "tags"?: ((string)[]) | (null)
  "status"?: RecordStatus
  "archive_reason"?: (string) | (null)
}

export type AssetFontConfigSummary = {
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

export type AssetIconAnalysisPayload = {
  "format"?: "svg" | "image" | "unknown"
  "render_mode"?: "inline_svg" | "image"
  "style"?: "stroke" | "fill" | "mixed" | "complex" | "unknown"
  "inline_safe"?: boolean
  "stroke_width_editable"?: boolean
  "analysis_status"?: "analyzed" | "unsupported" | "error"
  "reasons"?: (string)[]
}

export type AssetPackageExportRequest = {
  "asset_ids": (number)[]
}

export type AssetPackageImportFailure = {
  "name": string
  "code": string
  "detail": string
}

export type AssetPackageImportItem = {
  "name": string
  "original_name": string
  "asset_type": AssetType
  "file_hash": string
  "action": "create" | "update_metadata" | "reuse"
  "asset_id"?: (number) | (null)
}

export type AssetPackageImportResult = {
  "imported_count"?: number
  "updated_count"?: number
  "reused_count"?: number
  "failed_count"?: number
  "assets"?: (AssetPackageImportItem)[]
  "failures"?: (AssetPackageImportFailure)[]
}

export type AssetReferenceSummary = {
  "theme_count"?: number
  "font_count"?: number
  "page_count"?: number
  "component_count"?: number
  "component_version_count"?: number
  "references"?: (Record<string, unknown>)[]
  "has_references": boolean
}

export type AssetRenderHintBackfillFailure = {
  "asset_id": number
  "asset_name"?: (string) | (null)
  "code": string
  "detail": string
}

export type AssetRenderHintBackfillJobCreateRequest = {
  "asset_types"?: (("image" | "video" | "drawio" | "mermaid" | "formula")[]) | (null)
  "asset_ids"?: ((number)[]) | (null)
  "mode"?: "preview" | "apply"
  "overwrite_manual"?: boolean
}

export type AssetRenderHintBackfillJobGroupResponse = {
  "job_group_id": string
  "status": "pending" | "running" | "succeeded" | "failed" | "partial"
  "requested_count": number
  "pending_count": number
  "running_count": number
  "succeeded_count": number
  "failed_count": number
  "skipped_count": number
  "asset_ids"?: (number)[]
  "jobs"?: (AssetRenderHintBackfillJobResponse)[]
  "failures"?: (AssetRenderHintBackfillFailure)[]
}

export type AssetRenderHintBackfillJobResponse = {
  "id": number
  "job_group_id": (string) | (null)
  "workspace_id": number
  "asset_id": number
  "asset_name"?: (string) | (null)
  "asset_type": AssetType
  "source": string
  "mode": "preview" | "apply"
  "overwrite_manual": boolean
  "status": "pending" | "running" | "succeeded" | "failed" | "skipped"
  "attempt_count": number
  "current_render_metadata"?: (Record<string, unknown>) | (null)
  "next_render_metadata"?: (Record<string, unknown>) | (null)
  "current_approx_aspect_ratio"?: (string) | (null)
  "next_approx_aspect_ratio"?: (string) | (null)
  "error_code"?: (string) | (null)
  "error_message"?: (string) | (null)
  "created_by": (number) | (null)
  "created_at": string
  "updated_at": string
  "started_at": (string) | (null)
  "finished_at": (string) | (null)
}

export type AssetResponse = {
  "id": number
  "workspace_id": number
  "name": string
  "file_name": string
  "original_name": string
  "description"?: (string) | (null)
  "file_size": number
  "file_hash": string
  "content_type"?: (string) | (null)
  "asset_type": AssetType
  "asset_role"?: AssetRole
  "render_type"?: AssetType
  "tags"?: (string)[]
  "analysis_metadata"?: (AssetAnalysisMetadata) | (null)
  "render_metadata"?: (Record<string, unknown>) | (null)
  "approx_aspect_ratio"?: (string) | (null)
  "approx_aspect_ratio_value"?: (number) | (null)
  "aspect_ratio_source"?: (string) | (null)
  "status"?: RecordStatus
  "archived_at"?: (string) | (null)
  "archive_reason"?: (string) | (null)
  "source_asset_id"?: (number) | (null)
  "history_kind"?: (string) | (null)
  "content_editable"?: boolean
  "url"?: (string) | (null)
  "font_config"?: (AssetFontConfigSummary) | (null)
  "rename_block_reason"?: (string) | (null)
  "delete_block_reason"?: (string) | (null)
  "archive_block_reason"?: (string) | (null)
  "archive_warning_reasons"?: (string)[]
  "created_at": string
  "updated_at": string
}

export type AssetRestoreRequest = {
  "restore_reason"?: (string) | (null)
}

export type AssetRole = "foundation" | "content"

export type AssetType = "icon" | "font" | "image" | "video" | "drawio" | "mermaid" | "chart" | "formula"

export type AssetUpdateRequest = {
  "name"?: (string) | (null)
  "original_name"?: (string) | (null)
  "description"?: (string) | (null)
  "tags"?: ((string)[]) | (null)
  "approx_aspect_ratio"?: (string) | (null)
}

export type AuthUser = {
  "id": number
  "username": string
  "display_name": string
  "role": UserRole
  "status": RecordStatus
  "last_login_at": (string) | (null)
  "preview_size_presets": (PreviewSizePreset)[]
}

export type Body_create_project_template_package_preview_artifact_api_workspaces__workspace_id__template_packages_preview_artifact_post = {
  "archive": string
}

export type Body_import_component_package_api_components_import_package_post = {
  "workspace_id": number
  "archive": string
}

export type Body_import_project_template_package_api_workspaces__workspace_id__template_packages_import_post = {
  "archive": string
}

export type Body_import_workspace_asset_package_api_workspaces__workspace_id__assets_import_package_post = {
  "archive": string
}

export type Body_import_workspace_style_package_api_workspaces__workspace_id__styles_import_package_post = {
  "archive": string
}

export type Body_replace_workspace_asset_file_api_workspaces__workspace_id__assets__asset_id__replace_post = {
  "file": string
}

export type Body_upload_agent_image_attachment_api_ai_sessions__session_id__attachments_images_post = {
  "file": string
}

export type Body_upload_asset_api_v1_assets_post = {
  "file": string
  "asset_type": AssetType
  "name"?: (string) | (null)
  "description"?: (string) | (null)
  "tags"?: (string) | (null)
  "overwrite"?: boolean
}

export type Body_upload_asset_file_api_workspaces__workspace_id__assets_upload_post = {
  "file": string
  "asset_type"?: AssetType
  "tags"?: string
  "name"?: (string) | (null)
  "description"?: (string) | (null)
  "overwrite"?: boolean
}

export type Body_validate_component_package_import_api_components_import_package_validate_post = {
  "workspace_id": number
  "archive": string
}

export type Body_validate_project_template_package_import_api_workspaces__workspace_id__template_packages_import_validate_post = {
  "archive": string
}

export type Body_validate_workspace_style_package_import_api_workspaces__workspace_id__styles_import_package_validate_post = {
  "archive": string
}

export type BuildJobClaimRequest = {
  "worker_id": string
}

export type BuildJobClaimResponse = {
  "job_id"?: (number) | (null)
  "project_id"?: (number) | (null)
  "snapshot_release_id"?: (string) | (null)
  "base_url"?: (string) | (null)
  "workspace_id"?: (number) | (null)
  "attempt_id"?: (string) | (null)
  "lease_owner"?: (string) | (null)
  "lease_expires_at"?: (string) | (null)
  "deadline_at"?: (string) | (null)
  "build_token"?: (string) | (null)
  "service_token"?: (string) | (null)
  "message"?: string
}

export type BuildJobCompleteRequest = {
  "success": boolean
  "error_message"?: (string) | (null)
}

export type ChangePasswordRequest = {
  "old_password": string
  "new_password": string
}

export type ChatBindingItem = {
  "slot": string
  "model_config_id"?: (number) | (null)
  "model_name"?: (string) | (null)
  "provider_config_id"?: (number) | (null)
  "provider_config_name"?: (string) | (null)
  "provider_key"?: (string) | (null)
  "provider_name"?: (string) | (null)
  "model_id"?: (string) | (null)
  "supports_image_input"?: boolean
  "binding_ready": boolean
  "inherited_from_global"?: boolean
}

export type ChatBindingUpdate = {
  "model_config_id"?: (number) | (null)
  "scope"?: AiLlmConfigScope
}

export type ChatModelCatalogItem = {
  "provider_key": string
  "model_id": string
  "name": string
  "protocol_key": string
  "family"?: (string) | (null)
  "status"?: (string) | (null)
  "release_date"?: (string) | (null)
  "last_updated"?: (string) | (null)
  "context_tokens"?: (number) | (null)
  "input_tokens"?: (number) | (null)
  "output_tokens"?: (number) | (null)
  "input_modalities"?: (string)[]
  "output_modalities"?: (string)[]
  "supports_tool_call"?: boolean
  "supports_structured_output"?: boolean
  "supports_attachment"?: boolean
  "supports_reasoning"?: boolean
  "reasoning_options"?: Record<string, unknown>
  "catalog_version": string
  "synced_at"?: (string) | (null)
}

export type ChatModelConfigCreate = {
  "name": string
  "scope"?: AiLlmConfigScope
  "provider_config_id": number
  "model_id": string
  "capability_override"?: Record<string, unknown>
  "advanced_config"?: Record<string, unknown>
}

export type ChatModelConfigItem = {
  "id": number
  "scope": string
  "editable": boolean
  "name": string
  "provider_config_id": number
  "provider_name": string
  "provider_key": string
  "protocol_key": string
  "model_id": string
  "catalog_version"?: (string) | (null)
  "capability": Record<string, unknown>
  "capability_override": Record<string, unknown>
  "advanced_config": Record<string, unknown>
  "status": string
}

export type ChatModelConfigUpdate = {
  "name"?: (string) | (null)
  "provider_config_id"?: (number) | (null)
  "model_id"?: (string) | (null)
  "capability_override"?: (Record<string, unknown>) | (null)
  "advanced_config"?: (Record<string, unknown>) | (null)
  "status"?: ("active" | "archived") | (null)
}

export type ChatProviderCatalogItem = {
  "provider_key": string
  "name": string
  "api_url"?: (string) | (null)
  "docs_url"?: (string) | (null)
  "default_base_url"?: (string) | (null)
  "protocol_key": string
  "catalog_version": string
  "synced_at"?: (string) | (null)
}

export type ChatProviderConfigCreate = {
  "name": string
  "scope"?: AiLlmConfigScope
  "catalog_provider_key"?: (string) | (null)
  "custom"?: boolean
  "base_url"?: (string) | (null)
  "api_key"?: (string) | (null)
}

export type ChatProviderConfigItem = {
  "id": number
  "scope": string
  "editable": boolean
  "name": string
  "provider_key": string
  "catalog_provider_key"?: (string) | (null)
  "provider_name": string
  "protocol_key": string
  "base_url"?: (string) | (null)
  "has_api_key": boolean
  "api_key_masked"?: (string) | (null)
  "status": string
}

export type ChatProviderConfigUpdate = {
  "name"?: (string) | (null)
  "base_url"?: (string) | (null)
  "api_key"?: (string) | (null)
  "status"?: ("active" | "archived") | (null)
}

export type ClientErrorLogRequest = {
  "source": "editor" | "runtime-browser"
  "message": string
  "error_name"?: (string) | (null)
  "stack"?: (string) | (null)
  "route"?: (string) | (null)
  "url"?: (string) | (null)
  "component"?: (string) | (null)
  "trace_id"?: (string) | (null)
  "artifact_id"?: (string) | (null)
  "context"?: Record<string, unknown>
}

export type ComponentPreviewOptions = {
  "page"?: ComponentPreviewPageOptions
  "placement"?: ComponentPreviewPlacementOptions
}

export type ComponentPreviewPageOptions = {
  "width"?: number
  "height"?: number
  "base_font_size"?: string
  "icon_default_stroke_width"?: number
  "theme_key"?: (string) | (null)
  "theme_config_yaml"?: (string) | (null)
}

export type ComponentPreviewPlacementOptions = {
  "width_mode"?: "auto" | "percent" | "fixed"
  "width_value"?: (number) | (null)
  "height_mode"?: "auto" | "percent" | "fixed"
  "height_value"?: (number) | (null)
  "horizontal_align"?: "start" | "center" | "end"
  "vertical_align"?: "start" | "center" | "end"
  "padding"?: number
}

export type ComponentShareExportAssetSummary = {
  "name": string
  "original_name": string
  "asset_type": string
  "file_hash": string
  "source"?: string
}

export type ComponentShareExportComponentSummary = {
  "source_component_code": string
  "source_version_no": number
  "name": string
  "import_name": string
  "has_dynamic_resources"?: boolean
  "missing_static_asset_names"?: (string)[]
}

export type ComponentShareExportValidationResult = {
  "can_export"?: boolean
  "components"?: (ComponentShareExportComponentSummary)[]
  "automatic_assets"?: (ComponentShareExportAssetSummary)[]
  "manual_assets"?: (ComponentShareExportAssetSummary)[]
  "fonts"?: (ComponentSharePackageFontSummary)[]
  "warnings"?: (string)[]
  "missing_static_asset_names"?: (string)[]
  "missing_manual_asset_names"?: (string)[]
  "dynamic_resource_components"?: (string)[]
}

export type ComponentShareImportResult = {
  "imported_components"?: (WorkspaceComponentItem)[]
  "components"?: (ComponentSharePackageComponentSummary)[]
  "assets"?: (ComponentSharePackageAssetSummary)[]
  "fonts"?: (ComponentSharePackageFontSummary)[]
  "warnings"?: (string)[]
}

export type ComponentShareImportValidationResult = {
  "valid": boolean
  "schema_version"?: (number) | (null)
  "runtime_kit_manifest_version"?: (string) | (null)
  "components"?: (ComponentSharePackageComponentSummary)[]
  "assets"?: (ComponentSharePackageAssetSummary)[]
  "fonts"?: (ComponentSharePackageFontSummary)[]
  "errors"?: (string)[]
  "warnings"?: (string)[]
}

export type ComponentSharePackageAssetSummary = {
  "name": string
  "original_name": string
  "asset_type": string
  "file_hash": string
  "action"?: string
}

export type ComponentSharePackageComponentSummary = {
  "source_component_code": string
  "source_version_no": number
  "name": string
  "import_name": string
  "component_type": string
  "dependencies"?: (string)[]
  "component_fingerprint"?: (string) | (null)
  "matched_component_id"?: (number) | (null)
  "matched_component_code"?: (string) | (null)
  "action"?: string
  "match_reason"?: (string) | (null)
}

export type ComponentSharePackageFontSummary = {
  "asset_name": string
  "font_family": string
  "font_format": string
  "font_weight": string
  "font_style": string
  "font_display": string
  "status": string
  "action"?: string
}

export type CreateAgentSessionRequest = {
  "agent_id"?: string
  "session_name"?: (string) | (null)
  "workspace_id": number
  "focus_mode"?: "follow_route" | "pinned_project" | "workspace"
  "pinned_project_id"?: (number) | (null)
  "work_scope_mode"?: "workspace" | "selected_projects"
  "allowed_project_ids"?: (number)[]
  "llm_config_id"?: (number) | (null)
}

export type ExternalAssetContentCreateRequest = {
  "asset_type": string
  "name": string
  "original_name": string
  "content": string
  "description"?: (string) | (null)
  "tags"?: (string)[]
  "approx_aspect_ratio"?: (string) | (null)
}

export type ExternalAssetContentPreviewRequest = {
  "content": string
}

export type ExternalAssetContentUpdateRequest = {
  "content": string
  "change_note"?: (string) | (null)
}

export type ExternalAssetCopyRequest = {
  "name"?: (string) | (null)
  "original_name"?: (string) | (null)
  "description"?: (string) | (null)
  "tags"?: ((string)[]) | (null)
}

export type ExternalBatchArchiveRequest = {
  "ids": (number)[]
  "reason"?: (string) | (null)
}

export type ExternalBatchArchiveResponse = {
  "archived_ids": (number)[]
  "failed_ids": (number)[]
  "total": number
}

export type ExternalCapabilitiesResponse = {
  "version"?: string
  "workspace_id": number
  "scopes": (string)[]
  "operations": (string)[]
}

export type ExternalComponentApplyEditsMutationRequest = {
  "component_id": number
  "base_version_no": number
  "base_draft_hash"?: (string) | (null)
  "edits": (Record<string, unknown>)[]
}

export type ExternalComponentCreateMutationRequest = {
  "workspace_id": number
  "import_name": string
  "name": string
  "component_type"?: string
  "source_code": string
  "description"?: (string) | (null)
  "preview_schema"?: (Record<string, unknown>) | (null)
}

export type ExternalComponentMetadataMutationRequest = {
  "component_id": number
  "base_version_no"?: (number) | (null)
  "base_draft_hash"?: (string) | (null)
  "name"?: (string) | (null)
  "import_name"?: (string) | (null)
  "component_type"?: (string) | (null)
  "summary"?: (string) | (null)
  "preview_schema"?: (Record<string, unknown>) | (null)
  "change_note"?: (string) | (null)
}

export type ExternalComponentMetadataUpdateRequest = {
  "name"?: (string) | (null)
  "summary"?: (string) | (null)
}

export type ExternalEntityValidationRequest = {
  "entity_type": "page" | "component"
  "entity_id"?: (number) | (null)
  "mode"?: "current" | "content" | "edits"
  "source_code"?: (string) | (null)
  "edits"?: ((Record<string, unknown>)[]) | (null)
  "preview_schema"?: (Record<string, unknown>) | (null)
  "detail"?: boolean
}

export type ExternalEntityValidationResponse = {
  "entity_type": "page" | "component"
  "entity_id"?: (number) | (null)
  "mode": "current" | "content" | "edits"
  "valid": boolean
  "status"?: (string) | (null)
  "retryable"?: boolean
  "error_code"?: (string) | (null)
  "summary": string
  "errors"?: (string)[]
  "warnings"?: (string)[]
  "imports"?: (string)[]
  "diagnostics"?: (Record<string, unknown>)[]
}

export type ExternalErrorDetail = {
  "code": string
  "message": string
  "retryable"?: boolean
  "details"?: (Record<string, unknown>) | (null)
}

export type ExternalMutationJobResponse = {
  "job_id": string
  "job_type": string
  "workspace_id": number
  "target_id"?: (number) | (null)
  "status": "pending" | "running" | "succeeded" | "failed" | "canceled"
  "attempt_count": number
  "max_attempts": number
  "next_attempt_at"?: (string) | (null)
  "last_error_code"?: (string) | (null)
  "cancel_requested_at"?: (string) | (null)
  "retry_of_job_id"?: (string) | (null)
  "result"?: (Record<string, unknown>) | (null)
  "error"?: (ExternalErrorDetail) | (null)
  "created_at": string
  "started_at"?: (string) | (null)
  "finished_at"?: (string) | (null)
}

export type ExternalPageApplyEditsMutationRequest = {
  "page_id": number
  "base_version_no": number
  "edits": (Record<string, unknown>)[]
}

export type ExternalPageCopyRequest = {
  "target_project_id": number
  "title"?: (string) | (null)
  "summary"?: (string) | (null)
  "route_placement"?: "none" | "root" | "group"
  "parent_route_id"?: (number) | (null)
  "route"?: (string) | (null)
}

export type ExternalPageCreateMutationRequest = {
  "project_id": number
  "name": string
  "source_code": string
  "description"?: (string) | (null)
}

export type ExternalPageMetadataUpdateRequest = {
  "title"?: (string) | (null)
  "summary"?: (string) | (null)
  "speaker_notes"?: (string) | (null)
}

export type ExternalPreviewArtifactCreateRequest = {
  "route"?: (string) | (null)
}

export type ExternalProjectApplyStyleRequest = {
  "style_id": number
}

export type ExternalProjectBuildAssetsRequest = {
  "build_extra_assets_json"?: Record<string, unknown>
}

export type ExternalProjectConfigurationResponse = {
  "project_id": number
  "workspace_id": number
  "presentation": Record<string, unknown>
  "suggested_components"?: (Record<string, unknown>)[]
  "build_extra_assets_json"?: Record<string, unknown>
}

export type ExternalProjectConfigurationUpdateRequest = {
  "configuration"?: Record<string, unknown>
  "build_extra_assets_json"?: (Record<string, unknown>) | (null)
}

export type ExternalProjectCreateRequest = {
  "name": string
  "description"?: (string) | (null)
  "status"?: string
  "configuration"?: (ProjectDefaultConfiguration) | (ProjectStyleConfiguration) | (ProjectCustomConfiguration)
  "build_extra_assets_json"?: (Record<string, unknown>) | (null)
}

export type ExternalStandardResponse = {
  "standard_type": string
  "markdown": string
}

export type ExternalStyleCreateRequest = {
  "name": string
  "key"?: (string) | (null)
  "description"?: (string) | (null)
  "configuration"?: StyleConfiguration
  "page_width"?: (number) | (null)
  "page_height"?: (number) | (null)
  "base_font_size"?: (string) | (null)
  "icon_default_stroke_width"?: (number) | (null)
  "show_pdf_export_button"?: (boolean) | (null)
  "menu_mode"?: ("text" | "preview" | "bottom-preview") | (null)
  "theme_key"?: (string) | (null)
  "style_spec_markdown"?: (string) | (null)
}

export type ExternalSystemHealthResponse = {
  "status"?: string
  "database"?: boolean
  "redis"?: boolean
}

export type ExternalSystemVersionResponse = {
  "version": string
  "api_version"?: string
  "app_name": string
}

export type ExternalThemeCreateRequest = {
  "key": string
  "name": string
  "description"?: (string) | (null)
  "palette"?: (Record<string, unknown>) | (null)
}

export type ExternalWhoAmIResponse = {
  "user": Record<string, unknown>
  "token"?: (Record<string, unknown>) | (null)
  "workspaces"?: (Record<string, unknown>)[]
}

export type HTTPValidationError = {
  "detail"?: (ValidationError)[]
}

export type ImageBindingItem = {
  "slot"?: string
  "model_config_id"?: (number) | (null)
  "model_name"?: (string) | (null)
  "provider_config_id"?: (number) | (null)
  "provider_config_name"?: (string) | (null)
  "provider_key"?: (string) | (null)
  "provider_name"?: (string) | (null)
  "model_id"?: (string) | (null)
  "binding_ready": boolean
  "inherited_from_global"?: boolean
}

export type ImageBindingUpdate = {
  "model_config_id"?: (number) | (null)
  "scope"?: AiLlmConfigScope
}

export type ImageModelConfigCreate = {
  "name": string
  "scope"?: AiLlmConfigScope
  "provider_config_id": number
  "model_id": string
  "advanced_config"?: Record<string, unknown>
}

export type ImageModelConfigItem = {
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

export type ImageModelConfigUpdate = {
  "name"?: (string) | (null)
  "provider_config_id"?: (number) | (null)
  "model_id"?: (string) | (null)
  "advanced_config"?: (Record<string, unknown>) | (null)
  "status"?: ("active" | "archived") | (null)
}

export type ImageProviderCatalogItem = {
  "provider_key": string
  "name": string
  "docs_url": string
  "default_base_url"?: (string) | (null)
  "requires_base_url": boolean
  "models": (Record<string, unknown>)[]
}

export type ImageProviderConfigCreate = {
  "name": string
  "scope"?: AiLlmConfigScope
  "provider_key": string
  "base_url"?: (string) | (null)
  "api_key"?: (string) | (null)
}

export type ImageProviderConfigItem = {
  "id": number
  "scope": string
  "editable": boolean
  "name": string
  "provider_key": string
  "provider_name": string
  "base_url"?: (string) | (null)
  "has_api_key": boolean
  "api_key_masked"?: (string) | (null)
  "status": string
}

export type ImageProviderConfigUpdate = {
  "name"?: (string) | (null)
  "base_url"?: (string) | (null)
  "api_key"?: (string) | (null)
  "status"?: ("active" | "archived") | (null)
}

export type JsonValue = unknown

export type LoginRequest = {
  "username": string
  "password": string
}

export type LoginResponse = {
  "user": AuthUser
}

export type MessageResponse = {
  "message": string
}

export type ModelCatalogSyncItem = {
  "catalog_version"?: (string) | (null)
  "last_attempt_at"?: (string) | (null)
  "last_success_at"?: (string) | (null)
  "last_error"?: (string) | (null)
  "syncing"?: boolean
}

export type PageComponentResourceItem = {
  "component_name": string
  "resource_attr": string
  "resource_name": string
}

export type PageCopyToProjectRequest = {
  "target_project_id": number
  "title"?: (string) | (null)
  "summary"?: (string) | (null)
  "route_placement"?: "none" | "root" | "group"
  "parent_route_id"?: (number) | (null)
  "route"?: (string) | (null)
}

export type PageCreateRequest = {
  "page_content": string
  "file_type"?: PageFileType
  "title": string
  "summary"?: (string) | (null)
  "speaker_notes"?: (string) | (null)
  "status"?: RecordStatus
  "workspace_id"?: (number) | (null)
  "project_id"?: (number) | (null)
}

export type PageCurrentComponentIndex = {
  "page_id": number
  "current_version_no": number
  "page_version_id": (number) | (null)
  "components": (string)[]
  "resources": (PageComponentResourceItem)[]
}

export type PageCurrentModuleDependencies = {
  "page_id": number
  "current_version_no": number
  "page_version_id": (number) | (null)
  "dependencies": (PageModuleDependencyItem)[]
}

export type PageFileType = "vue" | "ts" | "js" | "json" | "md" | "txt" | "yaml"

export type PageItem = {
  "id": number
  "code": string
  "page_content": string
  "current_version_no": number
  "file_type": PageFileType
  "title": string
  "summary": (string) | (null)
  "speaker_notes"?: (string) | (null)
  "status": RecordStatus
  "workspace_id": (number) | (null)
  "workspace_name"?: (string) | (null)
  "project_id": (number) | (null)
  "project_name"?: (string) | (null)
  "created_at": string
  "updated_at": string
  "created_by": (number) | (null)
  "updated_by": (number) | (null)
  "screenshot_url"?: (string) | (null)
  "screenshot_version_no"?: (number) | (null)
  "screenshot_config_hash"?: (string) | (null)
  "screenshot_viewport_width"?: (number) | (null)
  "screenshot_viewport_height"?: (number) | (null)
  "screenshot_is_latest"?: boolean
  "screenshot_updated_at"?: (string) | (null)
  "is_in_project_route"?: (boolean) | (null)
  "route_bindings"?: (ProjectRoutePageBinding)[]
}

export type PageModuleDependencyItem = {
  "dependency_kind": string
  "component_code"?: (string) | (null)
  "component_version_no"?: (number) | (null)
  "runtime_module_path"?: (string) | (null)
  "runtime_kit_name"?: (string) | (null)
  "runtime_kit_base_name"?: (string) | (null)
  "runtime_kit_version_no"?: (number) | (null)
  "runtime_kit_import_path"?: (string) | (null)
}

export type PageScreenshotBatchDownloadRequest = {
  "page_ids": (number)[]
}

export type PageScreenshotBatchFailure = {
  "page_id": number
  "code": string
  "detail": string
}

export type PageScreenshotBatchRefreshRequest = {
  "project_id": number
}

export type PageScreenshotBatchRefreshResponse = {
  "requested_count": number
  "succeeded_count": number
  "failed_count": number
  "page_ids"?: (number)[]
  "failures"?: (PageScreenshotBatchFailure)[]
}

export type PageScreenshotJobGroupResponse = {
  "job_group_id": string
  "status": "pending" | "running" | "succeeded" | "failed" | "partial" | "cancelled"
  "requested_count": number
  "pending_count": number
  "running_count": number
  "succeeded_count": number
  "failed_count": number
  "skipped_count": number
  "cancelled_count": number
  "page_ids"?: (number)[]
  "jobs"?: (PageScreenshotJobResponse)[]
  "failures"?: (PageScreenshotBatchFailure)[]
}

export type PageScreenshotJobRequest = {
  "viewport_width"?: (number) | (null)
  "viewport_height"?: (number) | (null)
}

export type PageScreenshotJobResponse = {
  "id": number
  "job_group_id": (string) | (null)
  "source": string
  "page_id": number
  "workspace_id": (number) | (null)
  "project_id": (number) | (null)
  "viewport_width": number
  "viewport_height": number
  "target_page_version_no": number
  "config_hash": string
  "status": "pending" | "running" | "succeeded" | "failed" | "skipped" | "cancelled"
  "attempt_count": number
  "error_code": (string) | (null)
  "error_message": (string) | (null)
  "created_by": (number) | (null)
  "created_at": string
  "updated_at": string
  "started_at": (string) | (null)
  "finished_at": (string) | (null)
  "cancel_requested_at": (string) | (null)
}

export type PageScreenshotRequest = {
  "viewport_width"?: (number) | (null)
  "viewport_height"?: (number) | (null)
}

export type PageSnapshotCreateRequest = {
  "snapshot_name"?: (string) | (null)
}

export type PageUpdateRequest = {
  "page_content"?: (string) | (null)
  "file_type"?: (PageFileType) | (null)
  "change_note"?: (string) | (null)
  "title"?: (string) | (null)
  "summary"?: (string) | (null)
  "speaker_notes"?: (string) | (null)
  "status"?: (RecordStatus) | (null)
  "workspace_id"?: (number) | (null)
  "project_id"?: (number) | (null)
}

export type PageVersionContent = {
  "page_id": number
  "version_no": number
  "version_label": string
  "file_type": PageFileType
  "storage_type": PageVersionStorageType
  "is_important": boolean
  "snapshot_name": (string) | (null)
  "change_note": (string) | (null)
  "speaker_notes"?: (string) | (null)
  "content_mode": "full" | "diff"
  "content": string
  "resolved_content": string
  "created_at": string
  "created_by": (number) | (null)
}

export type PageVersionListItem = {
  "id": number
  "page_id": number
  "version_no": number
  "version_label": string
  "file_type": PageFileType
  "storage_type": PageVersionStorageType
  "is_important": boolean
  "is_current": boolean
  "snapshot_name": (string) | (null)
  "change_note": (string) | (null)
  "content_size": number
  "created_at": string
  "created_by": (number) | (null)
}

export type PageVersionRestoreRequest = {
  "change_note"?: (string) | (null)
}

export type PageVersionStorageType = "snapshot" | "diff"

export type PageVisualEditApplyDiagnostic = {
  "severity": "error" | "warning" | "info"
  "source": string
  "code": string
  "message": string
  "node_id"?: (string) | (null)
  "binding_id"?: (string) | (null)
}

export type PageVisualEditApplyRequest = {
  "protocolVersion": 1
  "artifactId": string
  "baseVersionNo": number
  "sourceHash": string
  "operations": ((PageVisualEditSetValueOperation) | (PageVisualEditSetJsonOperation) | (PageVisualEditSetRichTextOperation) | (PageVisualEditSetTailwindTokensOperation) | (PageVisualEditDuplicateNodeOperation) | (PageVisualEditDeleteNodeOperation))[]
  "changeNote"?: (string) | (null)
}

export type PageVisualEditApplyResponse = {
  "protocol_version": 1
  "success"?: true
  "page_id": number
  "previous_version_no": number
  "current_version_no": number
  "source_hash": string
  "operations_applied": number
  "canonical_diff": string
  "diagnostics"?: (PageVisualEditApplyDiagnostic)[]
  "refresh_required"?: true
}

export type PageVisualEditBinding = {
  "binding_id": string
  "node_id": string
  "kind": "text" | "rich_text" | "class" | "prop" | "json"
  "name"?: (string) | (null)
  "value_type": "string" | "number" | "boolean" | "null" | "json" | "unknown"
  "value"?: JsonValue
  "expression"?: (string) | (null)
  "source_range": PageVisualEditSourceRange
  "editable": boolean
  "readonly_reason"?: ("SFC_PARSE_ERROR" | "TEMPLATE_UNSUPPORTED" | "DYNAMIC_EXPRESSION" | "DYNAMIC_SCRIPT_SOURCE" | "SCRIPT_SOURCE_NOT_FOUND" | "LOOP_SOURCE_UNSUPPORTED" | "NESTED_LOOP_UNSUPPORTED" | "LOOP_MEMBER_UNSUPPORTED" | "MEMBER_NOT_FOUND" | "MEMBER_VALUE_DYNAMIC" | "ATTRIBUTE_VALUE_MISSING" | "RICH_TEXT_DYNAMIC_CONTENT" | "RICH_TEXT_UNSUPPORTED_STRUCTURE" | "RICH_TEXT_SOURCE_RANGE_UNRESOLVED" | "STRUCTURE_ROOT_UNSUPPORTED" | "STRUCTURE_CONTROL_FLOW_UNSUPPORTED" | "STRUCTURE_LOOP_INSTANCE_REQUIRED") | (null)
  "source"?: ((PageVisualEditScriptArrayBindingSource) | (PageVisualEditTemplateBindingSource) | (PageVisualEditTemplateRichTextBindingSource) | (PageVisualEditJsonBindingSource)) | (null)
}

export type PageVisualEditComponentPropField = {
  "type": "string" | "textarea" | "number" | "boolean" | "select" | "json"
  "label"?: (string) | (null)
  "description"?: (string) | (null)
  "required"?: (boolean) | (null)
  "default"?: JsonValue
  "placeholder"?: (string) | (null)
  "options"?: ((PageVisualEditComponentSelectOption)[]) | (null)
}

export type PageVisualEditComponentSchema = {
  "source": "workspace_component" | "runtime_kit"
  "import_path": string
  "component_code": string
  "version_no": number
  "props"?: (Record<string, unknown>) | (null)
}

export type PageVisualEditComponentSelectOption = {
  "label": string
  "value": (string) | (number) | (number) | (boolean)
}

export type PageVisualEditDeleteNodeOperation = {
  "nodeId": string
  "instancePath"?: (PageVisualEditInstancePathSegment)[]
  "type": "delete_node"
}

export type PageVisualEditDiagnostic = {
  "severity": "warning" | "error"
  "code": "SFC_PARSE_ERROR" | "TEMPLATE_UNSUPPORTED" | "DYNAMIC_EXPRESSION" | "DYNAMIC_SCRIPT_SOURCE" | "SCRIPT_SOURCE_NOT_FOUND" | "LOOP_SOURCE_UNSUPPORTED" | "NESTED_LOOP_UNSUPPORTED" | "LOOP_MEMBER_UNSUPPORTED" | "MEMBER_NOT_FOUND" | "MEMBER_VALUE_DYNAMIC" | "ATTRIBUTE_VALUE_MISSING" | "RICH_TEXT_DYNAMIC_CONTENT" | "RICH_TEXT_UNSUPPORTED_STRUCTURE" | "RICH_TEXT_SOURCE_RANGE_UNRESOLVED" | "STRUCTURE_ROOT_UNSUPPORTED" | "STRUCTURE_CONTROL_FLOW_UNSUPPORTED" | "STRUCTURE_LOOP_INSTANCE_REQUIRED"
  "message": string
  "source_range"?: (PageVisualEditSourceRange) | (null)
}

export type PageVisualEditDuplicateNodeOperation = {
  "nodeId": string
  "instancePath"?: (PageVisualEditInstancePathSegment)[]
  "type": "duplicate_node"
}

export type PageVisualEditInstancePathSegment = {
  "loopNodeId": string
  "key"?: (string) | (number) | (null)
  "index"?: (number) | (null)
}

export type PageVisualEditJsonBindingSource = {
  "kind": "json-source"
  "source_id": string
}

export type PageVisualEditJsonSource = {
  "source_id": string
  "kind": "const" | "ref" | "reactive" | "template-expression"
  "name"?: (string) | (null)
  "value": JsonValue
  "source_range": PageVisualEditSourceRange
  "editable": true
}

export type PageVisualEditLoopContext = {
  "loop_node_id": string
  "source_expression": string
  "source_binding"?: (string) | (null)
  "item_alias": string
  "index_alias"?: (string) | (null)
  "key_expression"?: (string) | (null)
  "key_member"?: (string) | (null)
  "editable": boolean
  "readonly_reason"?: ("SFC_PARSE_ERROR" | "TEMPLATE_UNSUPPORTED" | "DYNAMIC_EXPRESSION" | "DYNAMIC_SCRIPT_SOURCE" | "SCRIPT_SOURCE_NOT_FOUND" | "LOOP_SOURCE_UNSUPPORTED" | "NESTED_LOOP_UNSUPPORTED" | "LOOP_MEMBER_UNSUPPORTED" | "MEMBER_NOT_FOUND" | "MEMBER_VALUE_DYNAMIC" | "ATTRIBUTE_VALUE_MISSING" | "RICH_TEXT_DYNAMIC_CONTENT" | "RICH_TEXT_UNSUPPORTED_STRUCTURE" | "RICH_TEXT_SOURCE_RANGE_UNRESOLVED" | "STRUCTURE_ROOT_UNSUPPORTED" | "STRUCTURE_CONTROL_FLOW_UNSUPPORTED" | "STRUCTURE_LOOP_INSTANCE_REQUIRED") | (null)
}

export type PageVisualEditLoopItemActions = {
  "can_duplicate": boolean
  "can_delete": boolean
  "loop_node_id": string
  "collection_name": string
  "key_member": string
  "instances": (PageVisualEditLoopItemLocation)[]
  "readonly_reason"?: ("SFC_PARSE_ERROR" | "TEMPLATE_UNSUPPORTED" | "DYNAMIC_EXPRESSION" | "DYNAMIC_SCRIPT_SOURCE" | "SCRIPT_SOURCE_NOT_FOUND" | "LOOP_SOURCE_UNSUPPORTED" | "NESTED_LOOP_UNSUPPORTED" | "LOOP_MEMBER_UNSUPPORTED" | "MEMBER_NOT_FOUND" | "MEMBER_VALUE_DYNAMIC" | "ATTRIBUTE_VALUE_MISSING" | "RICH_TEXT_DYNAMIC_CONTENT" | "RICH_TEXT_UNSUPPORTED_STRUCTURE" | "RICH_TEXT_SOURCE_RANGE_UNRESOLVED" | "STRUCTURE_ROOT_UNSUPPORTED" | "STRUCTURE_CONTROL_FLOW_UNSUPPORTED" | "STRUCTURE_LOOP_INSTANCE_REQUIRED") | (null)
}

export type PageVisualEditLoopItemLocation = {
  "index": number
  "key": (string) | (number)
}

export type PageVisualEditManifest = {
  "protocol_version": 1
  "module_path": string
  "source_hash": string
  "root": PageVisualEditNode
  "diagnostics"?: (PageVisualEditDiagnostic)[]
  "tailwind_catalog": PageVisualEditTailwindCatalog
  "json_sources": (PageVisualEditJsonSource)[]
}

export type PageVisualEditNode = {
  "node_id": string
  "kind": "root" | "element" | "component"
  "tag": string
  "source_range": PageVisualEditSourceRange
  "loop_context"?: (PageVisualEditLoopContext) | (null)
  "template_actions": PageVisualEditTemplateActions
  "loop_item_actions"?: (PageVisualEditLoopItemActions) | (null)
  "bindings"?: (PageVisualEditBinding)[]
  "children"?: (PageVisualEditNode)[]
}

export type PageVisualEditPreviewArtifactCreateRequest = {
  "protocolVersion": 1
  "baseVersionNo": number
}

export type PageVisualEditPreviewArtifactResponse = {
  "preview_url": string
  "artifact_id": string
  "preview_kind": "page"
  "entry_descriptor": PageVisualEditPreviewEntryDescriptor
  "viewport_width": number
  "viewport_height": number
  "project_id": number
  "workspace_id": number
  "visual_edit": PageVisualEditPreviewContext
}

export type PageVisualEditPreviewContext = {
  "protocol_version": 1
  "page_id": number
  "base_version_no": number
  "source_hash": string
  "module_path": string
  "manifest": PageVisualEditManifest
  "component_schemas": Record<string, unknown>
  "warnings"?: (PageVisualEditDiagnostic)[]
}

export type PageVisualEditPreviewEntryDescriptor = {
  "entry_type": "module"
  "module_path": string
  "route"?: null
}

export type PageVisualEditScriptArrayBindingSource = {
  "kind": "script-array-item"
  "collection_name": string
  "collection_kind": "const-array" | "ref-array" | "reactive-array"
  "item_alias": string
  "member": string
  "key_member"?: (string) | (null)
  "locations"?: (PageVisualEditScriptMemberLocation)[]
}

export type PageVisualEditScriptMemberLocation = {
  "index": number
  "key"?: (string) | (number) | (null)
  "value"?: (string) | (number) | (number) | (boolean) | (null)
  "source_range"?: (PageVisualEditSourceRange) | (null)
  "editable": boolean
  "readonly_reason"?: ("SFC_PARSE_ERROR" | "TEMPLATE_UNSUPPORTED" | "DYNAMIC_EXPRESSION" | "DYNAMIC_SCRIPT_SOURCE" | "SCRIPT_SOURCE_NOT_FOUND" | "LOOP_SOURCE_UNSUPPORTED" | "NESTED_LOOP_UNSUPPORTED" | "LOOP_MEMBER_UNSUPPORTED" | "MEMBER_NOT_FOUND" | "MEMBER_VALUE_DYNAMIC" | "ATTRIBUTE_VALUE_MISSING" | "RICH_TEXT_DYNAMIC_CONTENT" | "RICH_TEXT_UNSUPPORTED_STRUCTURE" | "RICH_TEXT_SOURCE_RANGE_UNRESOLVED" | "STRUCTURE_ROOT_UNSUPPORTED" | "STRUCTURE_CONTROL_FLOW_UNSUPPORTED" | "STRUCTURE_LOOP_INSTANCE_REQUIRED") | (null)
}

export type PageVisualEditSetJsonOperation = {
  "type": "set_json"
  "sourceId": string
  "value": JsonValue
}

export type PageVisualEditSetRichTextOperation = {
  "nodeId": string
  "instancePath"?: (PageVisualEditInstancePathSegment)[]
  "bindingId": string
  "type": "set_rich_text"
  "html": string
}

export type PageVisualEditSetTailwindTokensOperation = {
  "nodeId": string
  "instancePath"?: (PageVisualEditInstancePathSegment)[]
  "bindingId": string
  "type": "set_tailwind_tokens"
  "changes": (PageVisualEditTailwindTokenChange)[]
}

export type PageVisualEditSetValueOperation = {
  "nodeId": string
  "instancePath"?: (PageVisualEditInstancePathSegment)[]
  "bindingId": string
  "type": "set_value"
  "value": (string) | (number) | (number) | (boolean) | (null)
}

export type PageVisualEditSourceRange = {
  "start": number
  "end": number
}

export type PageVisualEditTailwindCatalog = {
  "version": 1
  "groups"?: (PageVisualEditTailwindGroup)[]
}

export type PageVisualEditTailwindGroup = {
  "key": string
  "label": string
  "options"?: (PageVisualEditTailwindOption)[]
}

export type PageVisualEditTailwindOption = {
  "class_name": string
  "label": string
}

export type PageVisualEditTailwindTokenChange = {
  "group": string
  "className"?: (string) | (null)
}

export type PageVisualEditTemplateActions = {
  "can_duplicate": boolean
  "can_delete": boolean
  "readonly_reason"?: ("SFC_PARSE_ERROR" | "TEMPLATE_UNSUPPORTED" | "DYNAMIC_EXPRESSION" | "DYNAMIC_SCRIPT_SOURCE" | "SCRIPT_SOURCE_NOT_FOUND" | "LOOP_SOURCE_UNSUPPORTED" | "NESTED_LOOP_UNSUPPORTED" | "LOOP_MEMBER_UNSUPPORTED" | "MEMBER_NOT_FOUND" | "MEMBER_VALUE_DYNAMIC" | "ATTRIBUTE_VALUE_MISSING" | "RICH_TEXT_DYNAMIC_CONTENT" | "RICH_TEXT_UNSUPPORTED_STRUCTURE" | "RICH_TEXT_SOURCE_RANGE_UNRESOLVED" | "STRUCTURE_ROOT_UNSUPPORTED" | "STRUCTURE_CONTROL_FLOW_UNSUPPORTED" | "STRUCTURE_LOOP_INSTANCE_REQUIRED") | (null)
}

export type PageVisualEditTemplateBindingSource = {
  "kind": "template-literal"
}

export type PageVisualEditTemplateRichTextBindingSource = {
  "kind": "template-rich-text"
}

export type PagedResponse_AssetResponse_ = {
  "items": (AssetResponse)[]
  "total": number
  "page": number
  "page_size": number
}

export type PagedResponse_PageItem_ = {
  "items": (PageItem)[]
  "total": number
  "page": number
  "page_size": number
}

export type PagedResponse_ProjectItem_ = {
  "items": (ProjectItem)[]
  "total": number
  "page": number
  "page_size": number
}

export type PagedResponse_Union_WorkspaceComponentItem__SuggestedComponentItem__ = {
  "items": ((WorkspaceComponentItem) | (SuggestedComponentItem))[]
  "total": number
  "page": number
  "page_size": number
}

export type PagedResponse_WorkspaceComponentItem_ = {
  "items": (WorkspaceComponentItem)[]
  "total": number
  "page": number
  "page_size": number
}

export type PagedResponse_WorkspaceFontConfigResponse_ = {
  "items": (WorkspaceFontConfigResponse)[]
  "total": number
  "page": number
  "page_size": number
}

export type PagedResponse_WorkspaceFontFamilyResponse_ = {
  "items": (WorkspaceFontFamilyResponse)[]
  "total": number
  "page": number
  "page_size": number
}

export type PagedResponse_WorkspaceItem_ = {
  "items": (WorkspaceItem)[]
  "total": number
  "page": number
  "page_size": number
}

export type PagedResponse_WorkspaceStyleItem_ = {
  "items": (WorkspaceStyleItem)[]
  "total": number
  "page": number
  "page_size": number
}

export type PagedResponse_WorkspaceThemeItem_ = {
  "items": (WorkspaceThemeItem)[]
  "total": number
  "page": number
  "page_size": number
}

export type PresentationConfig = {
  "page_width"?: number
  "page_height"?: number
  "base_font_size"?: string
  "icon_default_stroke_width"?: number
  "show_pdf_export_button"?: boolean
  "menu_mode"?: "text" | "preview" | "bottom-preview"
  "theme_key"?: (string) | (null)
  "style_spec_markdown"?: string
}

export type PresentationConfigPatch = {
  "page_width"?: (number) | (null)
  "page_height"?: (number) | (null)
  "base_font_size"?: (string) | (null)
  "icon_default_stroke_width"?: (number) | (null)
  "show_pdf_export_button"?: (boolean) | (null)
  "menu_mode"?: ("text" | "preview" | "bottom-preview") | (null)
  "theme_key"?: (string) | (null)
  "style_spec_markdown"?: (string) | (null)
}

export type PreviewArtifactCreateRequest = {
  "entry_descriptor"?: (PreviewEntryDescriptor) | (null)
}

export type PreviewArtifactResponse = {
  "preview_url": string
  "artifact_id": string
  "preview_kind": "project" | "page" | "component" | "asset"
  "entry_descriptor": PreviewEntryDescriptor
  "viewport_width": number
  "viewport_height": number
  "project_id"?: (number) | (null)
  "workspace_id"?: (number) | (null)
  "component_preview_mode"?: ("saved" | "draft") | (null)
  "component_source"?: ("workspace_component" | "runtime_kit") | (null)
  "component_code"?: (string) | (null)
  "component_version_no"?: (number) | (null)
  "runtime_kit_component_name"?: (string) | (null)
  "runtime_kit_manifest_version"?: (string) | (null)
  "asset_id"?: (number) | (null)
  "asset_name"?: (string) | (null)
}

export type PreviewEntryDescriptor = {
  "entry_type": "route" | "module" | "component_host" | "asset_host"
  "route"?: (string) | (null)
  "module_path"?: (string) | (null)
}

export type PreviewServiceTokenExchangeRequest = {
  "preview_token": string
}

export type PreviewServiceTokenExchangeResponse = {
  "service_token": string
  "token_type"?: string
  "expires_in": number
  "artifact_id": string
  "scope"?: string
}

export type PreviewSizePreset = {
  "name": string
  "width": number
  "height": number
  "base_font_size"?: string
  "icon_default_stroke_width"?: number
}

export type PreviewSizePresetUpdateRequest = {
  "presets"?: (PreviewSizePreset)[]
}

export type ProjectBuildAssetSummary = {
  "automatic_asset_names"?: (string)[]
  "extra_asset_names"?: (string)[]
  "included_asset_names"?: (string)[]
  "dynamic_module_paths"?: (string)[]
}

export type ProjectBuildCreateRequest = {
  "base_url"?: string
}

export type ProjectBuildExtraAssetsConfig = {
  "asset_names"?: (string)[]
}

export type ProjectBuildJobResponse = {
  "id": number
  "project_id": number
  "snapshot_release_id": number
  "base_url": string
  "status": "pending" | "running" | "succeeded" | "failed"
  "error_message": (string) | (null)
  "artifact_storage_key": (string) | (null)
  "artifact_download_url": (string) | (null)
  "artifact_proxy_url"?: (string) | (null)
  "artifact_entry_file": (string) | (null)
  "artifact_sha256": (string) | (null)
  "artifact_size_bytes": (number) | (null)
  "created_by": (number) | (null)
  "created_at": string
  "updated_at": string
  "started_at": (string) | (null)
  "finished_at": (string) | (null)
  "attempt_id"?: (string) | (null)
  "attempt_count"?: (number) | (null)
  "max_attempts"?: (number) | (null)
}

export type ProjectCreateRequest = {
  "workspace_id": number
  "name": string
  "description"?: (string) | (null)
  "status"?: RecordStatus
  "configuration"?: (ProjectDefaultConfiguration) | (ProjectStyleConfiguration) | (ProjectCustomConfiguration)
  "build_extra_assets_json"?: ProjectBuildExtraAssetsConfig
}

export type ProjectCustomConfiguration = {
  "presentation"?: PresentationConfig
  "suggested_components"?: SuggestedComponentsSelection
  "mode": "custom"
}

export type ProjectDefaultConfiguration = {
  "mode"?: "default"
}

export type ProjectItem = {
  "id": number
  "workspace_id": number
  "workspace_name": string
  "code": string
  "name": string
  "description": (string) | (null)
  "is_system_managed"?: boolean
  "status": RecordStatus
  "archived_at": (string) | (null)
  "page_width": number
  "page_height": number
  "base_font_size": string
  "icon_default_stroke_width": number
  "show_pdf_export_button": boolean
  "menu_mode": "text" | "preview" | "bottom-preview"
  "theme_key": (string) | (null)
  "style_spec_markdown": string
  "build_extra_assets_json": ProjectBuildExtraAssetsConfig
  "routed_page_count"?: number
  "total_page_count"?: number
  "first_page_title"?: (string) | (null)
  "first_page_screenshot_url"?: (string) | (null)
  "created_at": string
  "updated_at": string
  "created_by": (number) | (null)
  "updated_by": (number) | (null)
}

export type ProjectPatchConfiguration = {
  "presentation"?: (PresentationConfigPatch) | (null)
  "suggested_components"?: (SuggestedComponentsSelection) | (null)
  "mode": "patch"
}

export type ProjectRouteChildItem = {
  "id": number
  "route_type"?: "page"
  "route": string
  "order": number
  "hidden"?: boolean
  "page_id": number
  "page_code": string
  "page_title": string
  "display_title": string
}

export type ProjectRouteChildWrite = {
  "route": string
  "order": number
  "hidden"?: boolean
  "page_id": number
}

export type ProjectRouteItemWrite = {
  "route_type": "group" | "page"
  "route": string
  "order": number
  "hidden"?: boolean
  "group_title"?: (string) | (null)
  "page_id"?: (number) | (null)
  "children"?: (ProjectRouteChildWrite)[]
}

export type ProjectRoutePageBinding = {
  "route_id": number
  "parent_route"?: (string) | (null)
  "route": string
  "full_path": string
  "parent_order"?: (number) | (null)
  "order": number
}

export type ProjectRouteTreeItem = {
  "id": number
  "route_type": "group" | "page"
  "route": string
  "order": number
  "hidden"?: boolean
  "group_title"?: (string) | (null)
  "page_id"?: (number) | (null)
  "page_code"?: (string) | (null)
  "page_title"?: (string) | (null)
  "display_title": string
  "children"?: (ProjectRouteChildItem)[]
}

export type ProjectRouteTreeResponse = {
  "routes"?: (ProjectRouteTreeItem)[]
}

export type ProjectRouteTreeWriteRequest = {
  "routes"?: (ProjectRouteItemWrite)[]
}

export type ProjectStyleConfiguration = {
  "mode": "style"
  "style_id": number
}

export type ProjectSuggestedReferenceAssetItem = {
  "id": number
  "name": string
  "original_name": string
  "description"?: (string) | (null)
  "asset_type": AssetType
  "content_editable"?: boolean
  "approx_aspect_ratio"?: (string) | (null)
  "approx_aspect_ratio_value"?: (number) | (null)
  "aspect_ratio_source"?: (string) | (null)
}

export type ProjectSuggestedReferenceAssetsResponse = {
  "items"?: (ProjectSuggestedReferenceAssetItem)[]
}

export type ProjectSuggestedReferenceAssetsUpdateRequest = {
  "asset_ids"?: (number)[]
}

export type ProjectTemplateExportRequest = {
  "metadata"?: ProjectTemplateMetadataPayload
  "cover_page_id"?: (number) | (null)
  "manual_asset_names"?: (string)[]
  "refresh_screenshots"?: boolean
}

export type ProjectTemplateExportValidationResult = {
  "can_export"?: boolean
  "project": ProjectTemplatePackageProjectSummary
  "pages"?: (ProjectTemplatePackagePageSummary)[]
  "components"?: (ComponentShareExportComponentSummary)[]
  "automatic_assets"?: (ComponentShareExportAssetSummary)[]
  "manual_assets"?: (ComponentShareExportAssetSummary)[]
  "themes"?: (WorkspaceStylePackageThemeSummary)[]
  "fonts"?: (ComponentSharePackageFontSummary)[]
  "screenshots"?: ProjectTemplateScreenshotSummary
  "warnings"?: (string)[]
  "errors"?: (string)[]
  "missing_static_asset_names"?: (string)[]
  "missing_manual_asset_names"?: (string)[]
  "dynamic_resource_modules"?: (string)[]
}

export type ProjectTemplateImportResult = {
  "project_id": number
  "project_code": string
  "project_name": string
  "page_ids"?: (number)[]
  "pages"?: (ProjectTemplatePackagePageSummary)[]
  "components"?: (ComponentSharePackageComponentSummary)[]
  "assets"?: (ComponentSharePackageAssetSummary)[]
  "themes"?: (WorkspaceStylePackageThemeSummary)[]
  "fonts"?: (ComponentSharePackageFontSummary)[]
  "warnings"?: (string)[]
}

export type ProjectTemplateImportValidationResult = {
  "valid": boolean
  "schema_version"?: (number) | (null)
  "runtime_kit_manifest_version"?: (string) | (null)
  "template"?: Record<string, unknown>
  "project"?: (ProjectTemplatePackageProjectSummary) | (null)
  "pages"?: (ProjectTemplatePackagePageSummary)[]
  "components"?: (ComponentSharePackageComponentSummary)[]
  "assets"?: (ComponentSharePackageAssetSummary)[]
  "themes"?: (WorkspaceStylePackageThemeSummary)[]
  "fonts"?: (ComponentSharePackageFontSummary)[]
  "screenshots"?: ProjectTemplateScreenshotSummary
  "errors"?: (string)[]
  "warnings"?: (string)[]
}

export type ProjectTemplateMetadataPayload = {
  "slug"?: (string) | (null)
  "name"?: (string) | (null)
  "summary"?: (string) | (null)
  "description"?: (string) | (null)
}

export type ProjectTemplatePackagePageSummary = {
  "source_page_code": string
  "title": string
  "summary"?: (string) | (null)
  "file_type": PageFileType
  "action"?: "create"
}

export type ProjectTemplatePackageProjectSummary = {
  "source_project_code": string
  "name": string
  "description"?: (string) | (null)
  "page_width": number
  "page_height": number
  "base_font_size": string
  "icon_default_stroke_width": number
  "show_pdf_export_button": boolean
  "menu_mode": "text" | "preview" | "bottom-preview"
  "theme_key"?: (string) | (null)
  "style_spec_markdown"?: string
}

export type ProjectTemplateScreenshotItem = {
  "path": string
  "width": number
  "height": number
  "source_page_code"?: (string) | (null)
  "title"?: (string) | (null)
  "order"?: (number) | (null)
}

export type ProjectTemplateScreenshotSummary = {
  "cover"?: (ProjectTemplateScreenshotItem) | (null)
  "pages"?: (ProjectTemplateScreenshotItem)[]
}

export type ProjectUpdateRequest = {
  "workspace_id"?: (number) | (null)
  "name"?: (string) | (null)
  "description"?: (string) | (null)
  "status"?: (RecordStatus) | (null)
  "configuration"?: ((ProjectPatchConfiguration) | (ProjectStyleConfiguration)) | (null)
  "build_extra_assets_json"?: (ProjectBuildExtraAssetsConfig) | (null)
}

export type ReasoningPolicy = {
  "mode"?: "auto" | "disabled" | "effort" | "budget_tokens"
  "value"?: (string) | (number) | (null)
}

export type RecordStatus = "active" | "archived"

export type RenameAgentSessionRequest = {
  "session_name"?: (string) | (null)
  "autogenerate"?: boolean
}

export type RuntimeKitCapabilityItem = {
  "kind": "component" | "composable" | "util" | "type"
  "base_name": string
  "version_no": number
  "name": string
  "import_path": string
  "category": string
  "description": string
  "display_name": string
  "summary": string
  "tags": (string)[]
  "previewable": boolean
  "preview_schema"?: (Record<string, unknown>) | (null)
  "preview_options"?: (Record<string, unknown>) | (null)
  "usage": (string)[]
  "returns"?: (string) | (null)
  "return_example": (string)[]
  "constraints": (string)[]
  "audiences": ("backend" | "agent")[]
  "manifest_version": string
}

export type RuntimeKitCapabilityListResponse = {
  "items": (RuntimeKitCapabilityItem)[]
  "total": number
  "manifest_version"?: (string) | (null)
}

export type RuntimeKitComponentPreviewRequest = {
  "workspace_id": number
  "preview_options"?: (ComponentPreviewOptions) | (null)
}

export type RuntimeModuleBatchRequest = {
  "paths": (string)[]
}

export type StyleConfiguration = {
  "presentation"?: PresentationConfig
  "suggested_components"?: SuggestedComponentsSelection
}

export type StyleConfigurationPatch = {
  "presentation"?: (PresentationConfigPatch) | (null)
  "suggested_components"?: (SuggestedComponentsSelection) | (null)
}

export type SuggestedComponentItem = {
  "id": number
  "code": string
  "name": string
  "import_name": string
  "component_type": WorkspaceComponentType
  "summary": (string) | (null)
  "current_version_no": number
  "available"?: boolean
  "unavailable_reason"?: (string) | (null)
  "import_path"?: (string) | (null)
  "import_statement"?: (string) | (null)
}

export type SuggestedComponentsResponse = {
  "items"?: (SuggestedComponentItem)[]
}

export type SuggestedComponentsSelection = {
  "component_ids"?: (number)[]
}

export type ThemeBackgroundPalette = {
  "default": string
  "invert": string
}

export type ThemeBorderPalette = {
  "default": string
  "subtle": string
}

export type ThemeLinkPalette = {
  "default": string
  "hover": string
  "visited": string
}

export type ThemePalette = {
  "text": ThemeTextPalette
  "background": ThemeBackgroundPalette
  "border": ThemeBorderPalette
  "link": ThemeLinkPalette
  "accent": (string)[]
}

export type ThemeTextPalette = {
  "primary": string
  "secondary": string
  "invert": string
}

export type UpdateAgentSessionPreferencesRequest = {
  "focus_mode": "follow_route" | "pinned_project" | "workspace"
  "pinned_project_id"?: (number) | (null)
  "work_scope_mode": "workspace" | "selected_projects"
  "allowed_project_ids"?: (number)[]
}

export type UserCreateRequest = {
  "username": string
  "password": string
  "display_name": string
  "role"?: UserRole
  "status"?: RecordStatus
}

export type UserItem = {
  "id": number
  "username": string
  "display_name": string
  "role": UserRole
  "status": RecordStatus
  "last_login_at": (string) | (null)
  "created_at": string
  "updated_at": string
}

export type UserResetPasswordRequest = {
  "new_password": string
}

export type UserRole = "platform_admin" | "workspace_user"

export type UserUpdateRequest = {
  "display_name"?: (string) | (null)
  "role"?: (UserRole) | (null)
  "status"?: (RecordStatus) | (null)
}

export type ValidationError = {
  "loc": ((string) | (number))[]
  "msg": string
  "type": string
  "input"?: unknown
  "ctx"?: Record<string, unknown>
}

export type WorkspaceComponentComponentReferenceItem = {
  "component_id": number
  "component_code": string
  "component_name": string
  "current_version_no": number
  "component_version_id": number
  "referenced_component_version_no": number
  "has_unpublished_changes": boolean
  "draft_referenced_component_version_no"?: (number) | (null)
  "draft_is_current_version": boolean
  "is_current_version": boolean
  "can_upgrade": boolean
}

export type WorkspaceComponentCreateRequest = {
  "workspace_id": number
  "content": string
  "file_type"?: PageFileType
  "name": string
  "import_name": string
  "component_type"?: WorkspaceComponentType
  "summary"?: (string) | (null)
  "preview_schema"?: (string) | (null)
  "status"?: RecordStatus
  "change_note"?: (string) | (null)
}

export type WorkspaceComponentCurrentDependencies = {
  "component_id": number
  "current_version_no": number
  "component_version_id": (number) | (null)
  "dependencies": (WorkspaceComponentDependencyItem)[]
}

export type WorkspaceComponentDependencyItem = {
  "dependency_kind": string
  "component_code"?: (string) | (null)
  "component_version_no"?: (number) | (null)
  "runtime_module_path"?: (string) | (null)
  "runtime_kit_name"?: (string) | (null)
  "runtime_kit_base_name"?: (string) | (null)
  "runtime_kit_version_no"?: (number) | (null)
  "runtime_kit_import_path"?: (string) | (null)
}

export type WorkspaceComponentExportPackageRequest = {
  "workspace_id": number
  "component_ids": (number)[]
  "manual_asset_names"?: (string)[]
}

export type WorkspaceComponentItem = {
  "id": number
  "workspace_id": number
  "workspace_name"?: (string) | (null)
  "code": string
  "content": string
  "draft_hash"?: (string) | (null)
  "preview_schema": (string) | (null)
  "current_version_no": number
  "draft_base_version_no": number
  "has_unpublished_changes": boolean
  "published_at": (string) | (null)
  "file_type": PageFileType
  "name": string
  "import_name": string
  "component_type": WorkspaceComponentType
  "summary": (string) | (null)
  "status": RecordStatus
  "created_at": string
  "updated_at": string
  "created_by": (number) | (null)
  "updated_by": (number) | (null)
  "import_path"?: (string) | (null)
  "import_statement"?: (string) | (null)
}

export type WorkspaceComponentPageReferenceItem = {
  "page_id": number
  "page_code": string
  "page_title": string
  "project_id"?: (number) | (null)
  "project_name"?: (string) | (null)
  "current_version_no": number
  "page_version_id": number
  "referenced_component_version_no": number
  "is_current_version": boolean
  "can_upgrade": boolean
}

export type WorkspaceComponentPublishRequest = {
  "release_name"?: (string) | (null)
  "change_note"?: (string) | (null)
}

export type WorkspaceComponentReferenceUpgradeComponentItem = {
  "component_id": number
  "component_code": string
  "component_name": string
  "current_version_no": number
  "draft_referenced_component_version_no": number
}

export type WorkspaceComponentReferenceUpgradeIssue = {
  "kind": string
  "id": number
  "code": string
  "detail": string
}

export type WorkspaceComponentReferenceUpgradePageItem = {
  "page_id": number
  "page_code": string
  "page_title": string
  "previous_version_no": number
  "current_version_no": number
}

export type WorkspaceComponentReferenceUpgradeRequest = {
  "page_ids"?: (number)[]
  "component_ids"?: (number)[]
}

export type WorkspaceComponentReferenceUpgradeResponse = {
  "updated_pages"?: (WorkspaceComponentReferenceUpgradePageItem)[]
  "updated_components"?: (WorkspaceComponentReferenceUpgradeComponentItem)[]
  "skipped"?: (WorkspaceComponentReferenceUpgradeIssue)[]
  "failures"?: (WorkspaceComponentReferenceUpgradeIssue)[]
}

export type WorkspaceComponentReferences = {
  "component_id": number
  "component_code": string
  "current_version_no": number
  "page_references": (WorkspaceComponentPageReferenceItem)[]
  "component_references": (WorkspaceComponentComponentReferenceItem)[]
}

export type WorkspaceComponentRestoreDraftRequest = {
  "change_note"?: (string) | (null)
}

export type WorkspaceComponentSourcePreviewRequest = {
  "workspace_id": number
  "component_id"?: (number) | (null)
  "component_name"?: (string) | (null)
  "content": string
  "preview_schema"?: (string) | (null)
  "preview_options"?: (ComponentPreviewOptions) | (null)
  "file_type"?: PageFileType
}

export type WorkspaceComponentType = "页面组件" | "内容组件" | "原子组件"

export type WorkspaceComponentUpdateRequest = {
  "workspace_id"?: (number) | (null)
  "content"?: (string) | (null)
  "file_type"?: (PageFileType) | (null)
  "name"?: (string) | (null)
  "import_name"?: (string) | (null)
  "component_type"?: (WorkspaceComponentType) | (null)
  "summary"?: (string) | (null)
  "preview_schema"?: (string) | (null)
  "status"?: (RecordStatus) | (null)
  "change_note"?: (string) | (null)
}

export type WorkspaceComponentVersionContent = {
  "component_id": number
  "version_no": number
  "version_label": string
  "release_name": (string) | (null)
  "file_type": PageFileType
  "is_current": boolean
  "content": string
  "preview_schema": (string) | (null)
  "change_note": (string) | (null)
  "created_at": string
  "created_by": (number) | (null)
}

export type WorkspaceComponentVersionListItem = {
  "id": number
  "component_id": number
  "version_no": number
  "version_label": string
  "release_name": (string) | (null)
  "file_type": PageFileType
  "is_current": boolean
  "content_size": number
  "change_note": (string) | (null)
  "created_at": string
  "created_by": (number) | (null)
}

export type WorkspaceCreateRequest = {
  "name": string
  "description"?: (string) | (null)
  "status"?: RecordStatus
  "default_theme_key"?: (string) | (null)
}

export type WorkspaceFontConfigCreateRequest = {
  "asset_id": number
  "family_name": string
  "font_format"?: (string) | (null)
  "font_weight"?: string
  "font_style"?: string
  "font_display"?: string
  "status"?: RecordStatus
}

export type WorkspaceFontConfigResponse = {
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
  "asset_url"?: (string) | (null)
  "created_at": string
  "updated_at": string
}

export type WorkspaceFontConfigUpdateRequest = {
  "family_name"?: (string) | (null)
  "font_format"?: (string) | (null)
  "font_weight"?: (string) | (null)
  "font_style"?: (string) | (null)
  "font_display"?: (string) | (null)
  "status"?: (RecordStatus) | (null)
}

export type WorkspaceFontFamilyResponse = {
  "id": number
  "workspace_id": number
  "name": string
  "faces"?: (WorkspaceFontConfigResponse)[]
  "created_at": string
  "updated_at": string
}

export type WorkspaceFontFamilyUpdateRequest = {
  "name": string
}

export type WorkspaceItem = {
  "id": number
  "code": string
  "name": string
  "description": (string) | (null)
  "status": RecordStatus
  "last_opened_at": (string) | (null)
  "default_theme_key": (string) | (null)
  "created_at": string
  "updated_at": string
  "created_by": (number) | (null)
  "updated_by": (number) | (null)
}

export type WorkspaceStyleCopyRequest = {
  "key"?: (string) | (null)
  "name"?: (string) | (null)
}

export type WorkspaceStyleCreateRequest = {
  "key": string
  "name": string
  "description"?: (string) | (null)
  "configuration"?: StyleConfiguration
}

export type WorkspaceStyleExportAssetSummary = {
  "name": string
  "original_name": string
  "asset_type": string
  "file_hash": string
  "source"?: string
}

export type WorkspaceStyleExportPackageRequest = {
  "style_ids": (number)[]
  "manual_asset_names"?: (string)[]
}

export type WorkspaceStyleExportValidationResult = {
  "can_export"?: boolean
  "automatic_assets"?: (WorkspaceStyleExportAssetSummary)[]
  "manual_assets"?: (WorkspaceStyleExportAssetSummary)[]
  "fonts"?: (WorkspaceStylePackageFontSummary)[]
  "warnings"?: (string)[]
  "missing_static_asset_names"?: (string)[]
  "missing_manual_asset_names"?: (string)[]
  "dynamic_resource_components"?: (string)[]
}

export type WorkspaceStyleImportResult = {
  "styles"?: (WorkspaceStylePackageStyleSummary)[]
  "themes"?: (WorkspaceStylePackageThemeSummary)[]
  "assets"?: (WorkspaceStylePackageAssetSummary)[]
  "fonts"?: (WorkspaceStylePackageFontSummary)[]
  "components"?: (WorkspaceStylePackageComponentSummary)[]
  "warnings"?: (string)[]
}

export type WorkspaceStyleImportValidationResult = {
  "valid": boolean
  "schema_version"?: (number) | (null)
  "styles"?: (WorkspaceStylePackageStyleSummary)[]
  "themes"?: (WorkspaceStylePackageThemeSummary)[]
  "assets"?: (WorkspaceStylePackageAssetSummary)[]
  "fonts"?: (WorkspaceStylePackageFontSummary)[]
  "components"?: (WorkspaceStylePackageComponentSummary)[]
  "errors"?: (string)[]
  "warnings"?: (string)[]
}

export type WorkspaceStyleItem = {
  "id": number
  "workspace_id": number
  "key": string
  "name": string
  "description": (string) | (null)
  "page_width": number
  "page_height": number
  "base_font_size": string
  "icon_default_stroke_width": number
  "show_pdf_export_button": boolean
  "menu_mode": "text" | "preview" | "bottom-preview"
  "theme_key": (string) | (null)
  "style_spec_markdown": string
  "created_at": string
  "updated_at": string
  "created_by": (number) | (null)
  "updated_by": (number) | (null)
}

export type WorkspaceStylePackageAssetSummary = {
  "name": string
  "original_name": string
  "asset_type": string
  "file_hash": string
  "action"?: string
}

export type WorkspaceStylePackageComponentSummary = {
  "source_component_code": string
  "source_version_no": number
  "name": string
  "import_name": string
  "component_type": string
  "dependencies"?: (string)[]
  "component_fingerprint"?: (string) | (null)
  "matched_component_id"?: (number) | (null)
  "matched_component_code"?: (string) | (null)
  "action"?: string
  "match_reason"?: (string) | (null)
}

export type WorkspaceStylePackageFontSummary = {
  "asset_name": string
  "font_family": string
  "font_format": string
  "font_weight": string
  "font_style": string
  "font_display": string
  "status": string
  "action"?: string
}

export type WorkspaceStylePackageStyleSummary = {
  "key": string
  "name": string
  "theme_key"?: (string) | (null)
  "page_width": number
  "page_height": number
  "base_font_size": string
  "icon_default_stroke_width": number
  "show_pdf_export_button": boolean
  "menu_mode": "text" | "preview" | "bottom-preview"
  "style_spec_markdown"?: string
  "action"?: string
}

export type WorkspaceStylePackageThemeSummary = {
  "key": string
  "name": string
  "action"?: string
}

export type WorkspaceStyleUpdateRequest = {
  "name"?: (string) | (null)
  "description"?: (string) | (null)
  "configuration"?: (StyleConfigurationPatch) | (null)
}

export type WorkspaceThemeAssetSummary = {
  "id": number
  "name": string
  "original_name": string
  "asset_type": string
  "analysis_metadata"?: (AssetAnalysisMetadata) | (null)
  "url"?: (string) | (null)
}

export type WorkspaceThemeCopyRequest = {
  "key"?: (string) | (null)
  "name"?: (string) | (null)
}

export type WorkspaceThemeCreateRequest = {
  "key": string
  "name": string
  "description"?: (string) | (null)
  "logo_asset_id"?: (number) | (null)
  "invert_logo_asset_id"?: (number) | (null)
  "project_icon_asset_id"?: (number) | (null)
  "heading_font_family_id"?: (number) | (null)
  "body_font_family_id"?: (number) | (null)
  "code_font_family_id"?: (number) | (null)
  "heading_font_preset"?: (string) | (null)
  "body_font_preset"?: (string) | (null)
  "code_font_preset"?: (string) | (null)
  "palette": ThemePalette
}

export type WorkspaceThemeFontFamilySummary = {
  "id": number
  "name": string
}

export type WorkspaceThemeItem = {
  "id": number
  "workspace_id": number
  "key": string
  "name": string
  "description": (string) | (null)
  "logo_asset_id": (number) | (null)
  "invert_logo_asset_id": (number) | (null)
  "project_icon_asset_id": (number) | (null)
  "project_icon_name": (string) | (null)
  "heading_font_family_id": (number) | (null)
  "body_font_family_id": (number) | (null)
  "code_font_family_id": (number) | (null)
  "heading_font_label"?: (string) | (null)
  "body_font_label"?: (string) | (null)
  "code_font_label"?: (string) | (null)
  "heading_font_preset"?: (string) | (null)
  "body_font_preset"?: (string) | (null)
  "code_font_preset"?: (string) | (null)
  "palette": ThemePalette
  "logo_asset"?: (WorkspaceThemeAssetSummary) | (null)
  "invert_logo_asset"?: (WorkspaceThemeAssetSummary) | (null)
  "project_icon_asset"?: (WorkspaceThemeAssetSummary) | (null)
  "heading_font_family"?: (WorkspaceThemeFontFamilySummary) | (null)
  "body_font_family"?: (WorkspaceThemeFontFamilySummary) | (null)
  "code_font_family"?: (WorkspaceThemeFontFamilySummary) | (null)
  "resolved_theme_config_yaml": string
  "created_at": string
  "updated_at": string
  "created_by": (number) | (null)
  "updated_by": (number) | (null)
}

export type WorkspaceThemeUpdateRequest = {
  "key"?: (string) | (null)
  "name"?: (string) | (null)
  "description"?: (string) | (null)
  "logo_asset_id"?: (number) | (null)
  "invert_logo_asset_id"?: (number) | (null)
  "project_icon_asset_id"?: (number) | (null)
  "heading_font_family_id"?: (number) | (null)
  "body_font_family_id"?: (number) | (null)
  "code_font_family_id"?: (number) | (null)
  "heading_font_preset"?: (string) | (null)
  "body_font_preset"?: (string) | (null)
  "code_font_preset"?: (string) | (null)
  "palette"?: (ThemePalette) | (null)
}

export type WorkspaceUpdateRequest = {
  "name"?: (string) | (null)
  "description"?: (string) | (null)
  "status"?: (RecordStatus) | (null)
  "default_theme_key"?: (string) | (null)
}
