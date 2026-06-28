/**
 * 文件功能：定义前端共享的接口类型与分页结构，供页面、状态和请求层统一复用。
 */
export type RecordStatus = 'active' | 'archived'
export type UserRole = 'platform_admin' | 'workspace_user'
export type AiLlmConfigScope = 'global' | 'personal'
export type PageFileType = 'vue' | 'ts' | 'js' | 'json' | 'md' | 'txt' | 'yaml'
export type PageVersionStorageType = 'snapshot' | 'diff'
export type AssetType = 'icon' | 'font' | 'image' | 'video' | 'drawio' | 'mermaid' | 'chart' | 'formula'
export type AssetRole = 'foundation' | 'content'
export type ProjectMenuMode = 'text' | 'preview' | 'bottom-preview'
export type WorkspaceComponentType = '页面组件' | '内容组件' | '原子组件'

export interface PreviewSizePreset {
  name: string
  width: number
  height: number
  base_font_size?: string
  icon_default_stroke_width?: number
}

export interface AuthUser {
  id: number
  username: string
  display_name: string
  role: UserRole
  status: RecordStatus
  last_login_at: string | null
  preview_size_presets: PreviewSizePreset[]
}

export interface PagedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface ProjectBuildExtraAssetsJson {
  asset_names: string[]
}

export interface ProjectSuggestedReferenceAssetItem {
  id: number
  name: string
  original_name: string
  description: string | null
  asset_type: AssetType
  content_editable: boolean
  approx_aspect_ratio?: string | null
  approx_aspect_ratio_value?: number | null
  aspect_ratio_source?: 'auto' | 'manual' | 'agent' | string | null
}

export interface ProjectSuggestedReferenceAssetsResponse {
  items: ProjectSuggestedReferenceAssetItem[]
}

export interface SuggestedComponentItem {
  id: number
  code: string
  name: string
  import_name: string
  component_type: WorkspaceComponentType
  summary: string | null
  current_version_no: number
  available?: boolean
  unavailable_reason?: string | null
}

export interface SuggestedComponentsResponse {
  items: SuggestedComponentItem[]
}

export interface WorkspaceItem {
  id: number
  code: string
  name: string
  description: string | null
  status: RecordStatus
  last_opened_at: string | null
  default_theme_key: string | null
  created_at: string
  updated_at: string
  created_by: number | null
  updated_by: number | null
}

export interface ProjectItem {
  id: number
  workspace_id: number
  workspace_name: string
  code: string
  name: string
  description: string | null
  is_system_managed: boolean
  status: RecordStatus
  archived_at: string | null
  page_width: number
  page_height: number
  base_font_size: string
  icon_default_stroke_width: number
  show_pdf_export_button: boolean
  menu_mode: ProjectMenuMode
  theme_key: string | null
  theme_config_yaml: string
  style_spec_markdown: string
  build_extra_assets_json?: ProjectBuildExtraAssetsJson
  created_at: string
  updated_at: string
  created_by: number | null
  updated_by: number | null
}

export type ProjectBuildStatus = 'pending' | 'running' | 'succeeded' | 'failed'

export interface WorkspaceStyleItem {
  id: number
  workspace_id: number
  key: string
  name: string
  description: string | null
  page_width: number
  page_height: number
  base_font_size: string
  icon_default_stroke_width: number
  show_pdf_export_button: boolean
  menu_mode: ProjectMenuMode
  theme_key: string | null
  style_spec_markdown: string
  created_at: string
  updated_at: string
  created_by: number | null
  updated_by: number | null
}

export interface WorkspaceStylePackageStyleSummary {
  key: string
  name: string
  theme_key: string | null
  page_width: number
  page_height: number
  base_font_size: string
  icon_default_stroke_width: number
  show_pdf_export_button: boolean
  menu_mode: ProjectMenuMode
  style_spec_markdown: string
  action: 'create' | 'overwrite' | string
}

export interface WorkspaceStylePackageThemeSummary {
  key: string
  name: string
  action: 'create' | 'reuse' | string
}

export interface WorkspaceStylePackageAssetSummary {
  name: string
  original_name: string
  asset_type: string
  file_hash: string
  action: 'create' | 'reuse' | string
}

export interface WorkspaceStylePackageFontSummary {
  asset_name: string
  font_family: string
  font_format: string
  font_weight: string
  font_style: string
  font_display: string
  status: RecordStatus | string
  action: 'create' | 'reuse' | string
}

