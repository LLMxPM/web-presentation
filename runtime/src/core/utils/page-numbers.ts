/**
 * 文件用途：以不依赖 Vue 的纯函数分配运行时路由页码，并投影出页面可读取的路由目录。
 *
 * config.ts 与跨端契约测试共用本模块：Backend 侧按同一规则复算页码目录，用于判断
 * 静态截图是否仍然匹配；两侧规则必须逐字节一致，否则会出现截图反复失效或错误复用。
 *
 * 目录投影只保留「静态截图中真正会变像素」的字段，逐项口径见 buildCatalogItem。
 */

/** 路由节点结构：只声明页码分配与目录投影真正读取的字段。 */
export interface RouteNumberingNode {
  route: string
  component?: string
  meta: {
    title?: string
    order?: number
    pageNumber?: number
    hidden?: boolean
    [key: string]: unknown
  }
  children?: RouteNumberingNode[]
}

/** 单条页面可读路由目录项。 */
export interface RouteCatalogItem {
  path: string
  title: string
  order: number
  pageNumber?: number
  parentPath?: string
  hidden: boolean
}

/** 路由目录投影：目录项、最大页码与最小页码。 */
export interface RouteCatalogProjection {
  catalog: RouteCatalogItem[]
  totalPages: number
  minPageNumber: number
}

/**
 * 按路由 meta.order 升序排列，未配置时按 0 处理。
 * @param left 左侧路由配置
 * @param right 右侧路由配置
 * @returns 排序结果
 */
function sortRoutesByOrder<T extends { meta?: { order?: number } }>(left: T, right: T): number {
  return (left.meta?.order || 0) - (right.meta?.order || 0)
}

/** 判断路由节点是否隐藏；隐藏节点不参与页码编号。 */
function isHiddenRoute(node: RouteNumberingNode): boolean {
  return Boolean(node.meta?.hidden)
}

/**
 * 按 Runtime 既定规则为路由配置分配页码。
 *
 * 规则：顶层按 order 稳定排序；有子路由的顶层节点只是分组，自身不占页码，
 * 其可见子路由按 order 排序后连续编号；隐藏分组不影响其子路由编号。
 * 输出为深拷贝，不修改入参。
 *
 * @param routes 运行时路由配置
 * @returns 带 meta.pageNumber 的排序后路由配置副本
 */
export function assignPageNumbers<T extends RouteNumberingNode>(routes: T[]): T[] {
  // 保持既有行为：走 JSON 深拷贝，丢弃 undefined 字段后再排序赋值。
  const ordered = JSON.parse(JSON.stringify(routes)) as T[]
  ordered.sort(sortRoutesByOrder)

  let currentPageNumber = 1
  ordered.forEach((route) => {
    const hasChildren = Array.isArray(route.children) && route.children.length > 0

    if (!hasChildren && !isHiddenRoute(route)) {
      route.meta.pageNumber = currentPageNumber
      currentPageNumber += 1
    }

    if (hasChildren && route.children) {
      // 原地排序，使目录投影与 route-generator 的子路由顺序一致。
      route.children.sort(sortRoutesByOrder)
      route.children.forEach((child) => {
        if (!isHiddenRoute(child)) {
          child.meta.pageNumber = currentPageNumber
          currentPageNumber += 1
        }
      })
    }
  })

  return ordered
}

/**
 * 把已分配页码的路由配置投影为页面可读取的目录。
 *
 * 分组节点自身不进入目录；可见与隐藏叶子都会保留：隐藏叶子没有 pageNumber，
 * 但 getRouteInfoByPath 仍能命中，其标题对页面可见。
 *
 * @param routes 已完成页码分配的路由配置
 * @returns 目录项、总页数与最小页码
 */
export function projectRouteCatalog(routes: RouteNumberingNode[]): RouteCatalogProjection {
  const catalog: RouteCatalogItem[] = []

  routes.forEach((route) => {
    const children = Array.isArray(route.children) ? route.children : []
    if (children.length === 0) {
      catalog.push(buildCatalogItem(`/${route.route}`, route, undefined))
      return
    }
    children.forEach((child) => {
      catalog.push(buildCatalogItem(`/${route.route}/${child.route}`, child, `/${route.route}`))
    })
  })

  const pageNumbers = catalog
    .map(item => item.pageNumber)
    .filter((value): value is number => typeof value === 'number')

  return {
    catalog,
    totalPages: pageNumbers.length > 0 ? Math.max(...pageNumbers) : 0,
    minPageNumber: pageNumbers.length > 0 ? Math.min(...pageNumbers) : 0,
  }
}

/**
 * 分配页码并投影目录，供配置加载与跨端契约测试共用。
 * @param routes 运行时路由配置
 * @returns 目录项、总页数与最小页码
 */
export function buildRouteCatalogProjection(routes: RouteNumberingNode[]): RouteCatalogProjection {
  return projectRouteCatalog(assignPageNumbers(routes))
}

/**
 * 构造单条目录项。
 *
 * 收录：path（目录跳转与 getPageNumberByPath）、title（目录文字与 useCurrentPage 回退）、
 * order（routesByOrder）、pageNumber（页码显示）、parentPath（层级）、hidden（可见性过滤）。
 * 剔除：component（只决定 artifact 模块白名单，不改本页输出）、speakerNotes（演讲台与
 * PPTX 导出专用）、transition/advance（捕获上下文禁用播放）。
 *
 * @param path 完整路由路径
 * @param node 路由节点
 * @param parentPath 父分组路径
 * @returns 目录项
 */
function buildCatalogItem(
  path: string,
  node: RouteNumberingNode,
  parentPath: string | undefined,
): RouteCatalogItem {
  const meta = node.meta ?? {}
  const item: RouteCatalogItem = {
    path,
    title: typeof meta.title === 'string' ? meta.title : '',
    order: Number(meta.order ?? 0) || 0,
    hidden: Boolean(meta.hidden),
  }
  if (typeof meta.pageNumber === 'number') {
    item.pageNumber = meta.pageNumber
  }
  if (parentPath) {
    item.parentPath = parentPath
  }
  return item
}
