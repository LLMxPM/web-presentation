/**
 * 文件用途：统一处理运行时配置来源、预览上下文、资源路径和站内导航路径。
 */

import type {
  RuntimeArtifactKind,
  RuntimePreloadedConfigBundle,
  RuntimePreviewContext,
} from '@/core/shared/runtime-preview'
import { normalizeAssetKey, resolvePreviewEntryModulePath } from '@/core/shared/runtime-preview'

export type ConfigFileName = 'app' | 'routes' | 'themes' | 'icons'

export interface RuntimeConfigContext {
  projectId?: number
  projectConfigBaseUrl?: string
}

/**
 * 判断是否为浏览器可直接访问的资源地址。
 * @param value 待判断的路径
 * @returns 是否为 http/https/data/blob 地址
 */
export function isRemoteUrl(value: string): boolean {
  return /^(https?:\/\/|data:|blob:)/i.test(value)
}

/**
 * 规范化相对资源路径。
 * @param value 原始路径
 * @returns 以 ./ 开头的相对路径
 */
function normalizeRelativePath(value: string): string {
  const normalized = value.trim().replace(/\\/g, '/').replace(/^\.?\/*/, '')
  if (!normalized) {
    return './'
  }

  return `./${normalized}`
}

/**
 * 读取浏览器侧注入的运行时配置上下文。
 * @returns 运行时配置上下文；非浏览器环境返回 undefined
 */
export function getRuntimeConfigContext(): RuntimeConfigContext | undefined {
  if (typeof window === 'undefined') {
    return undefined
  }
  return window.__RUNTIME_CONFIG_CONTEXT__
}

/**
 * 在浏览器侧写入运行时配置上下文，供本地只读 fixture 或测试场景覆盖配置来源。
 * @param context 运行时配置上下文；传空则清理
 */
export function setRuntimeConfigContext(context?: RuntimeConfigContext): void {
  if (typeof window === 'undefined') {
    return
  }

  if (!context) {
    delete window.__RUNTIME_CONFIG_CONTEXT__
    return
  }

  window.__RUNTIME_CONFIG_CONTEXT__ = context
}

/**
 * 读取浏览器侧注入的公开预览上下文。
 * @returns 公开预览上下文；非预览模式返回 undefined
 */
export function getRuntimePreviewContext(): RuntimePreviewContext | undefined {
  if (typeof window === 'undefined') {
    return undefined
  }
  return window.__RUNTIME_PREVIEW_CONTEXT__
}

/**
 * 写入公开预览上下文，仅供测试或受控入口注入。
 * @param context 公开预览上下文；传空则清理
 */
export function setRuntimePreviewContext(context?: RuntimePreviewContext): void {
  if (typeof window === 'undefined') {
    return
  }
  if (!context) {
    delete window.__RUNTIME_PREVIEW_CONTEXT__
    return
  }
  window.__RUNTIME_PREVIEW_CONTEXT__ = context
}

/**
 * 读取浏览器侧注入的预览上下文 token。
 * @returns 预览上下文 token；非预览模式返回空串
 */
export function getRuntimePreviewToken(): string {
  if (typeof window === 'undefined') {
    return ''
  }
  return String(window.__RUNTIME_PREVIEW_TOKEN__ || '')
}

/**
 * 写入预览上下文 token，仅供测试或受控入口注入。
 * @param token 预览上下文 token；传空则清理
 */
export function setRuntimePreviewToken(token?: string): void {
  if (typeof window === 'undefined') {
    return
  }
  if (!token) {
    delete window.__RUNTIME_PREVIEW_TOKEN__
    return
  }
  window.__RUNTIME_PREVIEW_TOKEN__ = token
}

/**
 * 读取浏览器侧注入的预加载配置包。
 * @returns 预加载配置；非预览模式返回 undefined
 */
export function getRuntimePreloadedConfig(): RuntimePreloadedConfigBundle | undefined {
  if (typeof window === 'undefined') {
    return undefined
  }
  return window.__RUNTIME_PRELOADED_CONFIG__
}

/**
 * 写入预加载配置包，仅供测试或受控入口注入。
 * @param config 预加载配置包；传空则清理
 */
export function setRuntimePreloadedConfig(config?: RuntimePreloadedConfigBundle): void {
  if (typeof window === 'undefined') {
    return
  }
  if (!config) {
    delete window.__RUNTIME_PRELOADED_CONFIG__
    return
  }
  window.__RUNTIME_PRELOADED_CONFIG__ = config
}

/**
 * 解析当前有效的外部配置根地址。
 * v1 仅保留 window 注入的受控地址，用于只读 fixture 或测试覆盖。
 * @returns 外部配置根地址；未配置时返回空串
 */
export function resolveExternalConfigBaseUrl(): string {
  const runtimeBaseUrl = getRuntimeConfigContext()?.projectConfigBaseUrl?.trim()
  if (runtimeBaseUrl) {
    return runtimeBaseUrl.replace(/\/+$/, '')
  }
  return ''
}

/**
 * 判断当前是否使用外部配置源。
 * @returns 是否存在远程或注入的配置根地址
 */
export function hasExternalConfigSource(): boolean {
  return resolveExternalConfigBaseUrl().length > 0
}

/**
 * 构建配置文件 URL。
 * @param configName 配置名称
 * @returns 配置文件的最终加载地址
 */
export function buildConfigUrl(configName: ConfigFileName): string {
  const configBaseUrl = resolveExternalConfigBaseUrl()
  const fileName = `${configName}.config.yaml`

  if (configBaseUrl) {
    return `${configBaseUrl}/${fileName}`
  }

  return `./config/${fileName}`
}

/**
 * 构建完整路径 - 用于菜单和导航
 * @param path 路由路径（相对或绝对）
 * @returns 完整路径（绝对）
 */
export function buildFullPath(path: string): string {
  if (!path || path === '') return '/'
  
  const cleanPath = path.startsWith('/') ? path : `/${path}`
  return cleanPath
}

/**
 * 解析资源路径
 * @param resourcePath 资源路径
 * @returns 解析后的完整路径
 */
export function resolveResourcePath(resourcePath: string): string {
  if (!resourcePath) {
    return './'
  }

  // 如果是绝对HTTP路径，直接返回
  if (isRemoteUrl(resourcePath)) {
    return resourcePath
  }

  const normalizedAssetKey = normalizeAssetKey(resourcePath)
  const preloadedConfig = getRuntimePreloadedConfig()
  const previewContext = getRuntimePreviewContext()
  const manifest = preloadedConfig?.manifest
  const assetMapping = manifest?.assets || {}
  const mappedAssetPath = resolveMappedAssetPath(assetMapping, normalizedAssetKey)
  const artifactKind = getRuntimeArtifactKind(manifest?.artifact_kind)
  if (mappedAssetPath) {
    return resolveArtifactMappedPath({
      artifactKind,
      mappedAssetPath,
      previewContext,
      manifestAssetBaseUrl: manifest?.asset_base_url,
    })
  }

  return normalizeRelativePath(resourcePath)
}

/**
 * 规范化 artifact 类型，未声明时视为本地模式。
 * @param rawArtifactKind manifest 中的 artifact_kind
 * @returns 当前资源解析策略对应的 artifact 类型
 */
function getRuntimeArtifactKind(rawArtifactKind: unknown): RuntimeArtifactKind | 'local' {
  const normalizedValue = String(rawArtifactKind || '').trim()
  if (
    normalizedValue === 'preview_artifact'
    || normalizedValue === 'page_visual_edit_preview'
    || normalizedValue === 'build_snapshot'
    || normalizedValue === 'build_release'
  ) {
    return normalizedValue
  }
  return 'local'
}

/**
 * 按 artifact 类型解析 manifest 命中的资源路径。
 * @param params 解析参数
 * @returns 浏览器可直接访问的最终资源地址
 */
function resolveArtifactMappedPath(params: {
  artifactKind: RuntimeArtifactKind | 'local'
  mappedAssetPath: string
  previewContext?: RuntimePreviewContext
  manifestAssetBaseUrl?: string
}): string {
  if (isRemoteUrl(params.mappedAssetPath)) {
    return params.mappedAssetPath
  }

  if (params.artifactKind === 'build_release') {
    return normalizeRelativePath(params.mappedAssetPath)
  }

  const assetBaseUrl = String(
    params.previewContext?.assetBaseUrl
    || params.manifestAssetBaseUrl
    || '',
  ).trim()
  return joinUrlPath(assetBaseUrl, params.mappedAssetPath)
}

/**
 * 解析 manifest.assets 中的资源映射，只允许按规范化后的精确 key 命中。
 * 关键约束：
 * 1. 工作空间资源必须使用 manifest 中声明的逻辑名；
 * 2. 不再支持大小写无关匹配；
 * 3. 不再支持 basename 或目录前缀兜底。
 * @param assetMapping manifest.assets 映射
 * @param normalizedAssetKey 已规范化的资源 key
 * @returns 命中的映射路径；未命中返回 undefined
 */
function resolveMappedAssetPath(assetMapping: Record<string, string>, normalizedAssetKey: string): string | undefined {
  const targetKey = normalizeAssetKey(normalizedAssetKey)
  if (!targetKey) {
    return undefined
  }

  return assetMapping[targetKey]
}

/**
 * 获取预览模式的初始路由。
 * @returns 入口路由；无预览上下文时返回空串
 */
export function getPreviewEntryRoute(): string {
  return String(getRuntimePreviewContext()?.entryDescriptor?.route || '').trim()
}

/**
 * 获取当前预览上下文对应的首屏导航路径。
 * @returns 路由路径；无预览上下文时返回空串
 */
export function getPreviewEntryNavigationPath(): string {
  const previewContext = getRuntimePreviewContext()
  const entryDescriptor = previewContext?.entryDescriptor
  if (!entryDescriptor) {
    return ''
  }
  if (entryDescriptor.entry_type === 'route') {
    return String(entryDescriptor.route || '').trim()
  }
  if (entryDescriptor.entry_type === 'module') {
    const modulePath = resolvePreviewEntryModulePath(entryDescriptor)
    return modulePath ? `/${modulePath}` : ''
  }
  if (entryDescriptor.entry_type === 'component_host') {
    return '/__component-preview'
  }
  if (entryDescriptor.entry_type === 'asset_host') {
    return '/__asset-preview'
  }
  return ''
}

/**
 * 判断是否需要把当前页面导航到预览入口。
 * @param entryPath 预览上下文声明的入口路径
 * @param currentHash 当前浏览器 hash；不传时读取 window.location.hash
 * @returns 当前没有显式 hash 路由时才需要主动导航
 */
export function shouldNavigateToPreviewEntryPath(entryPath: string, currentHash = readCurrentLocationHash()): boolean {
  const normalizedEntryPath = normalizeHashNavigationPath(entryPath)
  if (!normalizedEntryPath) {
    return false
  }

  const currentHashPath = normalizeHashNavigationPath(currentHash)
  return !currentHashPath || currentHashPath === '/'
}

/**
 * 读取当前浏览器 hash，供预览入口导航判定使用。
 * @returns 当前 hash；非浏览器环境返回空串
 */
function readCurrentLocationHash(): string {
  if (typeof window === 'undefined') {
    return ''
  }
  return String(window.location?.hash || '')
}

/**
 * 将 hash 或路径规整为 Vue Router hash history 使用的路径。
 * @param value hash 或路径
 * @returns 去掉 query/fragment 后的路径；无有效路径时返回空串
 */
function normalizeHashNavigationPath(value: string): string {
  const normalizedValue = String(value || '').trim().replace(/^#/, '')
  const pathWithoutQuery = normalizedValue.split(/[?#]/)[0]?.trim() || ''
  if (!pathWithoutQuery) {
    return ''
  }
  const path = pathWithoutQuery.startsWith('/') ? pathWithoutQuery : `/${pathWithoutQuery}`
  return normalizePath(path)
}

/**
 * 规范化路径
 * @param path 路径
 * @returns 规范化后的路径
 */
export function normalizePath(path: string): string {
  return path.replace(/\/+/g, '/').replace(/\/$/, '') || '/'
}

/**
 * 连接路径片段
 * @param paths 路径片段
 * @returns 连接后的路径
 */
export function joinPaths(...paths: string[]): string {
  return normalizePath(paths.filter(Boolean).join('/'))
}

/**
 * 拼接 URL 基地址与资源路径，避免出现重复斜杠。
 * @param baseUrl 基地址
 * @param resourcePath 资源路径
 * @returns 拼接后的 URL
 */
function joinUrlPath(baseUrl: string, resourcePath: string): string {
  const normalizedBase = String(baseUrl || '').trim().replace(/\/+$/, '')
  const normalizedResource = normalizeAssetKey(resourcePath)
  if (!normalizedBase) {
    return `./${normalizedResource}`
  }
  if (!normalizedResource) {
    return normalizedBase
  }
  return `${normalizedBase}/${normalizedResource}`
}