export interface WorkspaceStylePackageComponentSummary {
  source_component_code: string
  source_version_no: number
  name: string
  import_name: string
  component_type: WorkspaceComponentType | string
  dependencies: string[]
  component_fingerprint: string | null
  matched_component_id: number | null
  matched_component_code: string | null
  action: 'create' | 'reuse' | string
  match_reason: string | null
}

export interface WorkspaceStyleExportAssetSummary {
  name: string
  original_name: string
  asset_type: string
  file_hash: string
  source: 'automatic' | 'manual' | string
}

export interface WorkspaceStyleExportValidationResult {
  can_export: boolean
  automatic_assets: WorkspaceStyleExportAssetSummary[]
  manual_assets: WorkspaceStyleExportAssetSummary[]
  fonts: WorkspaceStylePackageFontSummary[]
  warnings: string[]
  missing_static_asset_names: string[]
  missing_manual_asset_names: string[]
  dynamic_resource_components: string[]
}

export interface WorkspaceStyleImportValidationResult {
  valid: boolean
  schema_version: number | null
  styles: WorkspaceStylePackageStyleSummary[]
  themes: WorkspaceStylePackageThemeSummary[]
  assets: WorkspaceStylePackageAssetSummary[]
  fonts: WorkspaceStylePackageFontSummary[]
  components: WorkspaceStylePackageComponentSummary[]
  errors: string[]
  warnings: string[]
}

export interface WorkspaceStyleImportResult {
  styles: WorkspaceStylePackageStyleSummary[]
  themes: WorkspaceStylePackageThemeSummary[]
  assets: WorkspaceStylePackageAssetSummary[]
  fonts: WorkspaceStylePackageFontSummary[]
  components: WorkspaceStylePackageComponentSummary[]
  warnings: string[]
}

export interface ProjectBuildCreateRequest {
  base_url: string
}

export interface ProjectBuildAssetSummary {
  automatic_asset_names: string[]
  extra_asset_names: string[]
  included_asset_names: string[]
  dynamic_module_paths: string[]
}

export interface ProjectBuildResourceIssueData {
  dynamic_module_paths?: string[]
  candidate_asset_names?: string[]
  current_extra_asset_names?: string[]
  missing_asset_names?: string[]
  required_asset_names?: string[]
}

export interface ProjectBuildJob {
  id: number
  project_id: number
  snapshot_release_id: number
  base_url: string
  status: ProjectBuildStatus
  error_message: string | null
  artifact_storage_key: string | null
  artifact_download_url: string | null
  artifact_proxy_url: string | null
  artifact_entry_file: string | null
  artifact_sha256: string | null
  artifact_size_bytes: number | null
  created_by: number | null
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
}

export interface ProjectRouteBinding {
  route_id: number
  parent_route: string | null
  route: string
  full_path: string
  parent_order?: number | null
  order?: number
}

export interface PageItem {
  id: number
  code: string
  page_content: string
  current_version_no: number
  file_type: PageFileType
  title: string
  summary: string | null
  speaker_notes?: string | null
  status: RecordStatus
  workspace_id: number | null
  workspace_name: string | null
  project_id: number | null
  project_name: string | null
  created_at: string
  updated_at: string
  created_by: number | null
  updated_by: number | null
  screenshot_url: string | null
  screenshot_version_no: number | null
  screenshot_config_hash: string | null
  screenshot_is_latest: boolean
  screenshot_updated_at: string | null
  is_in_project_route: boolean | null
  route_bindings: ProjectRouteBinding[]
}

export type PageCopyRoutePlacement = 'none' | 'root' | 'group'

export interface PageCopyToProjectPayload {
  target_project_id: number
  title?: string | null
  summary?: string | null
  route_placement?: PageCopyRoutePlacement
  parent_route_id?: number | null
  route?: string | null
}

export interface PageScreenshotBatchRefreshFailure {
  page_id: number
  code: string
  detail: string
}

export interface PageScreenshotBatchRefreshResponse {
  requested_count: number
  succeeded_count: number
  failed_count: number
  page_ids: number[]
  failures: PageScreenshotBatchRefreshFailure[]
}

export type PageScreenshotJobStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped'
export type PageScreenshotJobGroupStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'partial'

export interface PageScreenshotJob {
  id: number
  job_group_id: string | null
  source: string
  page_id: number
  workspace_id: number | null
  project_id: number | null
  viewport_width: number
  viewport_height: number
  config_hash: string
  status: PageScreenshotJobStatus
  attempt_count: number
  error_code: string | null
  error_message: string | null
  created_by: number | null
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
}

