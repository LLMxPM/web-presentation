/**
 * 文件用途：提供 Runtime 整包构建插件复用的 baseUrl 与静态资源路径辅助函数。
 */

import { extname, resolve } from 'path'

import autoprefixer from 'autoprefixer'
import tailwindcss from 'tailwindcss'
import type { UserConfig } from 'vite'

import { normalizeRuntimeModulePath, toAliasModulePath } from '../shared/runtime-preview'

const ROOT_ABSOLUTE_ASSET_PATTERNS = [
  /url\((['"]?)\/(?:img|fonts|favicon)/i,
  /(?:src|href)=['"]\/(?:img|fonts|favicon)/i,
  /\b(?:src|href)\s*:\s*['"]\/(?:img|fonts|favicon)/i,
  /[:=]\s*['"]\/(?:img|fonts|favicon)/i,
]

/**
 * 规范化整项目构建使用的部署基路径。
 * @param rawBaseUrl 用户输入或请求体中的原始 baseUrl
 * @returns 规范化后的 baseUrl
 */
export function normalizeBuildBaseUrl(rawBaseUrl: string | undefined | null): string {
  const normalized = String(rawBaseUrl || '').trim()
  if (!normalized || normalized === '.' || normalized === './') {
    return './'
  }

  if (/^https?:\/\//i.test(normalized) || normalized.startsWith('//')) {
    throw new Error('base_url 不能是完整 URL 或双斜杠路径。')
  }

  if (!normalized.startsWith('/')) {
    throw new Error('base_url 仅支持 ./ 或以 / 开头。')
  }

  return normalized.endsWith('/') ? normalized : `${normalized}/`
}

/**
 * 根据资源哈希与原始文件名生成静态构建产物中的资源路径。
 * @param fileHash Backend 下发的资源 hash
 * @param originalName 原始文件名
 * @param logicalName 逻辑资源名
 * @returns 静态资源相对路径
 */
export function buildStaticAssetPath(fileHash: string, originalName?: string, logicalName?: string): string {
  const normalizedHash = String(fileHash || '').trim()
  if (!normalizedHash) {
    throw new Error('缺少资源 hash，无法生成静态资源路径。')
  }

  const extension = extname(String(originalName || '').trim() || String(logicalName || '').trim())
  return `__build_assets/${normalizedHash}${extension || ''}`
}

/**
 * 构建 Runtime 临时工作区专用 CSS 配置。
 * @param tempRoot Runtime 构建临时工作区根目录
 * @returns Vite CSS 配置
 */
export function buildRuntimeBuildCssConfig(tempRoot: string): NonNullable<UserConfig['css']> {
  return {
    modules: {
      localsConvention: 'camelCase',
    },
    postcss: {
      plugins: [
        tailwindcss(resolve(tempRoot, 'tailwind.config.js')),
        autoprefixer(),
      ],
    },
  }
}

/**
 * 判断源码文本中是否存在根绝对静态资源引用。
 * 关键约束：
 * 1. 仅检查真实源码，不把注释中的示例路径视为违规；
 * 2. 仅拦截 `/img`、`/fonts`、`/favicon` 这类站点根路径资源；
 * 3. 远程 URL 与相对路径不在此校验范围内。
 * @param content 待检查源码文本
 * @returns 是否命中非法根绝对静态资源引用
 */
export function hasForbiddenRootAbsoluteAssetPath(content: string): boolean {
  const sanitizedContent = stripInspectableComments(content)
  return ROOT_ABSOLUTE_ASSET_PATTERNS.some(pattern => pattern.test(sanitizedContent))
}

/**
 * 生成 build release 专用页面模块映射源码。
 * @param modulePaths manifest.modules 中的逻辑模块路径
 * @returns 可写入 `build-release-view-modules.ts` 的源码
 */
export function createBuildReleaseViewModulesSource(modulePaths: Iterable<string>): string {
  const moduleEntries = new Map<string, string>()
  const normalizedPaths = Array.from(modulePaths)
    .map(path => normalizeBuildReleaseViewModulePath(path))
    .filter((path): path is string => Boolean(path))
    .sort()

  for (const normalizedPath of normalizedPaths) {
    const aliasPath = toBuildReleaseAliasPath(normalizedPath)
    moduleEntries.set(aliasPath, aliasPath)
    moduleEntries.set(`/${normalizedPath}`, aliasPath)
  }

  const entries = Array.from(moduleEntries.entries())
    .map(([key, importPath]) => `  ${JSON.stringify(key)}: () => import(${JSON.stringify(importPath)}),`)

  return [
    '/**',
    ' * 文件用途：Backend build release 临时页面模块映射，由 Runtime 构建插件按 manifest 生成。',
    ' */',
    '',
    'export const BUILD_RELEASE_VIEW_MODULES = {',
    ...entries,
    '} satisfies Record<string, () => Promise<unknown>>',
    '',
  ].join('\n')
}

/**
 * 生成诊断态专用模块加载器源码，覆盖页面与工作空间组件。
 * @param modulePaths manifest.modules 中的逻辑模块路径
 * @returns 可写入 `build-diagnostics-modules.ts` 的源码
 */
export function createDiagnosticsBuildModulesSource(modulePaths: Iterable<string>): string {
  const importPaths = Array.from(new Set(Array.from(modulePaths)
    .map(path => normalizeDiagnosticsBuildModulePath(path))
    .filter((path): path is string => Boolean(path))
    .map(path => toAliasModulePath(path))))
    .sort()

  const entries = importPaths.map(importPath => `  () => import(${JSON.stringify(importPath)}),`)

  return [
    '/**',
    ' * 文件用途：Runtime 诊断态临时模块加载器，由 Runtime 构建插件按 manifest 生成。',
    ' */',
    '',
    'export const BUILD_DIAGNOSTICS_MODULE_LOADERS = [',
    ...entries,
    '] satisfies Array<() => Promise<unknown>>',
    '',
  ].join('\n')
}

/**
 * 规范化 build release 中允许进入路由映射的页面模块路径。
 * @param rawPath 原始逻辑路径
 * @returns 标准 `src/views/*.vue` 路径；非法路径返回空
 */
function normalizeBuildReleaseViewModulePath(rawPath: string): string {
  let normalizedPath = String(rawPath || '').trim().replace(/\\/g, '/')
  if (!normalizedPath) {
    return ''
  }
  if (normalizedPath.startsWith('@/')) {
    normalizedPath = normalizedPath.replace('@/', 'src/')
  } else if (normalizedPath.startsWith('/src/')) {
    normalizedPath = normalizedPath.slice(1)
  }
  normalizedPath = normalizedPath.replace(/^\/+/, '')

  const segments = normalizedPath.split('/')
  if (segments.some(segment => segment === '.' || segment === '..' || segment === '')) {
    return ''
  }
  if (!normalizedPath.startsWith('src/views/') || !normalizedPath.endsWith('.vue')) {
    return ''
  }
  return normalizedPath
}

/**
 * 规范化诊断态允许主动加载的模块路径。
 * @param rawPath 原始逻辑路径
 * @returns 标准页面或工作空间组件路径；非法路径返回空
 */
function normalizeDiagnosticsBuildModulePath(rawPath: string): string {
  const normalizedPath = normalizeRuntimeModulePath(rawPath)
  const segments = normalizedPath.split('/')
  if (segments.some(segment => segment === '.' || segment === '..' || segment === '')) {
    return ''
  }
  if (!normalizedPath.endsWith('.vue')) {
    return ''
  }
  if (normalizedPath.startsWith('src/views/') || normalizedPath.startsWith('src/workspace-components/')) {
    return normalizedPath
  }
  return ''
}

/**
 * 将 build release 视图逻辑路径转换为源码别名路径。
 * @param normalizedPath 标准 `src/views/*.vue` 路径
 * @returns `@/views/*.vue` 路径
 */
function toBuildReleaseAliasPath(normalizedPath: string): string {
  return normalizedPath.replace(/^src\//, '@/')
}

/**
 * 移除源码中的常见注释，避免示例代码触发根绝对路径误报。
 * @param content 原始源码文本
 * @returns 去除注释后的源码文本
 */
export function stripInspectableComments(content: string): string {
  return String(content || '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}
