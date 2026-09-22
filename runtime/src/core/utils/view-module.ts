/**
 * 文件用途：统一处理页面视图模块的本地加载、远程虚拟模块加载与缺省回退逻辑。
 */

import type { Component } from 'vue'

import {
  type RuntimePreloadedConfigBundle,
  buildRemoteModuleId,
  isBuiltinLocalViewPath,
  normalizeRuntimeModulePath,
  toAliasModulePath,
} from '@/core/shared/runtime-preview'
import { getRuntimePreviewContext, getRuntimePreviewToken, getRuntimePreloadedConfig } from '@/core/utils/path'
import { BUILD_RELEASE_VIEW_MODULES } from './build-release-view-modules'

export interface RuntimeViewModule {
  default?: Component
  [key: string]: unknown
}

type ViewModuleLoader = () => Promise<RuntimeViewModule>

/**
 * Runtime 壳层内建兜底页面模块。
 * 关键约束：
 * 1. 仅保留远程预览/发布仍必须依赖的壳层页面；
 * 2. 主要用于 NotFound 等兜底页，避免依赖本地示例目录。
 */
const BUILTIN_VIEW_MODULES = {
  ...import.meta.glob<RuntimeViewModule>('@/runtime-shell/fallback/*.vue'),
  ...import.meta.glob<RuntimeViewModule>('/src/runtime-shell/fallback/*.vue')
} satisfies Record<string, ViewModuleLoader>

const NOT_FOUND_FALLBACK_KEYS = [
  '@/runtime-shell/fallback/NotFoundPage.vue',
  '/src/runtime-shell/fallback/NotFoundPage.vue'
]

/**
 * 规范化逻辑路径并返回对应的本地别名路径。
 * @param viewPath 页面逻辑路径
 * @returns 规范化结果
 */
export function resolveViewModulePath(viewPath: string): {
  normalizedPath: string
  aliasPath: string
} {
  const normalizedPath = normalizeRuntimeModulePath(viewPath)
  return {
    normalizedPath,
    aliasPath: toAliasModulePath(normalizedPath)
  }
}

/**
 * 判断当前页面模块是否应通过远程发布产物加载。
 * @param normalizedPath 已规范化的逻辑路径
 * @returns 是否走远程虚拟模块
 */
export function shouldUseRemoteViewModule(normalizedPath: string): boolean {
  const previewContext = getRuntimePreviewContext()
  return Boolean(
    previewContext
    && normalizedPath
    && !isBuiltinLocalViewPath(normalizedPath)
  )
}

/**
 * 判断当前页面模块是否应在 build release 模式下按本地构建产物加载。
 * @param normalizedPath 已规范化的逻辑路径
 * @param preloadedConfig 当前预加载配置
 * @returns 是否应走 build release 本地模块
 */
export function shouldUseBuildReleaseLocalViewModule(
  normalizedPath: string,
  preloadedConfig?: RuntimePreloadedConfigBundle,
): boolean {
  const manifest = preloadedConfig?.manifest
  if (!normalizedPath || isBuiltinLocalViewPath(normalizedPath)) {
    return false
  }
  if (manifest?.artifact_kind !== 'build_release') {
    return false
  }
  return Boolean(manifest.modules?.[normalizedPath])
}

/**
 * 判断当前页面模块是否应在 Runtime 本地模式下按本地页面模块加载。
 * @param normalizedPath 已规范化的逻辑路径
 * @param preloadedConfig 当前预加载配置
 * @returns 是否应走 runtime 本地页面模块
 */
export function shouldUseLocalRuntimeViewModule(
  normalizedPath: string,
  preloadedConfig?: RuntimePreloadedConfigBundle,
): boolean {
  const isLocalViewPath = normalizedPath.startsWith('src/views/')
    || normalizedPath.startsWith('src/examples/local/views/')

  if (!normalizedPath || !isLocalViewPath || !normalizedPath.endsWith('.vue')) {
    return false
  }

  if (getRuntimePreviewContext()) {
    return false
  }

  if (preloadedConfig?.manifest?.artifact_kind === 'build_release') {
    return false
  }

  return true
}

/**
 * 生成页面模块的动态导入器。
 * @param viewPath 页面逻辑路径
 * @returns 异步模块导入函数
 */
export function createViewModuleLoader(viewPath: string): () => Promise<RuntimeViewModule> {
  return async () => importViewModule(viewPath)
}

/**
 * 动态导入页面模块。
 * @param viewPath 页面逻辑路径
 * @returns 页面模块对象
 */