export interface PageScreenshotJobGroup {
  job_group_id: string
  status: PageScreenshotJobGroupStatus
  requested_count: number
  pending_count: number
  running_count: number
  succeeded_count: number
  failed_count: number
  skipped_count: number
  page_ids: number[]
  jobs: PageScreenshotJob[]
  failures: PageScreenshotBatchRefreshFailure[]
}

export type ProjectRouteNodeType = 'group' | 'page'

export interface ProjectRouteChildItem {
  id: number
  route_type: 'page'
  route: string
  order: number
  hidden: boolean
  page_id: number
  page_code: string
  page_title: string
  display_title: string
}

export interface ProjectRouteTreeItem {
  id: number
  route_type: ProjectRouteNodeType
  route: string
  order: number
  hidden: boolean
  group_title: string | null
  page_id: number | null
  page_code: string | null
  page_title: string | null
  display_title: string
  children: ProjectRouteChildItem[]
}

export interface ProjectRouteTreeResponse {
  routes: ProjectRouteTreeItem[]
}

export interface ProjectRouteChildWrite {
  route: string
  order: number
  hidden: boolean
  page_id: number
}

export interface ProjectRouteItemWrite {
  route_type: ProjectRouteNodeType
  route: string
  order: number
  hidden: boolean
  group_title?: string | null
  page_id?: number | null
  children?: ProjectRouteChildWrite[]
}

export interface PageVersionListItem {
  id: number
  page_id: number
  version_no: number
  version_label: string
  file_type: PageFileType
  storage_type: PageVersionStorageType
  is_important: boolean
  is_current: boolean
  snapshot_name: string | null
  change_note: string | null
  content_size: number
  created_at: string
  created_by: number | null
}

export interface PageVersionContent {
  page_id: number
  version_no: number
  version_label: string
  file_type: PageFileType
  storage_type: PageVersionStorageType
  is_important: boolean
  snapshot_name: string | null
  change_note: string | null
  speaker_notes?: string | null
  content_mode: 'full' | 'diff'
  content: string
  resolved_content: string
  created_at: string
  created_by: number | null
}

export interface PageComponentResourceItem {
  component_name: string
  resource_attr: string
  resource_name: string
}

export interface PageCurrentComponentIndex {
  page_id: number
  current_version_no: number
  page_version_id: number | null
  components: string[]
  resources: PageComponentResourceItem[]
}

export interface WorkspaceComponentDependencyItem {
  dependency_kind: string
  component_code: string | null
  component_version_no: number | null
  runtime_module_path: string | null
  runtime_kit_name?: string | null
  runtime_kit_base_name?: string | null
  runtime_kit_version_no?: number | null
  runtime_kit_import_path?: string | null
}

export interface WorkspaceComponentCurrentDependencies {
  component_id: number
  current_version_no: number
  component_version_id: number | null
  dependencies: WorkspaceComponentDependencyItem[]
}

export interface WorkspaceComponentPageReferenceItem {
  page_id: number
  page_code: string
  page_title: string
  project_id: number | null
  project_name: string | null
  current_version_no: number
  page_version_id: number
  referenced_component_version_no: number
  is_current_version: boolean
  can_upgrade: boolean
}

export interface WorkspaceComponentComponentReferenceItem {
  component_id: number
  component_code: string
  component_name: string
  current_version_no: number
  component_version_id: number
  referenced_component_version_no: number
  has_unpublished_changes: boolean
  draft_referenced_component_version_no: number | null
  draft_is_current_version: boolean
  is_current_version: boolean
  can_upgrade: boolean
}

export interface WorkspaceComponentReferences {
  component_id: number
  component_code: string
  current_version_no: number
  page_references: WorkspaceComponentPageReferenceItem[]
  component_references: WorkspaceComponentComponentReferenceItem[]
}

export interface WorkspaceComponentReferenceUpgradePayload {
  page_ids: number[]
  component_ids: number[]
}

export interface WorkspaceComponentReferenceUpgradeItem {
  kind: string
  id: number
  code: string
  detail: string
}

export interface WorkspaceComponentReferenceUpgradePageItem {
  page_id: number
  page_code: string
  page_title: string
  previous_version_no: number
  current_version_no: number
}

export interface WorkspaceComponentReferenceUpgradeComponentItem {
  component_id: number
  component_code: string
  component_name: string
  current_version_no: number
  draft_referenced_component_version_no: number
}

