/**
 * 扩展的路由生成器和相关工具函数
 * 从配置自动生成路由、菜单和处理路由信息查询
 * 重构后的统一路由处理模块
 */

import type { RouteRecordRaw } from 'vue-router'
import type { RouteConfig, NavigationItem, BaseRouteConfig } from '@/core/types'
import type { MenuItem, MenuConfig } from '@/core/types/menu'
import { routeConfigs } from '@/core/utils/config'
import { buildFullPath } from './path'
import {
  buildRelativePath,
  buildRouteFullPath
} from './route-path-builder'

// ==================== 辅助函数 ====================

/**
 * 按order排序路由配置
 * @param routes 路由配置数组
 * @returns 排序后的路由配置数组
 */
function sortRoutesByOrder<T extends RouteConfig | BaseRouteConfig>(routes: T[]): T[] {
  return routes.sort((a, b) => {
    const orderA = a.meta?.order ?? 999
    const orderB = b.meta?.order ?? 999
    return orderA - orderB
  })
}

/**
 * 过滤可见路由（不隐藏的路由）
 * @param routes 路由配置数组
 * @returns 过滤后的数组
 */
function filterVisibleRoutes<T extends RouteConfig | BaseRouteConfig>(routes: T[]): T[] {
  return routes.filter(route => {
    // 检查 meta.hidden
    if ('meta' in route && route.meta) {
      return !route.meta.hidden
    }
    // 默认为可见
    return true
  })
}

/**
 * 过滤并排序路由：先过滤可见路由，再按order排序
 * @param routes 路由配置数组
 * @returns 过滤并排序后的路由配置数组
 */
function filterAndSortRoutes<T extends RouteConfig | BaseRouteConfig>(routes: T[]): T[] {
  return sortRoutesByOrder(filterVisibleRoutes(routes))
}

// ==================== 路由生成 ====================

/**
 * 路由信息接口
 */
export interface RouteInfo {
  name: string          // 路由名称(title)
  path: string          // 路由路径
  level: number         // 层级(0为父路由，1为子路由)
  order: number         // 排序值
  pageNumber?: number   // 页码，表示在所有显示页面中的顺序
  parentPath?: string   // 父路由路径
  hidden?: boolean      // 是否隐藏
  component?: string    // 组件路径
  speakerNotes?: string | null // 演讲者备注
}



/**
 * 从路由配置生成 Vue Router 路由
 * 采用独立页面架构，所有路由都是平级的独立路由
 */
export function generateRoutes(
  configs: RouteConfig[]
): RouteRecordRaw[] {
  const flattenedRoutes: RouteRecordRaw[] = []

  configs.forEach(config => {
    const hasChildren = config.children && config.children.length > 0

    if (hasChildren) {
      // 有子路由时，父路由只是分组，生成重定向路由到第一个可见子路由
      const visibleChildren = config.children!.filter(child => !child.meta?.hidden)
      const sortedChildren = [...visibleChildren].sort((a, b) => (a.meta?.order ?? 999) - (b.meta?.order ?? 999))
      const firstChild = sortedChildren[0]

      if (firstChild) {
        // 父路由重定向到第一个子路由
        const parentPath = config.path.startsWith('/') ? config.path : `/${config.path}`
        flattenedRoutes.push({
          path: parentPath,
          redirect: `${parentPath}/${firstChild.path}`,
          meta: config.meta as RouteRecordRaw['meta']
        } as RouteRecordRaw)
      }

      // 添加子路由（作为独立路由）
      config.children!.forEach(child => {
        const childRoute = convertToRouteRecord(child, false, config.path)
        flattenedRoutes.push(childRoute)
      })
    } else {
      // 没有子路由时，正常注册为独立页面
      flattenedRoutes.push(convertToRouteRecord(config, true))
    }
  })

  return flattenedRoutes
}

/**
 * 将路由配置转换为 Vue Router 路由记录
 * @param config 路由配置
 * @param isParent 是否为父路由
 * @param parentPath 父路由路径（仅用于子路由）
 */
