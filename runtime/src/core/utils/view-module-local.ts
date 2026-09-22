/**
 * 文件用途：提供 Runtime 本地 fixture/开发模式可加载的页面模块映射。
 */

import type { RuntimeViewModule } from './view-module'

type ViewModuleLoader = () => Promise<RuntimeViewModule>

/**
 * Runtime 本地开发 / 本地构建模式可加载的页面模块。
 * 关键约束：
 * 1. 本文件只能由非 Backend build release 路径动态导入；
 * 2. 允许加载 `src/views/**` 与 `src/examples/local/views/**` 下的本地页面；
 * 3. Backend 构建态不应把本文件纳入 Rollup 依赖图。
 */
const LOCAL_RUNTIME_VIEW_MODULES: Record<string, ViewModuleLoader> = {
  ...import.meta.glob<RuntimeViewModule>('@/views/**/*.vue'),
  ...import.meta.glob<RuntimeViewModule>('/src/views/**/*.vue'),
  ...import.meta.glob<RuntimeViewModule>('@/examples/local/views/**/*.vue'),
  ...import.meta.glob<RuntimeViewModule>('/src/examples/local/views/**/*.vue'),
}

/**
 * 解析 Runtime 本地模式下的页面模块导入器。
 * @param aliasPath `@/views/...` 形式的别名路径
 * @returns 对应导入器；未命中时返回 null
 */
export function resolveLocalRuntimeViewModuleLoader(aliasPath: string): ViewModuleLoader | null {
  if (!aliasPath) {
    return null
  }

  const directLoader = LOCAL_RUNTIME_VIEW_MODULES[aliasPath]
  if (directLoader) {
    return directLoader
  }

  const srcPath = aliasPath.replace('@/', '/src/')
  return LOCAL_RUNTIME_VIEW_MODULES[srcPath] || null
}