export async function importViewModule(viewPath: string): Promise<RuntimeViewModule> {
  const { normalizedPath, aliasPath } = resolveViewModulePath(viewPath)
  const preloadedConfig = getRuntimePreloadedConfig()

  if (!normalizedPath) {
    return importFallbackModule()
  }

  if (shouldUseRemoteViewModule(normalizedPath)) {
    const previewContext = getRuntimePreviewContext()
    if (!previewContext) {
      return importFallbackModule()
    }
    const previewToken = getRuntimePreviewToken()
    if (!previewToken) {
      return importFallbackModule()
    }

    const remoteModuleId = buildRemoteModuleId(
      previewContext.artifactId,
      normalizedPath,
      previewToken,
    )
    return import(/* @vite-ignore */ remoteModuleId) as Promise<RuntimeViewModule>
  }

  const builtinLoader = resolveBuiltinViewModuleLoader(aliasPath)
  if (builtinLoader) {
    return builtinLoader()
  }

  const buildReleaseLoader = resolveBuildReleaseViewModuleLoader(aliasPath, normalizedPath, preloadedConfig)
  if (buildReleaseLoader) {
    return buildReleaseLoader()
  }

  const localModuleLoader = await resolveLocalRuntimeViewModuleLoader(aliasPath, normalizedPath, preloadedConfig)
  if (localModuleLoader) {
    return localModuleLoader()
  }

  return importFallbackModule()
}

/**
 * 解析内建默认页面模块导入器。
 * @param aliasPath `@/views/...` 形式的别名路径
 * @returns 对应导入器；未命中时返回 null
 */
function resolveBuiltinViewModuleLoader(aliasPath: string): ViewModuleLoader | null {
  if (!aliasPath) {
    return null
  }
  if (!isBuiltinLocalViewPath(normalizeRuntimeModulePath(aliasPath))) {
    return null
  }

  const directLoader = BUILTIN_VIEW_MODULES[aliasPath]
  if (directLoader) {
    return directLoader
  }

  const srcPath = aliasPath.replace('@/', '/src/')
  return BUILTIN_VIEW_MODULES[srcPath] || null
}

/**
 * 解析 Runtime 本地模式下的页面模块导入器。
 * @param aliasPath `@/views/...` 形式的别名路径
 * @param normalizedPath `src/views/...` 形式的逻辑路径
 * @param preloadedConfig 当前预加载配置
 * @returns 对应导入器；未命中时返回 null
 */
async function resolveLocalRuntimeViewModuleLoader(
  aliasPath: string,
  normalizedPath: string,
  preloadedConfig?: RuntimePreloadedConfigBundle,
): Promise<ViewModuleLoader | null> {
  if (__RUNTIME_BACKEND_BUILD__) {
    return null
  }
  if (!shouldUseLocalRuntimeViewModule(normalizedPath, preloadedConfig)) {
    return null
  }

  const localModules = await import('./view-module-local')
  return localModules.resolveLocalRuntimeViewModuleLoader(aliasPath)
}

/**
 * 解析 build release 模式下的本地页面模块导入器。
 * @param aliasPath `@/views/...` 形式的别名路径
 * @param normalizedPath `src/views/...` 形式的逻辑路径
 * @param preloadedConfig 当前预加载配置
 * @returns 对应导入器；未命中时返回 null
 */
function resolveBuildReleaseViewModuleLoader(
  aliasPath: string,
  normalizedPath: string,
  preloadedConfig?: RuntimePreloadedConfigBundle,
): ViewModuleLoader | null {
  if (!shouldUseBuildReleaseLocalViewModule(normalizedPath, preloadedConfig)) {
    return null
  }

  const directLoader = BUILD_RELEASE_VIEW_MODULES[aliasPath]
  if (directLoader) {
    return directLoader
  }

  const srcPath = aliasPath.replace('@/', '/src/')
  return BUILD_RELEASE_VIEW_MODULES[srcPath] || null
}

/**
 * 加载本地内建的 NotFound 页面。
 * @returns Fallback 模块
 */
async function importFallbackModule(): Promise<RuntimeViewModule> {
  for (const fallbackKey of NOT_FOUND_FALLBACK_KEYS) {
    const loader = BUILTIN_VIEW_MODULES[fallbackKey]
    if (loader) {
      return loader()
    }
  }

  return {
    default: {
      template: '<div class="p-8 text-red-600">页面组件加载失败</div>'
    }
  }
}