function convertToRouteRecord(
  config: RouteConfig | BaseRouteConfig,
  isParent: boolean = true,
  parentPath?: string
): RouteRecordRaw {
  // 根据是否为子路由构建路径
  let routePath: string
  if (isParent) {
    // 父路由使用 '/' + config.path 的格式
    routePath = config.path.startsWith('/') ? config.path : `/${config.path}`
  } else {
    // 子路由使用完整路径 '/父路径/子路径' 的格式
    routePath = `/${parentPath}/${config.path}`
  }

  const route: RouteRecordRaw = {
    path: routePath,
    name: 'name' in config ? config.name : config.title,
    component: config.component || (() => Promise.resolve({})),
    meta: config.meta as RouteRecordRaw['meta']
  }

  // 注意：不再处理子路由，因为所有路由都是独立的

  return route
}

/**
 * 根据路由名称查找路由配置
 */
function findRouteByName(name: string): RouteConfig | undefined {
  function searchInRoutes(routes: (RouteConfig | BaseRouteConfig)[]): RouteConfig | undefined {
    for (const route of routes) {
      const routeName = 'name' in route ? route.name : route.title
      if (routeName === name) {
        return route as RouteConfig
      }
      if (route.children) {
        const found = searchInRoutes(route.children)
        if (found) return found
      }
    }
    return undefined
  }

  return searchInRoutes(routeConfigs.value)
}

/**
 * 从路由配置生成导航菜单
 */
export function generateNavigation(): NavigationItem[] {
  return filterAndSortRoutes(routeConfigs.value)
    .map(route => convertToNavigationItem(route))
}

/**
 * 将路由配置转换为导航项
 */
function convertToNavigationItem(config: RouteConfig | BaseRouteConfig, parentPath: string = ''): NavigationItem {
  // 使用统一的路径构建工具
  const relativePath = buildRelativePath(config, parentPath)
  const fullPath = buildRouteFullPath(config, parentPath)

  const configName = 'name' in config ? config.name : config.title
  const configTitle = config.meta?.title || config.title || configName

  const item: NavigationItem = {
    id: configName,
    title: configTitle,
    path: fullPath,
    order: config.meta?.order || 0,
    hidden: config.meta?.hidden || false,
    disabled: config.meta?.disabled || false,
    meta: config.meta ? { ...config.meta } : undefined
  }

  // 处理子路由
  if (config.children && config.children.length > 0) {
    const visibleChildren = config.children
      .filter(child => {
        // 隐藏条件：
        // 1. meta.hidden = true
        const shouldHide = child.meta?.hidden

        return !shouldHide
      })
      .sort((a, b) => (a.meta?.order || 0) - (b.meta?.order || 0))
      .map(child => convertToNavigationItem(child, relativePath))

    // 只有当有可见的子路由时才添加 children 属性  
    if (visibleChildren.length > 0) {
      item.children = visibleChildren
    }

  }

  return item
}

/**
 * 从路由配置生成菜单配置
 */
export function generateMenuConfig(): MenuConfig {
  try {
    // 确保 routeConfigs.value 存在且不为空
    // console.log('generateMenuConfig - routeConfigs.value:', routeConfigs.value)
    const routes = routeConfigs.value || []
    // console.log('generateMenuConfig - routes:', routes)
    const items = filterAndSortRoutes(routes)
      .map(route => convertToMenuItem(route))

    // console.log('generateMenuConfig - items:', items)
    const result = {
      items,
      searchable: true,
      collapsible: true
    }
    // console.log('generateMenuConfig - result:', result)
    return result
  } catch {
    // console.error('generateMenuConfig 出错:', error)
    return {
      items: [],
      searchable: true,
      collapsible: true
    }
  }
}

/**
 * 将路由配置转换为菜单项
 */
