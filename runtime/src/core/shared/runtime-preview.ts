/**
 * 文件用途：定义无状态预览运行时共享契约、远程模块标识与资源路径解析辅助函数。
 */

export type RuntimeArtifactKind = 'preview_artifact' | 'page_visual_edit_preview' | 'build_snapshot' | 'build_release'
export type PreviewKind = 'project' | 'page' | 'component' | 'asset'
export type PreviewScopeType = 'project' | 'workspace_component' | 'runtime_kit_component' | 'workspace_asset'
export type PreviewEntryType = 'route' | 'module' | 'component_host' | 'asset_host'
export type ComponentPreviewMode = 'saved' | 'draft'
export type RuntimeComponentPreviewSource = 'workspace_component' | 'runtime_kit'

export interface RuntimePreviewEntryDescriptor {
  entry_type: PreviewEntryType
  route?: string
  module_path?: string
}

export interface RuntimePreviewOwnerScope {
  scope_type: PreviewScopeType
  workspace_id: string
  project_id?: string
  component_code?: string
  component_version_no?: number
  preview_mode?: ComponentPreviewMode
  runtime_kit_component_name?: string
  runtime_kit_manifest_version?: string
  asset_id?: string
}

export interface RuntimePreviewContext {
  artifactId: string
  tenantId: string
  previewKind: PreviewKind
  scopeType: PreviewScopeType
  workspaceId: string
  projectId?: string
  entryDescriptor: RuntimePreviewEntryDescriptor
  assetBaseUrl: string
  traceId: string
  componentPreviewMode?: ComponentPreviewMode
  componentSource?: RuntimeComponentPreviewSource
  componentCode?: string
  componentVersionNo?: number
  runtimeKitComponentName?: string
  runtimeKitManifestVersion?: string
  assetId?: string
}

export interface RuntimeReleaseManifestModule {
  path?: string
  hash?: string
}

export interface RuntimePreviewAssetMetadata {
  file_hash: string
  original_name?: string
  asset_role?: 'foundation' | 'content'
  render_type?: 'icon' | 'font' | 'image' | 'drawio' | 'mermaid' | 'chart' | 'formula' | 'video'
  content_type?: string
  approx_aspect_ratio?: string
  approx_aspect_ratio_value?: number
  aspect_ratio_source?: 'auto' | 'manual' | 'agent' | string
}

export interface RuntimePreviewArtifactManifest {
  artifact_id: string
  artifact_kind?: RuntimeArtifactKind
  tenant_id: string
  preview_kind: PreviewKind
  owner_scope: RuntimePreviewOwnerScope
  entry_descriptor: RuntimePreviewEntryDescriptor
  asset_base_url?: string
  project_id?: string
  workspace_id?: string
  modules: Record<string, string | RuntimeReleaseManifestModule>
  assets: Record<string, string>
  asset_metadata?: Record<string, RuntimePreviewAssetMetadata>
  version?: string
  published_at?: string
  visual_edit?: RuntimePageVisualEditArtifactMetadata
}

/**
 * Backend 写入页面可视化编辑专用 artifact 的版本化源码身份与只读 Manifest。
 */
export interface RuntimePageVisualEditArtifactMetadata {
  protocol_version: 1
  page_id: string | number
  page_version_id?: string | number
  base_version_no: number
  source_hash: string
  module_path: string
  manifest?: unknown
  warnings?: unknown[]
}

export interface RuntimeFontBundleItem {
  asset_name: string
  font_family: string
  font_format: string
  font_weight: string
  font_style: string
  font_display: string
}

export interface RuntimeFontBundle {
  items: Record<string, RuntimeFontBundleItem>
}

export interface RuntimeModuleResolverConfig {
  remote_component_prefix?: string
  runtime_kit_alias?: string
  runtime_kit_manifest_version?: string
  runtime_kit_exports?: Array<{
    kind: string
    base_name?: string
    version_no?: number
    name: string
    import_path: string
    category: string
    description?: string
  }>
}

export type ComponentPreviewFieldType = 'string' | 'textarea' | 'number' | 'boolean' | 'select' | 'json'

