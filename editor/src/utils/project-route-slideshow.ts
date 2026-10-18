/**
 * 文件功能：封装页面结构的放映生效值、时长估算、节点选择、批量覆盖与页面池追加等纯逻辑。
 */
import type {
  EffectiveSlideshowSettings,
  PageItem,
  ProjectRouteChildWrite,
  ProjectRouteItemWrite,
  SlideshowAdvance,
  SlideshowSettings,
  SlideshowTransition,
} from '@/types/api'
import { formatMillisecondsAsSeconds } from '@/components/project/project-slideshow-values'
import {
  buildPageRouteSlug,
  buildUniqueRoute,
  cloneProjectRoutes,
  normalizeProjectRouteOrders,
} from '@/utils/project-route'

/** 页面结构中的节点范围。 */
export type RouteNodeScope = 'root' | 'child'

/** 页面结构表格的筛选模式。 */
export type RouteSlideshowFilter = 'all' | 'overridden' | 'hidden'

/** 通过索引定位一个路由节点。 */
export interface RouteNodeTarget {
  scope: RouteNodeScope
  routeIndex: number
  childIndex?: number
}

/** 查找结果，包含渲染和检查器需要的派生信息。 */
export interface RouteNodeSelection extends RouteNodeTarget {
  key: string
  item: ProjectRouteItemWrite | ProjectRouteChildWrite
  parentRoute: string | null
  fullPath: string
  routeType: 'group' | 'page'
}

/** 页面池和检查器共用的页面摘要。 */
export interface RoutePageMeta {
  id: number
  title: string
  code: string
}

/** 行内放映摘要。 */
export interface RouteSlideshowSummary {
  label: string
  overridden: boolean
  hidden: boolean
}

/** 可放映时长估算；手动页和媒体页单独计数，避免给出虚假精确值。 */
export interface RouteDurationEstimate {
  totalMs: number
  playablePageCount: number
  manualCount: number
  mediaCount: number
}

/** 页面结构顶部汇总。 */
export interface ProjectRouteSummary {
  pageCount: number
  groupCount: number
  hiddenCount: number
  overrideCount: number
  estimate: RouteDurationEstimate
}

/** 批量设置时对一组属性执行“保持 / 恢复继承 / 覆盖”。 */
export interface SlideshowBatchPatch {
  transition?: SlideshowTransition | null
  advance?: SlideshowAdvance | null
}

/** 允许检查器写入节点的字段集合。 */
export interface RouteNodePatch {
  route?: string
  hidden?: boolean
  page_id?: number | null
  group_title?: string | null
  transition?: SlideshowTransition | null
  advance?: SlideshowAdvance | null
}

/** 生成节点稳定键；键基于路由片段，拖动排序后仍可保持选中。 */
export function buildRouteNodeKey(target: RouteNodeTarget, routes: ProjectRouteItemWrite[]): string {
  const parent = routes[target.routeIndex]
  if (!parent) {
    return ''
  }
  if (target.scope === 'root') {
    return parent.route_type === 'group' ? `group:${parent.route}` : `page:${parent.route}`
  }
  const child = parent.children?.[target.childIndex ?? -1]
  return child ? `child:${parent.route}/${child.route}` : ''
}

/** 拼接父级与子级的完整访问路径。 */
export function getRouteFullPath(parentRoute: string | null, route: string): string {
  const normalizedRoute = String(route ?? '').trim().replace(/^\/+|\/+$/g, '')
  if (!normalizedRoute) {
    return parentRoute ? `/${parentRoute.replace(/^\/+|\/+$/g, '')}` : '/'
  }
  if (!parentRoute) {
    return `/${normalizedRoute}`
  }
  return `/${parentRoute.replace(/^\/+|\/+$/g, '')}/${normalizedRoute}`
}

/** 按节点键查找路由节点，并返回检查器需要的父子上下文。 */
export function findRouteNodeByKey(
  routes: ProjectRouteItemWrite[],
  key: string | null,
): RouteNodeSelection | null {
  if (!key) {
    return null
  }
  for (let routeIndex = 0; routeIndex < routes.length; routeIndex += 1) {
    const item = routes[routeIndex]
    const rootKey = item.route_type === 'group' ? `group:${item.route}` : `page:${item.route}`
    if (rootKey === key) {
      return {
        key,
        scope: 'root',
        routeIndex,
        item,
        parentRoute: null,
        fullPath: getRouteFullPath(null, item.route),
        routeType: item.route_type,
      }
    }
    if (item.route_type !== 'group') {
      continue
    }
    for (let childIndex = 0; childIndex < (item.children?.length ?? 0); childIndex += 1) {
      const child = item.children?.[childIndex]
      if (!child) {
        continue
      }
      if (`child:${item.route}/${child.route}` === key) {
        return {
          key,
          scope: 'child',
          routeIndex,
          childIndex,
          item: child,
          parentRoute: item.route,
          fullPath: getRouteFullPath(item.route, child.route),
          routeType: 'page',
        }
      }
    }
  }
  return null
}

