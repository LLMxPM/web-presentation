/**
 * 文件功能：封装项目路由草稿的通用转换与默认值生成逻辑，供路由编辑器和页面列表复用。
 */
import type { PageItem, ProjectRouteItemWrite, ProjectRouteTreeItem } from '@/types/api'

const PROJECT_ROUTE_SEGMENT_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]*$/

/**
 * 将后端返回的树形路由结构转换为前端可写的草稿结构。
 */
export function mapRouteTreeToWriteItems(routeItems: ProjectRouteTreeItem[]): ProjectRouteItemWrite[] {
  return routeItems.map(routeItem => ({
    route_type: routeItem.route_type,
    route: routeItem.route,
    order: routeItem.order,
    hidden: routeItem.hidden,
    group_title: routeItem.group_title,
    page_id: routeItem.page_id,
    children: routeItem.children.map(child => ({
      route: child.route,
      order: child.order,
      hidden: child.hidden,
      page_id: child.page_id,
    })),
  }))
}

/**
 * 深拷贝路由草稿，避免在编辑过程中直接修改响应式入参。
 */
export function cloneProjectRoutes(routeItems: ProjectRouteItemWrite[]): ProjectRouteItemWrite[] {
  return routeItems.map(routeItem => ({
    route_type: routeItem.route_type,
    route: routeItem.route,
    order: routeItem.order,
    hidden: Boolean(routeItem.hidden),
    group_title: routeItem.group_title ?? null,
    page_id: routeItem.page_id ?? null,
    children: (routeItem.children ?? []).map(child => ({
      route: child.route,
      order: child.order,
      hidden: Boolean(child.hidden),
      page_id: child.page_id,
    })),
  }))
}

/**
 * 按当前数组顺序重建 order 字段，顶层与子级都按 10 递增。
 */
export function normalizeProjectRouteOrders(routeItems: ProjectRouteItemWrite[]): ProjectRouteItemWrite[] {
  return cloneProjectRoutes(routeItems).map((routeItem, routeIndex) => ({
    ...routeItem,
    order: (routeIndex + 1) * 10,
    children: (routeItem.children ?? []).map((child, childIndex) => ({
      ...child,
      order: (childIndex + 1) * 10,
    })),
  }))
}

/**
 * 根据页面信息推导默认路由片段，优先使用稳定的页面编码。
 */
export function buildPageRouteSlug(page: Pick<PageItem, 'id' | 'code' | 'title'>): string {
  const source = page.code || page.title
  const slug = source
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug || `page-${page.id}`
}

/**
 * 为同级节点生成不冲突的 route 字段。
 */
export function buildUniqueRoute(baseRoute: string, existingRoutes: string[]): string {
  const normalizedBaseRoute = baseRoute.trim() || 'route'
  if (!existingRoutes.includes(normalizedBaseRoute)) {
    return normalizedBaseRoute
  }
  let suffix = 2
  while (existingRoutes.includes(`${normalizedBaseRoute}-${suffix}`)) {
    suffix += 1
  }
  return `${normalizedBaseRoute}-${suffix}`
}

/**
 * 推导下一个顺序值，统一按 10 递增，给后续手动调整保留空隙。
 */
export function getNextOrder(existingOrders: number[]): number {
  if (existingOrders.length === 0) {
    return 10
  }
  return Math.max(...existingOrders) + 10
}

/**
 * 判断项目路由片段是否符合 Runtime 的单段相对路径约束。
 */
export function isValidProjectRouteSegment(route: string): boolean {
  return PROJECT_ROUTE_SEGMENT_PATTERN.test(route.trim())
}

/**
 * 向顶层路由追加一个页面节点，并自动补齐默认 route 与 order。
 */
export function appendRootPageRoute(
  routeItems: ProjectRouteItemWrite[],
  page: Pick<PageItem, 'id' | 'code' | 'title'>,
): ProjectRouteItemWrite[] {
  const nextRoutes = cloneProjectRoutes(routeItems)
  nextRoutes.push({
    route_type: 'page',
    route: buildUniqueRoute(buildPageRouteSlug(page), nextRoutes.map(item => item.route)),
    order: getNextOrder(nextRoutes.map(item => item.order)),
    hidden: false,
    page_id: page.id,
    children: [],
  })
  return normalizeProjectRouteOrders(nextRoutes)
}

/**
 * 校验项目路由草稿中的必填字段，返回所有错误消息。
 */
export function validateProjectRoutes(routeItems: ProjectRouteItemWrite[]): string[] {
  const errors: string[] = []

  routeItems.forEach((routeItem, routeIndex) => {
    const routeLabel = `第 ${routeIndex + 1} 个顶层节点`
    if (!routeItem.route.trim()) {
      errors.push(`${routeLabel} 的 Route 不能为空。`)
    } else if (!isValidProjectRouteSegment(routeItem.route)) {
      errors.push(`${routeLabel} 的 Route 只能使用单段相对片段，例如 home、chapter-1 或 PAGE_01，不能使用 /、/home、home/、a/b 或包含空格。`)
    }

    if (routeItem.route_type === 'group') {
      if (!(routeItem.group_title ?? '').trim()) {
        errors.push(`${routeLabel} 的分组标题不能为空。`)
      }
      ;(routeItem.children ?? []).forEach((childRoute, childIndex) => {
        const childLabel = `${routeLabel} 的第 ${childIndex + 1} 个子页`
        if (!childRoute.page_id) {
          errors.push(`${childLabel} 必须选择关联页面。`)
        }
        if (!childRoute.route.trim()) {
          errors.push(`${childLabel} 的 Route 不能为空。`)
        } else if (!isValidProjectRouteSegment(childRoute.route)) {
          errors.push(`${childLabel} 的 Route 只能使用单段相对片段，例如 home、chapter-1 或 PAGE_01，不能使用 /、/home、home/、a/b 或包含空格。`)
        }
      })
      return
    }

    if (!routeItem.page_id) {
      errors.push(`${routeLabel} 必须选择关联页面。`)
    }
  })

  return errors
}