export interface ComponentPreviewSelectOption {
  label: string
  value: string | number | boolean
}

export interface ComponentPreviewPropField {
  type: ComponentPreviewFieldType
  label?: string
  description?: string
  required?: boolean
  default?: unknown
  placeholder?: string
  options?: ComponentPreviewSelectOption[]
}

export interface ComponentPreviewSlotTextNode {
  type: 'text'
  value: string
}

export interface ComponentPreviewSlotHtmlNode {
  type: 'html'
  value: string
}

export interface ComponentPreviewSlotComponentNode {
  type: 'component'
  component: string
  props?: Record<string, unknown>
  children?: ComponentPreviewSlotNode[]
}

export type ComponentPreviewSlotNode =
  | ComponentPreviewSlotTextNode
  | ComponentPreviewSlotHtmlNode
  | ComponentPreviewSlotComponentNode

export interface ComponentPreviewSlotField {
  label?: string
  description?: string
  default?: ComponentPreviewSlotNode[]
}

export interface ComponentPreviewMockField {
  label?: string
  description?: string
  default?: unknown
}

export interface ComponentPreviewPreset {
  key: string
  label: string
  description?: string
  props?: Record<string, unknown>
  slots?: Record<string, ComponentPreviewSlotNode[]>
  mocks?: Record<string, unknown>
}

export interface ComponentPreviewSchema {
  props?: Record<string, ComponentPreviewPropField>
  slots?: Record<string, ComponentPreviewSlotField>
  mocks?: Record<string, ComponentPreviewMockField>
  presets?: ComponentPreviewPreset[]
}

export type RuntimeComponentPreviewSizeMode = 'auto' | 'percent' | 'fixed'
export type RuntimeComponentPreviewAlignment = 'start' | 'center' | 'end'

export interface RuntimeComponentPreviewPlacementOptions {
  width_mode?: RuntimeComponentPreviewSizeMode
  width_value?: number | null
  height_mode?: RuntimeComponentPreviewSizeMode
  height_value?: number | null
  horizontal_align?: RuntimeComponentPreviewAlignment
  vertical_align?: RuntimeComponentPreviewAlignment
  padding?: number
}

export interface RuntimeComponentPreviewConfig {
  component_import_path: string
  component_source?: RuntimeComponentPreviewSource
  component_code?: string
  component_version_no?: number
  runtime_kit_component_name?: string
  runtime_kit_manifest_version?: string
  display_name?: string
  schema?: ComponentPreviewSchema | null
  placement?: RuntimeComponentPreviewPlacementOptions
}

export interface RuntimeAssetPreviewConfig {
  asset_id: number | string
  name: string
  original_name: string
  asset_type: RuntimePreviewAssetMetadata['render_type'] | string
  render_type: RuntimePreviewAssetMetadata['render_type'] | string
  content_type?: string | null
  url?: string | null
  content_editable?: boolean
  file_hash: string
}

export interface RuntimePreloadedConfigBundle {
  app?: unknown
  routes?: unknown
  icons?: unknown
  themes?: unknown
  fonts?: RuntimeFontBundle
  manifest?: RuntimePreviewArtifactManifest
  module_resolver?: RuntimeModuleResolverConfig
  component_preview?: RuntimeComponentPreviewConfig
  asset_preview?: RuntimeAssetPreviewConfig
}

export const RUNTIME_REMOTE_MODULE_PREFIX = '/@runtime-preview'
export const RUNTIME_SNAPDOM_RESOURCE_PROXY_PATH = '/__runtime-snapdom-resource-proxy'

const BUILTIN_LOCAL_VIEW_PREFIXES = [
  'src/runtime-shell/fallback/',
]

const DEFAULT_RUNTIME_PUBLIC_LOCAL_PREFIXES = [
  'src/runtime-kit/public/',
]

/**
 * 规范化视图模块逻辑路径，统一转为 `src/views/...` 形式。
 * @param rawPath 原始组件路径
 * @returns 规范化后的逻辑路径
 */