export interface WorkspaceComponentReferenceUpgradeResponse {
  updated_pages: WorkspaceComponentReferenceUpgradePageItem[]
  updated_components: WorkspaceComponentReferenceUpgradeComponentItem[]
  skipped: WorkspaceComponentReferenceUpgradeItem[]
  failures: WorkspaceComponentReferenceUpgradeItem[]
}

export interface WorkspaceComponentItem {
  id: number
  workspace_id: number
  workspace_name: string | null
  code: string
  content: string
  preview_schema: string | null
  current_version_no: number
  draft_base_version_no: number
  has_unpublished_changes: boolean
  published_at: string | null
  file_type: PageFileType
  name: string
  import_name: string
  component_type: WorkspaceComponentType
  summary: string | null
  status: RecordStatus
  created_at: string
  updated_at: string
  created_by: number | null
  updated_by: number | null
}

export interface WorkspaceComponentVersionListItem {
  id: number
  component_id: number
  version_no: number
  version_label: string
  release_name: string | null
  file_type: PageFileType
  is_current: boolean
  content_size: number
  change_note: string | null
  created_at: string
  created_by: number | null
}

export interface WorkspaceComponentVersionContent {
  component_id: number
  version_no: number
  version_label: string
  release_name: string | null
  file_type: PageFileType
  is_current: boolean
  content: string
  preview_schema: string | null
  change_note: string | null
  created_at: string
  created_by: number | null
}

export interface ComponentSharePackageComponentSummary {
  source_component_code: string
  source_version_no: number
  name: string
  import_name: string
  component_type: string
  dependencies: string[]
  component_fingerprint: string | null
  matched_component_id: number | null
  matched_component_code: string | null
  action: 'create' | 'reuse' | string
  match_reason: string | null
}

export interface ComponentSharePackageAssetSummary {
  name: string
  original_name: string
  asset_type: string
  file_hash: string
  action: 'create' | 'reuse' | string
}

export interface ComponentSharePackageFontSummary {
  asset_name: string
  font_family: string
  font_format: string
  font_weight: string
  font_style: string
  font_display: string
  status: RecordStatus | string
  action: 'create' | 'reuse' | string
}

export interface ComponentShareExportComponentSummary {
  source_component_code: string
  source_version_no: number
  name: string
  import_name: string
  has_dynamic_resources: boolean
  missing_static_asset_names: string[]
}

export interface ComponentShareExportAssetSummary {
  name: string
  original_name: string
  asset_type: string
  file_hash: string
  source: 'automatic' | 'manual' | string
}

export interface ComponentShareExportValidationResult {
  can_export: boolean
  components: ComponentShareExportComponentSummary[]
  automatic_assets: ComponentShareExportAssetSummary[]
  manual_assets: ComponentShareExportAssetSummary[]
  fonts: ComponentSharePackageFontSummary[]
  warnings: string[]
  missing_static_asset_names: string[]
  missing_manual_asset_names: string[]
  dynamic_resource_components: string[]
}

export interface ComponentShareImportValidationResult {
  valid: boolean
  schema_version: number | null
  runtime_kit_manifest_version: string | null
  components: ComponentSharePackageComponentSummary[]
  assets: ComponentSharePackageAssetSummary[]
  fonts: ComponentSharePackageFontSummary[]
  errors: string[]
  warnings: string[]
}

export interface ComponentShareImportResult {
  imported_components: WorkspaceComponentItem[]
  components: ComponentSharePackageComponentSummary[]
  assets: ComponentSharePackageAssetSummary[]
  fonts: ComponentSharePackageFontSummary[]
  warnings: string[]
}

export type PreviewKind = 'project' | 'page' | 'component' | 'asset'
export type PreviewEntryType = 'route' | 'module' | 'component_host' | 'asset_host'
export type ComponentPreviewMode = 'saved' | 'draft'
export type ComponentPreviewSource = 'workspace_component' | 'runtime_kit'
export type RuntimeKitCapabilityKind = 'component' | 'composable' | 'util' | 'type'
export type RuntimeKitCapabilityAudience = 'backend' | 'agent'

export interface PreviewEntryDescriptor {
  entry_type: PreviewEntryType
  route?: string
  module_path?: string
}

export interface PreviewArtifactResponse {
  preview_url: string
  artifact_id: string
  preview_kind: PreviewKind
  entry_descriptor: PreviewEntryDescriptor
  viewport_width: number
  viewport_height: number
  project_id?: number | null
  workspace_id?: number | null
  component_preview_mode?: ComponentPreviewMode | null
  component_source?: ComponentPreviewSource | null
  component_code?: string | null
  component_version_no?: number | null
  runtime_kit_component_name?: string | null
  runtime_kit_manifest_version?: string | null
  asset_id?: number | null
  asset_name?: string | null
}

