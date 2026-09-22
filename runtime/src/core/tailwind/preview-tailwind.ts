/**
 * 文件用途：为 SaaS 预览 artifact 按需编译远程页面与工作空间组件源码中的 Tailwind utilities。
 */

import { createHash } from 'crypto'

import postcss from 'postcss'
import tailwindcss from 'tailwindcss'
import type { Config } from 'tailwindcss'

import {
  normalizeRuntimeModulePath,
  type RuntimePreviewArtifactManifest,
  type RuntimePreviewEntryDescriptor,
  type RuntimeReleaseManifestModule,
} from '../shared/runtime-preview'
import { runtimeTailwindTheme } from './runtime-tailwind-theme.js'

export interface PreviewTailwindSource {
  logicalPath: string
  content: string
  contentHash?: string
}

export interface PreviewModuleSourceBackendClient {
  fetchModuleSource(artifactId: string, modulePath: string): Promise<string>
}

export const DEFAULT_PREVIEW_TAILWIND_PATH = '/__preview-tailwind.css'

const SUPPORTED_RAW_EXTENSIONS = new Set(['vue', 'html', 'js', 'ts', 'jsx', 'tsx'])

/**
 * 规范化预览 Tailwind CSS 内部端点路径。
 * @param rawPath 原始端点路径
 * @returns 以单个斜杠开头的端点路径
 */
export function normalizePreviewTailwindEndpointPath(rawPath: string): string {
  const normalized = String(rawPath || '').trim()
  if (!normalized) {
    return DEFAULT_PREVIEW_TAILWIND_PATH
  }
  return normalized.startsWith('/') ? normalized : `/${normalized}`
}

/**
 * 构造预览 artifact Tailwind utilities CSS 链接。
 * @param params 链接参数
 * @returns 可写入 HTML 的 stylesheet href
 */
export function buildPreviewTailwindStylesheetHref(params: {
  assetBase: string
  artifactId: string
  previewToken: string
  previewTailwindPath?: string
}): string {
  const endpointPath = normalizePreviewTailwindEndpointPath(
    params.previewTailwindPath || DEFAULT_PREVIEW_TAILWIND_PATH,
  )
  const searchParams = new URLSearchParams({
    artifactId: params.artifactId,
    token: params.previewToken,
  })
  return `${params.assetBase || ''}${endpointPath}?${searchParams.toString()}`
}

/**
 * 根据远程模块逻辑路径推断 Tailwind raw content 的扩展名。
 * @param logicalPath 远程模块逻辑路径
 * @returns Tailwind raw content extension
 */
export function inferTailwindRawExtension(logicalPath: string): string {
  const cleanPath = String(logicalPath || '').split('?', 2)[0]
  const extension = cleanPath.split('.').pop()?.toLowerCase() || ''
  return SUPPORTED_RAW_EXTENSIONS.has(extension) ? extension : 'html'
}

/**
 * 对源码内容生成稳定 hash，用于 artifact CSS 缓存签名。
 * @param content 源码内容
 * @returns sha256 hash
 */
export function hashPreviewTailwindSource(content: string): string {
  return createHash('sha256').update(content).digest('hex')
}

/**
 * 构造按 artifact 源码集合缓存 CSS 的稳定签名。
 * @param sources 远程源码集合
 * @returns 源码集合签名
 */
export function buildPreviewTailwindCacheSignature(sources: PreviewTailwindSource[]): string {
  const hash = createHash('sha256')
  const normalizedSources = [...sources].sort((left, right) => left.logicalPath.localeCompare(right.logicalPath))
  if (normalizedSources.length === 0) {
    return 'empty'
  }

  for (const source of normalizedSources) {
    hash.update(source.logicalPath)
    hash.update('\0')
    hash.update(source.contentHash || hashPreviewTailwindSource(source.content))
    hash.update('\0')
  }
  return hash.digest('hex')
}

/**
 * 收集需要参与预览 Tailwind utilities 编译的远程模块源码。
 * @param params 收集参数
 * @returns 远程源码集合
 */
export async function collectPreviewTailwindSources(params: {
  artifactId: string
  manifest: RuntimePreviewArtifactManifest
  entryDescriptor?: RuntimePreviewEntryDescriptor | null
  backendClient: PreviewModuleSourceBackendClient
}): Promise<PreviewTailwindSource[]> {
  const moduleEntries = new Map<string, string | RuntimeReleaseManifestModule | undefined>()
  for (const [modulePath, manifestEntry] of Object.entries(params.manifest.modules || {})) {
    const normalizedPath = normalizeRuntimeModulePath(modulePath)
    if (normalizedPath) {
      moduleEntries.set(normalizedPath, manifestEntry)
    }
  }

  if (params.entryDescriptor?.entry_type === 'module') {
    const entryModulePath = normalizeRuntimeModulePath(params.entryDescriptor.module_path || '')
    if (entryModulePath && !moduleEntries.has(entryModulePath)) {
      moduleEntries.set(entryModulePath, undefined)
    }
  }

  const sources: PreviewTailwindSource[] = []
  for (const [modulePath, manifestEntry] of moduleEntries) {
    const content = await params.backendClient.fetchModuleSource(params.artifactId, modulePath)
    sources.push({
      logicalPath: modulePath,
      content,
      contentHash: getManifestModuleHash(manifestEntry) || hashPreviewTailwindSource(content),
    })
  }
  return sources
}

/**
 * 读取 manifest 模块条目中的内容 hash。
 * @param manifestEntry manifest 中的模块条目
 * @returns 模块 hash；不存在时返回空串
 */
function getManifestModuleHash(manifestEntry: string | RuntimeReleaseManifestModule | undefined): string {
  if (!manifestEntry) {
    return ''
  }
  if (typeof manifestEntry === 'string') {
    return manifestEntry
  }
  return String(manifestEntry.hash || '')
}

/**
 * 用 Tailwind/PostCSS 从远程源码 raw content 中只编译 utilities 层。
 * @param sources 远程页面与工作空间组件源码
 * @returns CSS 文本；无远程源码时返回空 CSS 注释
 */
export async function compilePreviewTailwindUtilities(sources: PreviewTailwindSource[]): Promise<string> {
  const effectiveSources = sources.filter(source => String(source.content || '').trim())
  if (effectiveSources.length === 0) {
    return '/* preview tailwind: no remote modules */\n'
  }

  const config: Config = {
    content: effectiveSources.map(source => ({
      raw: source.content,
      extension: inferTailwindRawExtension(source.logicalPath),
    })) as NonNullable<Config['content']>,
    safelist: [],
    theme: runtimeTailwindTheme,
    corePlugins: {
      preflight: false,
    },
    plugins: [],
  }
  const result = await postcss([tailwindcss(config)]).process('@tailwind utilities;', {
    from: undefined,
  })
  return `/* preview tailwind: ${effectiveSources.length} remote modules */\n${result.css}`
}
