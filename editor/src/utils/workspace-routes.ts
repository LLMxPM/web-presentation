/**
 * 文件功能：集中生成 Editor 工作空间内常用页面路径，避免页面与布局中重复拼接路由字符串。
 */

export type WorkspaceRouteKey = 'projects' | 'components' | 'assets' | 'themes' | 'styles'

/**
 * 生成工作空间项目首页路径。
 * @param workspaceId 工作空间 ID
 */
export function buildWorkspaceHomePath(workspaceId: number | string): string {
  return `/workspaces/${workspaceId}/home`
}

/**
 * 生成工作空间组件库路径。
 * @param workspaceId 工作空间 ID
 * @param componentId 可选的待打开组件 ID
 */
export function buildWorkspaceComponentsPath(workspaceId: number | string, componentId?: number | string | null): string {
  const path = `/workspaces/${workspaceId}/components`
  return componentId ? `${path}?componentId=${componentId}` : path
}

/**
 * 生成工作空间资源库路径。
 * @param workspaceId 工作空间 ID
 * @param assetId 可选的待打开资源 ID
 */
export function buildWorkspaceAssetsPath(workspaceId: number | string, assetId?: number | string | null): string {
  const path = `/workspaces/${workspaceId}/assets`
  return assetId ? `${path}?assetId=${assetId}` : path
}

/**
 * 生成工作空间主题字体页路径。
 * @param workspaceId 工作空间 ID
 */
export function buildWorkspaceThemesPath(workspaceId: number | string): string {
  return `/workspaces/${workspaceId}/themes`
}

/**
 * 生成工作空间样式库路径。
 * @param workspaceId 工作空间 ID
 */
export function buildWorkspaceStylesPath(workspaceId: number | string): string {
  return `/workspaces/${workspaceId}/styles`
}

/**
 * 生成项目页面列表路径。
 * @param workspaceId 工作空间 ID
 * @param projectId 项目 ID
 */
export function buildProjectPagesPath(workspaceId: number | string, projectId: number | string): string {
  return `/workspaces/${workspaceId}/projects/${projectId}/pages`
}

/**
 * 生成页面详情路径。
 * @param workspaceId 工作空间 ID
 * @param projectId 项目 ID
 * @param pageId 页面 ID
 */
export function buildPageDetailPath(
  workspaceId: number | string,
  projectId: number | string,
  pageId: number | string,
): string {
  return `${buildProjectPagesPath(workspaceId, projectId)}/${pageId}`
}

/**
 * 按导航 key 生成工作空间级页面路径。
 * @param workspaceId 工作空间 ID
 * @param key 右侧 Dock 导航 key
 */
export function buildWorkspaceRouteByKey(workspaceId: number | string, key: WorkspaceRouteKey): string {
  if (key === 'components') return buildWorkspaceComponentsPath(workspaceId)
  if (key === 'assets') return buildWorkspaceAssetsPath(workspaceId)
  if (key === 'themes') return buildWorkspaceThemesPath(workspaceId)
  if (key === 'styles') return buildWorkspaceStylesPath(workspaceId)
  return buildWorkspaceHomePath(workspaceId)
}