export function normalizeViewModulePath(rawPath: string): string {
  return normalizeRuntimeModulePath(rawPath)
}

/**
 * 规范化运行时模块逻辑路径，统一转为 `src/...` 形式。
 * @param rawPath 原始模块路径
 * @returns 规范化后的逻辑路径
 */
export function normalizeRuntimeModulePath(rawPath: string): string {
  const normalized = String(rawPath || '').trim().replace(/\\/g, '/')
  if (!normalized) {
    return ''
  }
  const remoteComponentPath = parseWorkspaceComponentImportPath(normalized)
  if (remoteComponentPath) {
    return remoteComponentPath
  }
  if (normalized.startsWith('@runtime-kit/')) {
    return normalized.replace('@runtime-kit/', 'src/runtime-kit/')
  }
  if (normalized.startsWith('@/')) {
    return normalized.replace('@/', 'src/')
  }
  if (normalized.startsWith('/src/')) {
    return normalized.slice(1)
  }
  if (normalized.startsWith('src/')) {
    return normalized
  }
  if (normalized.startsWith('views/')) {
    return `src/${normalized}`
  }
  if (normalized.startsWith('/views/')) {
    return `src${normalized}`
  }
  if (normalized.startsWith('workspace-components/')) {
    return normalizeWorkspaceComponentPath(`src/${normalized}`)
  }
  if (normalized.startsWith('/workspace-components/')) {
    return normalizeWorkspaceComponentPath(`src${normalized}`)
  }
  return normalized.replace(/^\/+/, '')
}

/**
 * 解析单页面预览入口对应的页面模块路径。
 * @param entryDescriptor 预览入口描述
 * @returns 页面模块逻辑路径；非直接页面模块预览时返回空串
 */
export function resolvePreviewEntryModulePath(entryDescriptor?: RuntimePreviewEntryDescriptor | null): string {
  if (!entryDescriptor || entryDescriptor.entry_type !== 'module') {
    return ''
  }
  const normalizedPath = normalizeRuntimeModulePath(entryDescriptor.module_path || '')
  if (!normalizedPath.startsWith('src/views/') || !normalizedPath.endsWith('.vue')) {
    return ''
  }
  return normalizedPath
}

/**
 * 解析项目级预览入口路由。
 * @param entryDescriptor 预览入口描述
 * @returns 入口路由；未命中时返回空串
 */
export function resolvePreviewEntryRoute(entryDescriptor?: RuntimePreviewEntryDescriptor | null): string {
  if (!entryDescriptor || entryDescriptor.entry_type !== 'route') {
    return ''
  }
  return String(entryDescriptor.route || '').trim()
}

/**
 * 判断视图模块是否属于 Runtime 本地内建页面。
 * @param normalizedPath 已规范化的视图逻辑路径
 * @returns 是否为本地内建视图
 */
export function isBuiltinLocalViewPath(normalizedPath: string): boolean {
  return BUILTIN_LOCAL_VIEW_PREFIXES.some(prefix => normalizedPath.startsWith(prefix))
}

/**
 * 判断模块是否属于 Runtime 对远程模块开放的本地公共模块。
 * @param normalizedPath 已规范化的模块路径
 * @returns 是否为 Runtime 本地公共模块
 */
export function isRuntimeLocalPublicModulePath(normalizedPath: string): boolean {
  return DEFAULT_RUNTIME_PUBLIC_LOCAL_PREFIXES.some(prefix => normalizedPath.startsWith(prefix))
}

/**
 * 将 `src/views/...` 路径转为 `@/views/...` 别名形式。
 * @param normalizedPath 规范化后的逻辑路径
 * @returns 别名路径
 */
export function toAliasViewPath(normalizedPath: string): string {
  return toAliasModulePath(normalizedPath)
}

/**
 * 将 `src/...` 路径转为运行时可理解的别名形式。
 * @param normalizedPath 规范化后的逻辑路径
 * @returns 别名路径
 */