function convertToMenuItem(config: RouteConfig | BaseRouteConfig, parentPath: string = ''): MenuItem {
  // console.log('=== convertToMenuItem 开始 ===')
  // console.log('路由配置:', config)
  // console.log('父级路径:', parentPath)

  // 使用统一的路径构建工具
  const relativePath = buildRelativePath(config, parentPath)
  const fullPath = buildRouteFullPath(config, parentPath)
  // console.log('构建的相对路径:', relativePath)
  // console.log('构建的完整路径:', fullPath)

  const configName = 'name' in config ? config.name : config.title
  const configTitle = config.meta?.title || config.title || configName

  const item: MenuItem = {
    id: configName,
    title: configTitle,
    path: fullPath,
    order: config.meta?.order || 0,
    hidden: config.meta?.hidden || config.meta?.hiddenInMenu || false,
    disabled: config.meta?.disabled || false,
    meta: config.meta ? { ...config.meta } : undefined
  }

  // 处理子路由
  if (config.children && config.children.length > 0) {
    const visibleChildren = config.children
      .filter(child => {
        // 隐藏条件：
        // 1. meta.hidden = true
        // 2. meta.hiddenInMenu = true
        const shouldHide = child.meta?.hidden ||
          child.meta?.hiddenInMenu

        return !shouldHide
      })
      .sort((a, b) => (a.meta?.order || 0) - (b.meta?.order || 0))
      .map(child => convertToMenuItem(child, relativePath))

    // 只有当有可见的子路由时才添加 children 属性  
    if (visibleChildren.length > 0) {
      item.children = visibleChildren
    }

  }

  return item
}


/**
 * 检查路由是否激活
 */
export function isRouteActive(routePath: string, currentPath: string): boolean {
  // 精确匹配
  if (routePath === currentPath) return true

  // 处理根路径的特殊情况
  if (routePath === '/' && currentPath !== '/') return false

  // 对于一级菜单，如果当前路径是其子路径，则认为激活
  // 例如：routePath = '/equipment-agent', currentPath = '/equipment-agent/overview'
  if (routePath !== '/' && currentPath.startsWith(routePath + '/')) {
    return true
  }

  return false
}

/**
 * 检查是否有激活的子路由
 */
export function hasActiveChild(item: NavigationItem | MenuItem, currentPath: string): boolean {
  if (!item.children) return false

  return item.children.some(child => {
    // 精确匹配子路由   
    if (child.path === currentPath) return true

    // 递归检查子路由的子路由
    return hasActiveChild(child, currentPath)
  })
}


/**
 * 获取路由的完整路径
 */
export function getFullRoutePath(routeName: string): string {
  const route = findRouteByName(routeName)
  if (!route) return buildFullPath('/')

  // 构建完整路径，确保包含baseURL但不重复
  return buildFullPath(route.path)
}

/**
 * 扁平化导航项
 */
export function flattenNavigationItems(items: NavigationItem[]): NavigationItem[] {
  const flattened: NavigationItem[] = []

  function flatten(items: NavigationItem[]) {
    items.forEach(item => {
      flattened.push(item)
      if (item.children) {
        flatten(item.children)
      }
    })
  }

  flatten(items)
  return flattened
}

// ==================== 路由信息查询功能 ====================

// ==================== 路由信息查询功能 ====================

/**
 * 获取所有路由信息（从已转换的routeConfig获取）
 * @returns 路由信息数组
 */
export function getAllRouteInfos(): RouteInfo[] {
  const routeInfos: RouteInfo[] = []

  // 使用已经转换并计算好页码的routeConfig
  const configs = routeConfigs.value
  if (!configs || configs.length === 0) {
    return routeInfos
  }

  // 扁平化路由配置，提取路由信息
  configs.forEach(parentConfig => {
    const hasChildren = parentConfig.children && parentConfig.children.length > 0

    if (!hasChildren) {
      // 没有子路由的路由是独立页面，添加到路由信息
      routeInfos.push({
        name: parentConfig.title,
        path: `/${parentConfig.path}`,
        level: 0,
        order: parentConfig.order || parentConfig.meta?.order || 0,
        pageNumber: parentConfig.pageNumber || parentConfig.meta?.pageNumber,
        hidden: parentConfig.meta?.hidden || false,
        component: parentConfig.component ? 'parent-component' : undefined,
        speakerNotes: typeof parentConfig.meta?.speakerNotes === 'string' ? parentConfig.meta.speakerNotes : null
      })
    }
    // 有子路由的父路由只是分组，不作为独立页面加入路由信息

    // 添加子路由信息
    if (hasChildren) {
      parentConfig.children!.forEach(childConfig => {
        // 构建子路由完整路径 
        const childPath = `/${parentConfig.path}/${childConfig.path}`

        routeInfos.push({
          name: childConfig.title,
          path: childPath,
          level: 1,
          order: childConfig.order || childConfig.meta?.order || 0,
          pageNumber: childConfig.pageNumber || childConfig.meta?.pageNumber,
          parentPath: `/${parentConfig.path}`,
          hidden: childConfig.meta?.hidden || false,
          component: childConfig.component ? 'child-component' : 'unknown',
          speakerNotes: typeof childConfig.meta?.speakerNotes === 'string' ? childConfig.meta.speakerNotes : null
        })
      })
    }
  })
  return routeInfos
}