export interface RuntimeKitComponentCapabilityItem {
  kind: RuntimeKitCapabilityKind
  base_name: string
  version_no: number
  name: string
  import_path: string
  category: string
  description: string
  display_name: string
  summary: string
  tags: string[]
  previewable: boolean
  preview_schema: import('@/types/component-preview').ComponentPreviewSchema | null
  preview_options: ComponentPreviewOptions | null
  usage: string[]
  returns: string | null
  return_example: string[]
  constraints: string[]
  audiences: RuntimeKitCapabilityAudience[]
  manifest_version: string
}

export interface RuntimeKitComponentCapabilityListResponse {
  items: RuntimeKitComponentCapabilityItem[]
  total: number
  manifest_version?: string | null
}

export interface AgentScopeContext {
  scope_type: 'workspace' | 'project' | 'page' | 'component'
  workspace_id: number
  project_id?: number | null
  page_id?: number | null
  component_id?: number | null
  workspace_name?: string | null
  project_name?: string | null
  page_title?: string | null
  component_name?: string | null
  source: string
}

export interface AgentDescriptor {
  id: string
  name: string
  icon: string
  summary: string
  default_session_name: string
  capabilities: string[]
  scope_type: 'workspace' | 'project' | 'page' | 'component'
  entry_kind: 'agent' | 'team'
  available: boolean
  unavailable_reason: string | null
  llm_slot: string | null
  llm_binding_ready: boolean
  bound_llm_name: string | null
  bound_provider_label: string | null
  supports_image_input: boolean
  prompt_customized: boolean
  enabled_tool_count: number
  disabled_tool_count: number
  scope: AgentScopeContext
}

export interface AgentSessionLlmMetadata {
  selection_kind: 'explicit_config' | 'slot_binding'
  config_id: number
  scope: AiLlmConfigScope
  name: string
  provider_config_id?: number | null
  provider_config_name?: string | null
  provider_key: string
  provider_label: string
  model_id: string
  supports_image_input: boolean
}

export interface AgentToolConfigItem {
  key: string
  label: string
  group_key: string
  group_label: string
  default_description: string
  description: string
  description_override: string | null
  default_instructions: string | null
  instructions: string | null
  instructions_override: string | null
  enabled: boolean
  configurable: boolean
  requires_confirmation: boolean
  risk_level: 'system' | 'read' | 'write' | 'danger'
  agent_guide: AgentToolGuideItem
}

export interface AgentToolGuideItem {
  tool_name: string
  effective_description: string
  system_description: string
  instructions: string | null
  parameters_schema: Record<string, unknown> | null
  call_example: Record<string, unknown> | null
  response_example: unknown | null
  response_notes: string | null
  required_context_fields: string[]
  runtime_disclosure_groups: string[]
  requires_confirmation: boolean
  risk_level: 'system' | 'read' | 'write' | 'danger'
}

export interface AgentToolGroupConfigItem {
  key: string
  label: string
  description: string
  tools: AgentToolConfigItem[]
}

export interface AgentCatalogItem {
  id: string
  name: string
  icon: string
  summary: string
  default_session_name: string
  capabilities: string[]
  scope_type: 'workspace' | 'project' | 'page' | 'component'
  entry_kind: 'agent' | 'team'
  llm_slot: string
  default_description: string
  description: string
  description_override: string | null
  description_customized: boolean
  role: string
  system_prompt: string
  default_prompt: string
  tool_groups: AgentToolGroupConfigItem[]
}

export interface AgentConfigItem extends AgentCatalogItem {
  prompt_override: string | null
  effective_prompt: string
  prompt_customized: boolean
  enabled_tool_count: number
  disabled_tool_count: number
}

export interface AgentSessionItem {
  session_id: string
  agent_id: string
  session_name: string | null
  created_at: string | null
  updated_at: string | null
  metadata: Record<string, unknown> & { llm?: AgentSessionLlmMetadata }
}

export interface AgentMessageItem {
  id: string
  run_id?: string | null
  role: 'user' | 'assistant' | 'tool'
  content: string
  reasoning_content?: string | null
  created_at: string | null
  tool_name: string | null
  tool_call_id: string | null
  tool_args: unknown | null
  tool_call_error: boolean | null
  tool_calls?: AgentMessageToolCallItem[]
  attachments?: AgentMessageAttachmentItem[]
}

