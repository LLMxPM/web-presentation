/**
 * 文件用途：提供 Backend build release 构建态页面模块映射的默认空实现。
 *
 * Runtime 构建插件会在临时工作区中用当前 artifact manifest 生成的版本覆盖本文件。
 */

import type { RuntimeViewModule } from './view-module'

export type BuildReleaseViewModuleLoader = () => Promise<RuntimeViewModule>

export const BUILD_RELEASE_VIEW_MODULES: Record<string, BuildReleaseViewModuleLoader> = {}