/** 合并项目默认值与节点覆盖，得到只读生效值。 */
export function resolveEffectiveSlideshow(
  defaults: SlideshowSettings,
  transition: SlideshowTransition | null | undefined,
  advance: SlideshowAdvance | null | undefined,
): EffectiveSlideshowSettings {
  return {
    transition: transition ?? defaults.transition,
    advance: advance ?? defaults.advance,
  }
}

/** 判断节点是否至少覆盖了动画或翻页中的一组。 */
export function hasSlideshowOverride(
  item: Pick<ProjectRouteChildWrite, 'transition' | 'advance'>
    | Pick<ProjectRouteItemWrite, 'transition' | 'advance'>,
): boolean {
  return item.transition != null || item.advance != null
}

/** 生成表格行内的短摘要，例如“5s · 继承”“媒体结束 · 覆盖”。 */
export function formatRouteSlideshowSummary(
  item: ProjectRouteChildWrite | ProjectRouteItemWrite,
  defaults: SlideshowSettings,
): RouteSlideshowSummary {
  const effective = resolveEffectiveSlideshow(defaults, item.transition, item.advance)
  const timing = formatAdvanceTiming(effective.advance)
  const overridden = hasSlideshowOverride(item)
  return {
    label: overridden ? `${timing} · 覆盖` : `${timing} · 继承`,
    overridden,
    hidden: Boolean(item.hidden),
  }
}

/** 估算可见叶子页的播放时长；隐藏页和隐藏分组不参与。 */
export function estimateProjectRoutesDuration(
  routes: ProjectRouteItemWrite[],
  defaults: SlideshowSettings,
): RouteDurationEstimate {
  const estimate: RouteDurationEstimate = {
    totalMs: 0,
    playablePageCount: 0,
    manualCount: 0,
    mediaCount: 0,
  }
  const visitPage = (item: ProjectRouteChildWrite | ProjectRouteItemWrite): void => {
    const effective = resolveEffectiveSlideshow(defaults, item.transition, item.advance)
    estimate.totalMs += effective.transition.effect === 'none' ? 0 : effective.transition.duration_ms
    estimate.playablePageCount += 1
    if (effective.advance.mode === 'timer') {
      estimate.totalMs += effective.advance.delay_ms
      return
    }
    if (effective.advance.mode === 'media_end') {
      estimate.totalMs += effective.advance.delay_ms
      estimate.mediaCount += 1
      return
    }
    estimate.manualCount += 1
  }
  for (const item of routes) {
    if (item.hidden) {
      continue
    }
    if (item.route_type === 'group') {
      for (const child of item.children ?? []) {
        if (!child.hidden) {
          visitPage(child)
        }
      }
      continue
    }
    visitPage(item)
  }
  return estimate
}

/** 汇总顶部页数、分组、隐藏、覆盖和时长估算。 */
export function summarizeProjectRoutes(
  routes: ProjectRouteItemWrite[],
  defaults: SlideshowSettings,
): ProjectRouteSummary {
  let pageCount = 0
  let groupCount = 0
  let hiddenCount = 0
  let overrideCount = 0
  for (const item of routes) {
    if (item.route_type === 'group') {
      groupCount += 1
      if (item.hidden) {
        hiddenCount += 1
      }
      for (const child of item.children ?? []) {
        pageCount += 1
        if (child.hidden) {
          hiddenCount += 1
        }
        if (hasSlideshowOverride(child)) {
          overrideCount += 1
        }
      }
      continue
    }
    pageCount += 1
    if (item.hidden) {
      hiddenCount += 1
    }
    if (hasSlideshowOverride(item)) {
      overrideCount += 1
    }
  }
  return {
    pageCount,
    groupCount,
    hiddenCount,
    overrideCount,
    estimate: estimateProjectRoutesDuration(routes, defaults),
  }
}

/** 把毫秒数格式化为“X 秒”“X 分 Y 秒”或“X 小时 Y 分”。 */
export function formatDurationMs(totalMs: number): string {
  const totalSeconds = Math.max(0, Math.round(totalMs / 1000))
  if (totalSeconds < 60) {
    return `${totalSeconds} 秒`
  }
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes < 60) {
    return seconds === 0 ? `${minutes} 分` : `${minutes} 分 ${seconds} 秒`
  }
  const hours = Math.floor(minutes / 60)
  const restMinutes = minutes % 60
  return restMinutes === 0 ? `${hours} 小时` : `${hours} 小时 ${restMinutes} 分`
}