export interface AgentMessageToolCallItem {
  id?: string | null
  type?: string | null
  name?: string | null
  arguments?: unknown
  tool_name?: string | null
  tool_args?: unknown
  tool_call_id?: string | null
  function?: {
    name?: string | null
    arguments?: unknown
  } | null
  [key: string]: unknown
}

export interface AgentImageAttachmentItem {
  id: number
  session_id: string
  source_kind: 'user_upload' | 'tool_output'
  original_name: string
  content_type: string
  file_size: number
  sha256: string
  url: string
  preview_available: boolean
  promoted_asset_id: number | null
  status: RecordStatus
  created_at: string | null
}

export interface AgentMessageAttachmentItem {
  id: number
  source_kind: 'user_upload' | 'tool_output'
  original_name: string
  content_type: string
  file_size: number
  url: string
  preview_available: boolean
  promoted_asset_id: number | null
}

export interface AgentContextStatusItem {
  session_id: string
  agent_id: string
  compression_enabled: boolean
  compression_required: boolean
  compression_status: 'idle' | 'compressing' | 'compressed' | 'failed'
  compression_method: 'none' | 'model' | 'deterministic_fallback'
  compression_error_message: string | null
  summary_available: boolean
  summary: string | null
  topics: string[]
  summary_updated_at: string | null
  context_window_tokens: number
  max_output_tokens: number
  history_token_ratio: number
  compression_target_ratio: number
  safety_margin_tokens: number
  current_input_tokens: number
  fixed_context_tokens: number
  history_budget_tokens: number
  compression_target_tokens: number
  estimated_history_tokens: number
  retained_recent_history_tokens: number
  retained_recent_message_count: number
  context_input_budget_tokens: number
  context_used_tokens: number
  context_remaining_tokens: number
  last_input_tokens: number
  last_output_tokens: number
  last_total_tokens: number
  last_reasoning_tokens: number
}

export interface AgentSuggestedPatch {
  tool_name: string
  target_page_id: number
  change_note: string | null
  proposed_content: string
  unified_diff: string
}

export interface AgentUserFeedbackOption {
  label: string
  description: string | null
  selected?: boolean
}

export interface AgentUserFeedbackQuestion {
  question: string
  header: string | null
  options: AgentUserFeedbackOption[]
  multi_select: boolean
  selected_options: string[] | null
}

export interface AgentFeedbackSelection {
  question: string
  selected_label?: string | null
  custom_text?: string | null
}

export interface AgentPendingRequirement {
  id: string | null
  kind: 'confirmation' | 'user_feedback'
  run_id: string
  session_id: string
  member_agent_id?: string | null
  member_agent_name?: string | null
  member_run_id?: string | null
  tool_name: string | null
  tool_execution: Record<string, unknown>
  suggested_patch: AgentSuggestedPatch | null
  user_feedback_schema: AgentUserFeedbackQuestion[]
  note: string | null
}

export interface AgentRunEvent {
  event: string
  run_id?: string | null
  session_id?: string | null
  content?: string | null
  data: Record<string, unknown>
  sequence?: number | null
  event_index?: number | null
  [key: string]: unknown
}

export type AgentActiveRunStatus = 'pending' | 'running' | 'paused' | 'cancelling' | 'completed' | 'cancelled' | 'failed'

export interface AgentActiveRunItem {
  run_id: string
  session_id: string
  agent_id: string
  status: AgentActiveRunStatus
  pending_requirement: AgentPendingRequirement | null
  content: string | null
  created_at: string | null
  updated_at?: string | null
  cancel_requested_at?: string | null
  event_index?: number
}

export interface AgentRunStartResponse {
  run_id: string
  session_id: string
  status: 'pending' | 'running'
  event_index: number
}

export interface AgentTimelineToolItem {
  tool_call_id: string | null
  tool_name: string
  member_agent_id?: string | null
  member_agent_name?: string | null
  member_run_id?: string | null
  status: 'running' | 'completed' | 'error'
  input_payload: unknown
  output_payload: unknown
  message: string
}

export interface AgentTimelineItem {
  id: string
  session_id: string
  run_id: string
  kind: 'message' | 'reasoning' | 'tool' | 'run_status' | 'requirement'
  role: 'user' | 'assistant' | null
  event_index: number | null
  order_index: number
  content: string | null
  status: string | null
  tool: AgentTimelineToolItem | null
  attachments?: AgentMessageAttachmentItem[]
  source: 'message' | 'event' | 'synthetic'
  created_at: string | null
}