// ... 文件中其他的函数 (getRouteInfoByPath, getRouteInfoByName 等) 保持不变 ...

/**
 * 根据路径获取路由信息
 * @param path 路由路径
 * @returns 路由信息或undefined
 */
export function getRouteInfoByPath(path: string): RouteInfo | undefined {
  const allRoutes = getAllRouteInfos()
  return allRoutes.find(route => route.path === path)
}

/**
 * 根据名称获取路由信息
 * @param name 路由名称
 * @returns 路由信息或undefined
 */
export function getRouteInfoByName(name: string): RouteInfo | undefined {
  const allRoutes = getAllRouteInfos()
  return allRoutes.find(route => route.name === name)
}

/**
 * 获取所有父路由信息
 * @returns 父路由信息数组
 */
export function getParentRouteInfos(): RouteInfo[] {
  return getAllRouteInfos().filter(route => route.level === 0)
}

/**
 * 获取指定父路由的所有子路由
 * @param parentPath 父路由路径
 * @returns 子路由信息数组
 */
export function getChildRouteInfos(parentPath: string): RouteInfo[] {
  return getAllRouteInfos().filter(route => route.level === 1 && route.parentPath === parentPath)
}

/**
 * 获取按order排序的路由信息
 * @param level 可选，指定层级(0或1)，不指定则返回所有层级
 * @returns 排序后的路由信息数组
 */
export function getRouteInfosSortedByOrder(level?: number): RouteInfo[] {
  let routes = getAllRouteInfos()

  if (level !== undefined) {
    routes = routes.filter(route => route.level === level)
  }

  return routes.sort((a, b) => {
    // 首先按层级排序，然后按order排序
    if (a.level !== b.level) {
      return a.level - b.level
    }
    return a.order - b.order
  })
}

/**
 * 获取按pageNumber排序的路由信息
 * @param level 可选，指定层级(0或1)，不指定则返回所有层级
 * @returns 按页码排序的路由信息数组
 */
export function getRouteInfosSortedByPageNumber(level?: number): RouteInfo[] {
  let routes = getAllRouteInfos().filter(route => route.pageNumber !== undefined)

  if (level !== undefined) {
    routes = routes.filter(route => route.level === level)
  }

  return routes.sort((a, b) => {
    // 首先按页码排序，如果页码相同则按order排序
    if (a.pageNumber !== b.pageNumber) {
      return (a.pageNumber || 0) - (b.pageNumber || 0)
    }
    return a.order - b.order
  })
}

/**
 * 根据路由路径获取路由的pageNumber
 * @param path 路由路径
 * @returns pageNumber 或 undefined
 */
export function getPageNumberByPath(path: string): number | undefined {
  // console.log("path", path)
  const routeInfo = getRouteInfoByPath(path)
  // console.log('当前页码', routeInfo?.pageNumber)
  return routeInfo?.pageNumber
}

/**
 * 根据路由名称获取路由的pageNumber
 * @param name 路由名称
 * @returns pageNumber 或 undefined
 */
export function getPageNumberByName(name: string): number | undefined {
  const routeInfo = getRouteInfoByName(name)
  return routeInfo?.pageNumber
}

/**
 * 获取指定页码的路由信息
 * @param pageNumber 页码
 * @returns 路由信息或undefined
 */
export function getRouteInfoByPageNumber(pageNumber: number): RouteInfo | undefined {
  const allRoutes = getAllRouteInfos()
  return allRoutes.find(route => route.pageNumber === pageNumber)
}

/**
 * 获取下一页的路由信息
 * @param currentPageNumber 当前页码
 * @returns 下一页的路由信息或undefined
 */
export function getNextPageRouteInfo(currentPageNumber: number): RouteInfo | undefined {
  const sortedRoutes = getRouteInfosSortedByPageNumber()
  const currentIndex = sortedRoutes.findIndex(route => route.pageNumber === currentPageNumber)

  if (currentIndex >= 0 && currentIndex < sortedRoutes.length - 1) {
    return sortedRoutes[currentIndex + 1]
  }

  return undefined
}