export function toAliasModulePath(normalizedPath: string): string {
  if (!normalizedPath) {
    return normalizedPath
  }
  if (normalizedPath.startsWith('src/workspace-components/')) {
    return toWorkspaceComponentAliasPath(normalizedPath)
  }
  if (normalizedPath.startsWith('src/runtime-kit/')) {
    return normalizedPath.replace(/^src\/runtime-kit\//, '@runtime-kit/')
  }
  if (normalizedPath.startsWith('@/')) {
    return normalizedPath
  }
  if (normalizedPath.startsWith('src/')) {
    return normalizedPath.replace(/^src\//, '@/')
  }
  return `@/${normalizedPath.replace(/^\/+/, '')}`
}

/**
 * 构建浏览器侧可直接动态导入的远程模块标识。
 * 关键约束：
 * 1. 逻辑模块路径必须编码到 pathname 中，避免 Vue SFC 子请求丢失 `path` 查询参数；
 * 2. `ctx` 仍保留在 query 中，供首个模块请求完成鉴权与 token 缓存。
 * @param artifactId preview artifact ID
 * @param modulePath 逻辑模块路径
 * @param previewToken 预览上下文 token
 * @param runtimePublicBaseUrl Runtime 浏览器可访问基址
 * @returns 远程模块 ID
 */
export function buildRemoteModuleId(
  artifactId: string,
  modulePath: string,
  previewToken: string,
  runtimePublicBaseUrl = resolveRuntimePublicBaseUrl(),
): string {
  const normalizedPath = normalizeRuntimeModulePath(modulePath)
  const searchParams = new URLSearchParams({
    ctx: previewToken,
  })
  const encodedModulePath = normalizedPath
    .split('/')
    .filter(Boolean)
    .map(segment => encodeURIComponent(segment))
    .join('/')
  const remoteModulePrefix = `${normalizeRuntimePublicBaseUrl(runtimePublicBaseUrl)}${RUNTIME_REMOTE_MODULE_PREFIX}`
  return `${remoteModulePrefix}/${encodeURIComponent(artifactId)}/${encodedModulePath}?${searchParams.toString()}`
}

/**
 * 读取浏览器侧 Runtime 公开基址；非浏览器环境返回空串以保留本地测试默认路径。
 * @returns Runtime 公开基址
 */
function resolveRuntimePublicBaseUrl(): string {
  if (typeof window === 'undefined') {
    return ''
  }
  return String(window.__RUNTIME_PUBLIC_BASE_URL__ || '')
}

/**
 * 规范化 Runtime 公开基址，去掉尾部斜杠。
 * @param rawBaseUrl 原始 Runtime 公开基址
 * @returns 可拼接远程模块前缀的基址
 */
function normalizeRuntimePublicBaseUrl(rawBaseUrl: string): string {
  return String(rawBaseUrl || '').trim().replace(/\/+$/, '')
}

/**
 * 解析远程模块 ID。
 * @param id 模块 ID
 * @returns 解析结果，非远程模块时返回 null
 */
export function parseRemoteModuleId(id: string): { artifactId: string; modulePath: string; previewToken?: string } | null {
  const normalizedId = String(id || '').trim().replace(/\\/g, '/')
  if (!normalizedId) {
    return null
  }

  const [pathPart, queryPart = ''] = normalizedId.split('?', 2)
  const remotePath = extractRemoteModulePath(pathPart)
  if (!remotePath) {
    return null
  }

  const segments = remotePath.split('/').filter(Boolean)
  if (segments.length < 2) {
    return null
  }

  const artifactId = decodeURIComponent(segments[0] || '')
  const searchParams = new URLSearchParams(queryPart)
  const encodedModulePathSegments = segments.slice(1)
  const modulePath = normalizeRuntimeModulePath(
    encodedModulePathSegments.map(segment => decodeURIComponent(segment)).join('/'),
  )
  const previewToken = searchParams.get('ctx') || undefined
  if (!artifactId || !modulePath) {
    return null
  }

  return { artifactId, modulePath, previewToken }
}

/**
 * 从绝对或相对形式的远程模块 ID 中提取 `/@runtime-preview/<artifactId>/...` 之后的路径片段。
 * @param pathPart 不含 query 的模块 ID 路径部分
 * @returns 远程模块相对路径；未命中时返回空
 */
function extractRemoteModulePath(pathPart: string): string {
  const normalizedPath = String(pathPart || '').trim().replace(/\\/g, '/')
  const prefixWithoutLeadingSlash = RUNTIME_REMOTE_MODULE_PREFIX.replace(/^\//, '')

  if (normalizedPath.startsWith(`${prefixWithoutLeadingSlash}/`)) {
    return normalizedPath.slice(prefixWithoutLeadingSlash.length + 1)
  }

  if (normalizedPath.startsWith(RUNTIME_REMOTE_MODULE_PREFIX)) {
    return normalizedPath.slice(RUNTIME_REMOTE_MODULE_PREFIX.length + 1)
  }

  const embeddedMarker = `/${prefixWithoutLeadingSlash}/`
  const embeddedIndex = normalizedPath.lastIndexOf(embeddedMarker)
  if (embeddedIndex < 0) {
    return ''
  }

  return normalizedPath.slice(embeddedIndex + embeddedMarker.length)
}

/**
 * 判断当前远程模块请求是否命中了单页面预览入口页。
 * @param modulePath 本次请求的远程模块逻辑路径
 * @param entryDescriptor 预览入口描述
 * @returns 是否为入口页模块请求
 */
export function isPreviewEntryModuleRequest(modulePath: string, entryDescriptor?: RuntimePreviewEntryDescriptor | null): boolean {
  const normalizedModulePath = normalizeRuntimeModulePath(modulePath)
  const previewEntryModulePath = resolvePreviewEntryModulePath(entryDescriptor)
  return Boolean(normalizedModulePath && previewEntryModulePath && normalizedModulePath === previewEntryModulePath)
}

/**
 * 判断当前上下文是否为组件预览宿主页。
 * @param previewContext 公开预览上下文
 * @returns 是否为组件预览
 */
export function isComponentPreviewContext(previewContext?: RuntimePreviewContext | null): boolean {
  return Boolean(
    previewContext
    && previewContext.previewKind === 'component'
    && previewContext.entryDescriptor?.entry_type === 'component_host',
  )
}

/**
 * 将资源路径规范化为发布产物索引 key。
 * @param rawPath 原始资源路径
 * @returns 规范化 key
 */
export function normalizeAssetKey(rawPath: string): string {
  return String(rawPath || '')
    .trim()
    .replace(/\\/g, '/')
    .replace(/^\.?\/*/, '')
}

/**
 * 解析工作空间组件导入别名。
 * @param rawPath 原始导入路径
 * @returns 对应的逻辑模块路径；未命中时返回 null
 */
function parseWorkspaceComponentImportPath(rawPath: string): string | null {
  const normalized = String(rawPath || '').trim().replace(/\\/g, '/')
  const match = normalized.match(/^@workspace-components\/([^/]+)\/v\/(\d+)(?:\.vue)?$/)
  if (!match) {
    return null
  }
  return `src/workspace-components/${match[1]}/v/${match[2]}.vue`
}

/**
 * 规范化工作空间组件逻辑路径，补齐 `.vue` 后缀。
 * @param normalizedPath 逻辑路径
 * @returns 标准化后的路径
 */
function normalizeWorkspaceComponentPath(normalizedPath: string): string {
  const trimmedPath = normalizedPath.replace(/^\/+/, '')
  return trimmedPath.endsWith('.vue') ? trimmedPath : `${trimmedPath}.vue`
}

/**
 * 将工作空间组件逻辑路径转回约定别名。
 * @param normalizedPath 标准化后的组件路径
 * @returns 组件别名路径
 */
function toWorkspaceComponentAliasPath(normalizedPath: string): string {
  const match = normalizedPath.match(/^src\/workspace-components\/([^/]+)\/v\/(\d+)(?:\.vue)?$/)
  if (!match) {
    return `@/${normalizedPath.replace(/^src\//, '')}`
  }
  return `@workspace-components/${match[1]}/v/${match[2]}`
}