export interface AgentMemberRunItem {
  parent_run_id: string
  run_id: string
  agent_id: string
  agent_name: string | null
  status: AgentActiveRunStatus
  created_at: string | null
  updated_at: string | null
  delegate_tool_call_id: string | null
  input_prompt?: string | null
  output_prompt?: string | null
  timeline_items: AgentTimelineItem[]
}

export interface AgentSessionRuntimeSnapshot {
  session: AgentSessionItem
  timeline_items: AgentTimelineItem[]
  member_runs: AgentMemberRunItem[]
  context_status: AgentContextStatusItem
  active_run: AgentActiveRunItem | null
  last_run: AgentActiveRunItem | null
  pending_requirement: AgentPendingRequirement | null
  event_index: number
  pending_attachments: AgentImageAttachmentItem[]
}

export interface AgentRunCancelResponse {
  run_id: string
  session_id: string
  cancel_requested: boolean
}

export interface LlmProviderCatalogItem {
  provider_key: string
  label: string
  provider_adapter: string
  docs_url: string
  supports_base_url: boolean
  supports_api_key: boolean
  supports_thinking: boolean
  thinking_mode: string
  default_base_url: string | null
  default_model_id: string | null
  default_thinking_enabled: boolean
  default_thinking_effort: string | null
  default_context_window_tokens: number | null
  default_max_output_tokens: number | null
  default_supports_image_input: boolean
  thinking_effort_options: string[]
  advanced_json_hint: Record<string, unknown>
}

export interface LlmConfigItem {
  id: number
  scope: AiLlmConfigScope
  owner_user_id: number | null
  editable: boolean
  name: string
  provider_config_id: number
  provider_config_name: string
  provider_key: string
  provider_label: string
  model_id: string
  thinking_enabled: boolean
  thinking_effort: string | null
  supports_image_input: boolean
  context_window_tokens: number
  max_output_tokens: number
  history_token_ratio: number
  compression_target_ratio: number
  advanced_config_json: Record<string, unknown>
  status: RecordStatus
  created_at: string | null
  updated_at: string | null
}

export interface LlmProviderConfigItem {
  id: number
  scope: AiLlmConfigScope
  owner_user_id: number | null
  editable: boolean
  name: string
  provider_key: string
  provider_label: string
  base_url: string | null
  status: RecordStatus
  has_api_key: boolean
  api_key_masked: string | null
  created_at: string | null
  updated_at: string | null
}

export interface LlmSlotBindingItem {
  slot: string
  slot_label: string
  llm_config_id: number | null
  llm_config_name: string | null
  provider_config_id: number | null
  provider_config_name: string | null
  provider_key: string | null
  provider_label: string | null
  model_id: string | null
  binding_ready: boolean
  supports_image_input: boolean
  inherited_from_global: boolean
}

export interface UserItem {
  id: number
  username: string
  display_name: string
  role: UserRole
  status: RecordStatus
  last_login_at: string | null
  created_at: string
  updated_at: string
}

export type ComponentPreviewSizeMode = 'auto' | 'percent' | 'fixed'
export type ComponentPreviewAlignment = 'start' | 'center' | 'end'

export interface ComponentPreviewPageOptions {
  width: number
  height: number
  base_font_size: string
  icon_default_stroke_width: number
  theme_key: string | null
  theme_config_yaml: string | null
}

export interface ComponentPreviewPlacementOptions {
  width_mode: ComponentPreviewSizeMode
  width_value: number | null
  height_mode: ComponentPreviewSizeMode
  height_value: number | null
  horizontal_align: ComponentPreviewAlignment
  vertical_align: ComponentPreviewAlignment
  padding: number
}

export interface ComponentPreviewOptions {
  page: ComponentPreviewPageOptions
  placement: ComponentPreviewPlacementOptions
}

export interface WorkspaceFontConfigSummary {
  id: number
  asset_id: number
  asset_name: string
  font_family: string
  font_format: string
  font_weight: string
  font_style: string
  font_display: string
  status: RecordStatus
}

export interface WorkspaceFontConfigItem extends WorkspaceFontConfigSummary {
  workspace_id: number
  asset_url: string | null
  created_at: string
  updated_at: string
}

export interface ThemeTextPalette {
  primary: string
  secondary: string
  invert: string
}

export interface ThemeBackgroundPalette {
  default: string
  invert: string
}

export interface ThemeBorderPalette {
  default: string
  subtle: string
}