/** 展开选中的分组，返回去重后的叶子节点键。 */
export function collectLeafKeysForTargets(
  routes: ProjectRouteItemWrite[],
  keys: Iterable<string>,
): string[] {
  const keySet = new Set(keys)
  const result: string[] = []
  const pushUnique = (key: string): void => {
    if (!result.includes(key)) {
      result.push(key)
    }
  }
  for (const item of routes) {
    const rootKey = item.route_type === 'group' ? `group:${item.route}` : `page:${item.route}`
    if (item.route_type === 'group') {
      const children = item.children ?? []
      if (keySet.has(rootKey)) {
        children.forEach(child => pushUnique(`child:${item.route}/${child.route}`))
      }
      children.forEach(child => {
        const childKey = `child:${item.route}/${child.route}`
        if (keySet.has(childKey)) {
          pushUnique(childKey)
        }
      })
      continue
    }
    if (keySet.has(rootKey)) {
      pushUnique(rootKey)
    }
  }
  return result
}

/** 统计选中节点展开后的叶子页数量。 */
export function countSelectedPages(routes: ProjectRouteItemWrite[], keys: Iterable<string>): number {
  return collectLeafKeysForTargets(routes, keys).length
}

/** 把放映覆盖批量写入选中的叶子页；未出现在 patch 中的组保持不变。 */
export function applySlideshowToKeys(
  routes: ProjectRouteItemWrite[],
  keys: Iterable<string>,
  patch: SlideshowBatchPatch,
): ProjectRouteItemWrite[] {
  const leafKeys = new Set(collectLeafKeysForTargets(routes, keys))
  const next = cloneProjectRoutes(routes)
  const applyNode = (item: ProjectRouteItemWrite | ProjectRouteChildWrite): void => {
    if ('transition' in patch) {
      item.transition = patch.transition ?? null
    }
    if ('advance' in patch) {
      item.advance = patch.advance ?? null
    }
  }
  for (const item of next) {
    const rootKey = item.route_type === 'group' ? `group:${item.route}` : `page:${item.route}`
    if (item.route_type === 'page' && leafKeys.has(rootKey)) {
      applyNode(item)
    }
    for (const child of item.children ?? []) {
      if (leafKeys.has(`child:${item.route}/${child.route}`)) {
        applyNode(child)
      }
    }
  }
  return next
}

/** 向页面池的目标位置追加页面；返回新草稿和可立即选中的节点键。 */
export function appendPageToTarget(
  routes: ProjectRouteItemWrite[],
  page: Pick<PageItem, 'id' | 'code' | 'title'>,
  targetKey: string,
): { routes: ProjectRouteItemWrite[]; key: string } {
  const next = cloneProjectRoutes(routes)
  if (targetKey === 'root') {
    const route = buildUniqueRoute(buildPageRouteSlug(page), next.map(item => item.route))
    next.push({
      route_type: 'page',
      route,
      order: 0,
      hidden: false,
      page_id: page.id,
      children: [],
    })
    return {
      routes: normalizeProjectRouteOrders(next),
      key: `page:${route}`,
    }
  }

  const groupRoute = targetKey.startsWith('group:') ? targetKey.slice('group:'.length) : ''
  const group = next.find(item => item.route_type === 'group' && item.route === groupRoute)
  if (!group) {
    return { routes: normalizeProjectRouteOrders(next), key: '' }
  }
  const children = [...(group.children ?? [])]
  const childRoute = buildUniqueRoute(buildPageRouteSlug(page), children.map(child => child.route))
  children.push({
    route: childRoute,
    order: 0,
    hidden: false,
    page_id: page.id,
  })
  group.children = children
  return {
    routes: normalizeProjectRouteOrders(next),
    key: `child:${groupRoute}/${childRoute}`,
  }
}

/** 追加一个顶层分组；返回新草稿和可立即选中的节点键。 */
export function appendGroup(routes: ProjectRouteItemWrite[]): { routes: ProjectRouteItemWrite[]; key: string } {
  const next = cloneProjectRoutes(routes)
  const route = buildUniqueRoute('group', next.map(item => item.route))
  next.push({
    route_type: 'group',
    route,
    order: 0,
    hidden: false,
    group_title: '新分组',
    children: [],
  })
  return {
    routes: normalizeProjectRouteOrders(next),
    key: `group:${route}`,
  }
}

