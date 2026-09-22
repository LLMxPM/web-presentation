/**
 * 文件用途：统一加载组件预览宿主页所需的远程工作空间组件和 Runtime 本地公共组件模块。
 */

import {
  buildRemoteModuleId,
  isRuntimeLocalPublicModulePath,
  normalizeRuntimeModulePath,
  toAliasModulePath,
} from '@/core/shared/runtime-preview'
import { getRuntimePreviewContext, getRuntimePreviewToken } from '@/core/utils/path'

const LOCAL_PREVIEW_MODULES = {
  ...import.meta.glob('@runtime-kit/public/components/**/*.vue'),
  ...import.meta.glob('/src/runtime-kit/public/components/**/*.vue'),
}

/**
 * 动态导入组件预览宿主页允许使用的模块。
 * @param modulePath 工作空间组件别名或 Runtime 公共模块路径
 * @returns 模块对象
 */
export async function importPreviewModule(modulePath: string): Promise<unknown> {
  const normalizedPath = normalizeRuntimeModulePath(modulePath)
  if (!normalizedPath) {
    throw new Error('组件预览模块路径不能为空。')
  }

  if (normalizedPath.startsWith('src/workspace-components/')) {
    const previewContext = getRuntimePreviewContext()
    if (!previewContext) {
      throw new Error('当前不处于 Runtime 预览模式，无法加载工作空间组件。')
    }
    const previewToken = getRuntimePreviewToken()
    if (!previewToken) {
      throw new Error('缺少 Runtime 预览上下文 token，无法加载工作空间组件。')
    }
    const remoteModuleId = buildRemoteModuleId(
      previewContext.artifactId,
      normalizedPath,
      previewToken,
    )
    return import(/* @vite-ignore */ remoteModuleId)
  }

  if (!isRuntimeLocalPublicModulePath(normalizedPath)) {
    throw new Error(`组件预览不允许加载未开放的本地模块：${modulePath}`)
  }

  const aliasPath = toAliasModulePath(normalizedPath)
  const loader = LOCAL_PREVIEW_MODULES[aliasPath] || LOCAL_PREVIEW_MODULES[aliasPath.replace('@runtime-kit/', '/src/runtime-kit/')]
  if (!loader) {
    throw new Error(`未找到组件预览本地模块：${modulePath}`)
  }
  return loader()
}