export interface ThemeLinkPalette {
  default: string
  hover: string
  visited: string
}

export interface ThemePalette {
  text: ThemeTextPalette
  background: ThemeBackgroundPalette
  border: ThemeBorderPalette
  link: ThemeLinkPalette
  accent: string[]
}

export interface ThemeAssetSummary {
  id: number
  name: string
  original_name: string
  asset_type: string
  analysis_metadata: AssetAnalysisMetadata | null
  url: string | null
}

export interface AssetIconAnalysisPayload {
  format: 'svg' | 'image' | 'unknown'
  render_mode: 'inline_svg' | 'image'
  style: 'stroke' | 'fill' | 'mixed' | 'complex' | 'unknown'
  inline_safe: boolean
  stroke_width_editable: boolean
  analysis_status: 'analyzed' | 'unsupported' | 'error'
  reasons: string[]
}

export interface AssetAnalysisMetadata {
  schema_version: number
  kind: 'icon'
  icon: AssetIconAnalysisPayload
}

export interface AssetRenderHintMetadata {
  schema_version: number
  kind: 'asset_render_hint'
  aspect_ratio: string
  aspect_ratio_value: number
  aspect_ratio_source: 'auto' | 'manual' | 'agent' | string
}

export interface WorkspaceThemeItem {
  id: number
  workspace_id: number
  key: string
  name: string
  description: string | null
  logo_asset_id: number | null
  invert_logo_asset_id: number | null
  project_icon_asset_id: number | null
  project_icon_name: string | null
  heading_font_id: number | null
  body_font_id: number | null
  code_font_id: number | null
  heading_font_label: string | null
  body_font_label: string | null
  code_font_label: string | null
  palette: ThemePalette
  logo_asset: ThemeAssetSummary | null
  invert_logo_asset: ThemeAssetSummary | null
  project_icon_asset: ThemeAssetSummary | null
  heading_font: WorkspaceFontConfigItem | null
  body_font: WorkspaceFontConfigItem | null
  code_font: WorkspaceFontConfigItem | null
  resolved_theme_config_yaml: string
  created_at: string
  updated_at: string
  created_by: number | null
  updated_by: number | null
}

export interface AssetResponse {
  id: number
  workspace_id: number
  name: string
  file_name: string
  original_name: string
  description: string | null
  file_size: number
  file_hash: string
  content_type: string | null
  asset_type: AssetType
  asset_role: AssetRole
  render_type: AssetType
  tags: string[]
  analysis_metadata: AssetAnalysisMetadata | null
  render_metadata: AssetRenderHintMetadata | Record<string, unknown> | null
  approx_aspect_ratio?: string | null
  approx_aspect_ratio_value?: number | null
  aspect_ratio_source?: 'auto' | 'manual' | 'agent' | string | null
  status: RecordStatus
  archived_at: string | null
  archive_reason: string | null
  source_asset_id: number | null
  history_kind: string | null
  content_editable: boolean
  url: string | null
  font_config: WorkspaceFontConfigSummary | null
  rename_block_reason: string | null
  delete_block_reason: string | null
  archive_block_reason: string | null
  archive_warning_reasons: string[]
  created_at: string
  updated_at: string
}

export interface AssetContentResponse {
  asset: AssetResponse
  content: string
}

export interface AssetContentPreviewResponse {
  asset_id: number
  asset_name: string
  changed: boolean
  unified_diff: string
}

export interface AssetReferenceSummary {
  theme_count: number
  font_count: number
  page_count: number
  component_count: number
  component_version_count: number
  references: Array<Record<string, unknown>>
  has_references: boolean
}

export interface AssetBatchOperationFailure {
  asset_id: number
  code: string
  detail: string
}

export interface AssetBatchOperationResponse {
  requested_count: number
  succeeded_count: number
  failed_count: number
  asset_ids: number[]
  failures: AssetBatchOperationFailure[]
}

export interface AssetPackageImportFailure {
  name: string
  code: string
  detail: string
}

export interface AssetPackageImportItem {
  name: string
  original_name: string
  asset_type: AssetType
  file_hash: string
  action: 'create' | 'update_metadata' | 'reuse' | string
  asset_id: number | null
}

export interface AssetPackageImportResult {
  imported_count: number
  updated_count: number
  reused_count: number
  failed_count: number
  assets: AssetPackageImportItem[]
  failures: AssetPackageImportFailure[]
}

export interface ListParams {
  page: number
  page_size: number
  keyword?: string
  status?: RecordStatus | ''
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}
