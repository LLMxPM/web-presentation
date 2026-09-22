/**
 * 路由路径构建工具函数
 * 提供统一的路径构建逻辑，避免代码重复
 */

import type { RouteConfig, BaseRouteConfig } from '@/core/types'
import { buildFullPath } from './path'

/**
 * 构建路由的相对路径
 * @param config 路由配置
 * @param parentPath 父路径
 * @returns 相对路径
 */
export function buildRelativePath(config: RouteConfig | BaseRouteConfig, parentPath = ''): string {
  if (config.path === '') {
    // 索引路由：使用父路径，如果没有父路径则使用路由名
    const configName = 'name' in config ? config.name : config.title
    return parentPath || configName
  } else {
    // 普通路由：拼接父路径和当前路径
    if (parentPath) {
      return `${parentPath}/${config.path}`.replace(/\/+/g, '/')
    } else {
      return config.path
    }
  }
}

/**
 * 构建子路由的完整路径
 * @param child 子路由配置
 * @param parentPath 父路径
 * @returns 子路由的完整路径
 */
export function buildChildRoutePath(child: RouteConfig | BaseRouteConfig, parentPath: string): string {
  if (child.path === '' || child.meta?.isIndex) {
    // 索引路由使用父路径
    return parentPath
  } else {
    // 普通子路由拼接路径
    const childPath = child.path.startsWith('/') ? child.path : `/${child.path}`
    return `${parentPath}${childPath}`.replace(/\/+/g, '/')
  }
}

/**
 * 构建路由的完整路径（包含base路径）
 * @param config 路由配置
 * @param parentPath 父路径
 * @returns 包含base路径的完整路径
 */
export function buildRouteFullPath(config: RouteConfig | BaseRouteConfig, parentPath = ''): string {
  const relativePath = buildRelativePath(config, parentPath)
  return buildFullPath(relativePath)
}

/**
 * 标准化路径格式
 * @param path 原始路径
 * @returns 标准化后的路径
 */
export function normalizeRoutePath(path: string): string {
  // 确保路径以 / 开头
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  // 去除多余的斜杠
  return normalizedPath.replace(/\/+/g, '/')
}

/**
 * 构建完整的父子路由路径结构
 * @param parentConfig 父路由配置
 * @param childConfig 子路由配置
 * @returns 完整的路径信息
 */
export function buildParentChildPaths(
  parentConfig: RouteConfig | BaseRouteConfig,
  childConfig: RouteConfig | BaseRouteConfig
): {
  parentPath: string
  childPath: string
  fullChildPath: string
} {
  const parentPath = buildRelativePath(parentConfig)
  const childPath = buildChildRoutePath(childConfig, parentPath)
  const fullChildPath = buildFullPath(childPath)
  
  return {
    parentPath,
    childPath,
    fullChildPath
  }
}