/** 更新指定节点的可写字段，并按节点类型过滤非法字段。 */
export function updateRouteNode(
  routes: ProjectRouteItemWrite[],
  key: string,
  patch: RouteNodePatch,
): ProjectRouteItemWrite[] {
  const next = cloneProjectRoutes(routes)
  for (let routeIndex = 0; routeIndex < next.length; routeIndex += 1) {
    const item = next[routeIndex]
    const rootKey = item.route_type === 'group' ? `group:${item.route}` : `page:${item.route}`
    if (rootKey === key) {
      next[routeIndex] = applyRootPatch(item, patch)
      return normalizeProjectRouteOrders(next)
    }
    if (item.route_type !== 'group') {
      continue
    }
    const children = [...(item.children ?? [])]
    for (let childIndex = 0; childIndex < children.length; childIndex += 1) {
      const child = children[childIndex]
      if (`child:${item.route}/${child.route}` !== key) {
        continue
      }
      children[childIndex] = applyChildPatch(child, patch)
      item.children = children
      return normalizeProjectRouteOrders(next)
    }
  }
  return next
}

/** 删除指定节点；删除分组时会一并移除其子页。 */
export function removeRouteNode(routes: ProjectRouteItemWrite[], key: string): ProjectRouteItemWrite[] {
  const next = cloneProjectRoutes(routes)
  for (let routeIndex = 0; routeIndex < next.length; routeIndex += 1) {
    const item = next[routeIndex]
    const rootKey = item.route_type === 'group' ? `group:${item.route}` : `page:${item.route}`
    if (rootKey === key) {
      next.splice(routeIndex, 1)
      return normalizeProjectRouteOrders(next)
    }
    if (item.route_type !== 'group') {
      continue
    }
    const children = [...(item.children ?? [])]
    const childIndex = children.findIndex(child => `child:${item.route}/${child.route}` === key)
    if (childIndex >= 0) {
      children.splice(childIndex, 1)
      item.children = children
      return normalizeProjectRouteOrders(next)
    }
  }
  return next
}

/** 计算可见叶子页在放映序列中的序号；隐藏页和隐藏分组不占序号。 */
export function getRouteSequenceNumber(routes: ProjectRouteItemWrite[], key: string): number | null {
  let sequence = 0
  for (const item of routes) {
    if (item.hidden) {
      continue
    }
    if (item.route_type === 'group') {
      for (const child of item.children ?? []) {
        if (child.hidden) {
          continue
        }
        sequence += 1
        if (`child:${item.route}/${child.route}` === key) {
          return sequence
        }
      }
      continue
    }
    sequence += 1
    if (`page:${item.route}` === key) {
      return sequence
    }
  }
  return null
}

/** 按节点类型应用顶层字段，避免把子页字段写进分组。 */
function applyRootPatch(item: ProjectRouteItemWrite, patch: RouteNodePatch): ProjectRouteItemWrite {
  const next: ProjectRouteItemWrite = { ...item }
  if ('route' in patch && patch.route !== undefined) {
    next.route = patch.route
  }
  if ('hidden' in patch && patch.hidden !== undefined) {
    next.hidden = patch.hidden
  }
  if (item.route_type === 'group') {
    if ('group_title' in patch) {
      next.group_title = patch.group_title ?? null
    }
    return next
  }
  if ('page_id' in patch) {
    next.page_id = patch.page_id ?? null
  }
  if ('transition' in patch) {
    next.transition = patch.transition ?? null
  }
  if ('advance' in patch) {
    next.advance = patch.advance ?? null
  }
  return next
}

/** 子页只允许页面、路径、显示和放映覆盖字段。 */
function applyChildPatch(item: ProjectRouteChildWrite, patch: RouteNodePatch): ProjectRouteChildWrite {
  const next: ProjectRouteChildWrite = { ...item }
  if ('route' in patch && patch.route !== undefined) {
    next.route = patch.route
  }
  if ('hidden' in patch && patch.hidden !== undefined) {
    next.hidden = patch.hidden
  }
  if ('page_id' in patch && patch.page_id != null) {
    next.page_id = patch.page_id
  }
  if ('transition' in patch) {
    next.transition = patch.transition ?? null
  }
  if ('advance' in patch) {
    next.advance = patch.advance ?? null
  }
  return next
}

/** 把翻页设置压缩成行内摘要文本。 */
function formatAdvanceTiming(advance: SlideshowAdvance): string {
  if (advance.mode === 'manual') {
    return '手动'
  }
  if (advance.mode === 'media_end') {
    return '媒体结束'
  }
  return `${formatMillisecondsAsSeconds(advance.delay_ms)}s`
}