/**
 * 获取上一页的路由信息
 * @param currentPageNumber 当前页码
 * @returns 上一页的路由信息或undefined
 */
export function getPreviousPageRouteInfo(currentPageNumber: number): RouteInfo | undefined {
  const sortedRoutes = getRouteInfosSortedByPageNumber()
  const currentIndex = sortedRoutes.findIndex(route => route.pageNumber === currentPageNumber)

  if (currentIndex > 0) {
    return sortedRoutes[currentIndex - 1]
  }

  return undefined
}

/**
 * 获取按页码范围的路由信息
 * @param startPage 起始页码
 * @param endPage 结束页码
 * @returns 指定范围内的路由信息数组
 */
export function getRouteInfosByPageRange(startPage: number, endPage: number): RouteInfo[] {
  const allRoutes = getAllRouteInfos()
  return allRoutes.filter(route =>
    route.pageNumber !== undefined &&
    route.pageNumber >= startPage &&
    route.pageNumber <= endPage
  ).sort((a, b) => (a.pageNumber || 0) - (b.pageNumber || 0))
}

/**
 * 获取最大页码
 * @returns 最大页码数
 */
export function getMaxPageNumber(): number {
  const allRoutes = getAllRouteInfos()
  const pageNumbers = allRoutes
    .map(route => route.pageNumber)
    .filter(pageNumber => pageNumber !== undefined) as number[]

  return pageNumbers.length > 0 ? Math.max(...pageNumbers) : 0
}

/**
 * 获取最小页码
 * @returns 最小页码数
 */
export function getMinPageNumber(): number {
  const allRoutes = getAllRouteInfos()
  const pageNumbers = allRoutes
    .map(route => route.pageNumber)
    .filter(pageNumber => pageNumber !== undefined) as number[]

  return pageNumbers.length > 0 ? Math.min(...pageNumbers) : 0
}

/**
 * 获取可见的路由信息（未隐藏的）
 * @param level 可选，指定层级
 * @returns 可见的路由信息数组
 */
export function getVisibleRouteInfos(level?: number): RouteInfo[] {
  let routes = getAllRouteInfos().filter(route => !route.hidden)

  if (level !== undefined) {
    routes = routes.filter(route => route.level === level)
  }

  return routes.sort((a, b) => {
    if (a.level !== b.level) {
      return a.level - b.level
    }
    return a.order - b.order
  })
}

/**
 * 获取路由的层级结构
 * @returns 层级结构对象，key为父路由路径，value为子路由数组
 */
export function getRouteHierarchy(): Record<string, RouteInfo[]> {
  const hierarchy: Record<string, RouteInfo[]> = {}
  const allRoutes = getAllRouteInfos()

  // 获取所有父路由
  const parentRoutes = allRoutes.filter(route => route.level === 0)

  parentRoutes.forEach(parentRoute => {
    hierarchy[parentRoute.path] = allRoutes.filter(route =>
      route.level === 1 && route.parentPath === parentRoute.path
    ).sort((a, b) => a.order - b.order)
  })

  return hierarchy
}

/**
 * 获取路由总数统计
 * @returns 统计信息对象
 */
export function getRouteStatistics(): {
  total: number
  parentRoutes: number
  childRoutes: number
  hiddenRoutes: number
  visibleRoutes: number
  withPageNumber: number
  withoutPageNumber: number
  maxPageNumber: number
  minPageNumber: number
} {
  const allRoutes = getAllRouteInfos()
  const routesWithPageNumber = allRoutes.filter(route => route.pageNumber !== undefined)

  return {
    total: allRoutes.length,
    parentRoutes: allRoutes.filter(route => route.level === 0).length,
    childRoutes: allRoutes.filter(route => route.level === 1).length,
    hiddenRoutes: allRoutes.filter(route => route.hidden).length,
    visibleRoutes: allRoutes.filter(route => !route.hidden).length,
    withPageNumber: routesWithPageNumber.length,
    withoutPageNumber: allRoutes.length - routesWithPageNumber.length,
    maxPageNumber: getMaxPageNumber(),
    minPageNumber: getMinPageNumber()
  }
}
