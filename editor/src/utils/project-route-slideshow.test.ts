/**
 * 文件功能：验证页面结构放映生效值、时长估算、批量覆盖与页面池追加等纯逻辑。
 */
import { describe, expect, it } from 'vitest'

import type {
  ProjectRouteItemWrite,
  SlideshowSettings,
} from '@/types/api'
import {
  appendGroup,
  appendPageToTarget,
  applySlideshowToKeys,
  buildRouteNodeKey,
  collectLeafKeysForTargets,
  estimateProjectRoutesDuration,
  findRouteNodeByKey,
  formatDurationMs,
  formatRouteSlideshowSummary,
  getRouteFullPath,
  getRouteSequenceNumber,
  removeRouteNode,
  resolveEffectiveSlideshow,
  summarizeProjectRoutes,
  updateRouteNode,
} from '@/utils/project-route-slideshow'

const defaults: SlideshowSettings = {
  transition: { effect: 'fade', duration_ms: 400 },
  advance: { mode: 'timer', delay_ms: 5000, media_timeout_ms: 300000 },
  loop: false,
  auto_start: false,
}

const manualDefaults: SlideshowSettings = {
  ...defaults,
  advance: { mode: 'manual', delay_ms: 5000, media_timeout_ms: 300000 },
}

/** 构造一个最小路由树，覆盖顶层页面、分组与子页。 */
function buildRoutes(): ProjectRouteItemWrite[] {
  return [
    {
      route_type: 'page',
      route: 'cover',
      order: 10,
      hidden: false,
      page_id: 1,
      children: [],
    },
    {
      route_type: 'group',
      route: 'chapter',
      order: 20,
      hidden: false,
      group_title: '章节',
      page_id: null,
      children: [
        {
          route: 'intro',
          order: 10,
          hidden: false,
          page_id: 2,
          transition: { effect: 'push', duration_ms: 500 },
        },
        {
          route: 'hidden-child',
          order: 20,
          hidden: true,
          page_id: 3,
        },
      ],
    },
    {
      route_type: 'page',
      route: 'hidden-page',
      order: 30,
      hidden: true,
      page_id: 4,
      children: [],
    },
    {
      route_type: 'page',
      route: 'end',
      order: 40,
      hidden: false,
      page_id: 5,
      advance: { mode: 'media_end', delay_ms: 6000, media_timeout_ms: 120000 },
      children: [],
    },
  ]
}

describe('project-route-slideshow', () => {
  it('应优先使用节点覆盖，否则继承项目默认值', () => {
    const inherited = resolveEffectiveSlideshow(defaults, null, null)
    expect(inherited).toEqual({
      transition: defaults.transition,
      advance: defaults.advance,
    })

    const overridden = resolveEffectiveSlideshow(
      defaults,
      { effect: 'push', duration_ms: 600 },
      null,
    )
    expect(overridden.transition).toEqual({ effect: 'push', duration_ms: 600 })
    expect(overridden.advance).toEqual(defaults.advance)
  })

  it('行内摘要应区分继承、覆盖与媒体结束', () => {
    expect(formatRouteSlideshowSummary({ hidden: false, transition: null, advance: null }, defaults).label)
      .toBe('5s · 继承')
    expect(formatRouteSlideshowSummary({
      hidden: false,
      transition: { effect: 'push', duration_ms: 600 },
      advance: { mode: 'timer', delay_ms: 8000 },
    }, defaults).label).toBe('8s · 覆盖')
    expect(formatRouteSlideshowSummary({
      hidden: false,
      transition: null,
      advance: { mode: 'media_end', delay_ms: 6000, media_timeout_ms: 120000 },
    }, defaults).label).toBe('媒体结束 · 覆盖')
  })

  it('时长估算应跳过隐藏页和隐藏分组，并单独统计手动页与媒体页', () => {
    const estimate = estimateProjectRoutesDuration(buildRoutes(), defaults)
    expect(estimate.playablePageCount).toBe(3)
    expect(estimate.manualCount).toBe(0)
    expect(estimate.mediaCount).toBe(1)
    expect(estimate.totalMs).toBe(400 + 5000 + 500 + 5000 + 400 + 6000)
  })

  it('手动页应只计动画时长并计入手动页数量', () => {
    const routes = buildRoutes().map(item => ({
      ...item,
      transition: null,
      advance: null,
      children: item.children?.map(child => ({ ...child, transition: null, advance: null })),
    }))
    const estimate = estimateProjectRoutesDuration(routes, manualDefaults)
    expect(estimate.manualCount).toBe(3)
    expect(estimate.mediaCount).toBe(0)
    expect(estimate.totalMs).toBe(400 + 400 + 400)
  })

  it('汇总应包含隐藏节点，并统计覆盖数量', () => {
    const summary = summarizeProjectRoutes(buildRoutes(), defaults)
    expect(summary.pageCount).toBe(5)
    expect(summary.groupCount).toBe(1)
    expect(summary.hiddenCount).toBe(2)
    expect(summary.overrideCount).toBe(2)
    expect(summary.estimate.playablePageCount).toBe(3)
  })

  it('分页时长应格式化为分钟和小时', () => {
    expect(formatDurationMs(9300)).toBe('9 秒')
    expect(formatDurationMs(125000)).toBe('2 分 5 秒')
    expect(formatDurationMs(3_600_000)).toBe('1 小时')
  })

  it('页面池追加到顶层和分组时应生成唯一 Route 并返回选中键', () => {
    const rootResult = appendPageToTarget(buildRoutes(), { id: 9, code: 'Cover', title: '封面副本' }, 'root')
    expect(rootResult.key).toBe('page:cover-2')
    expect(rootResult.routes.at(-1)).toMatchObject({ route: 'cover-2', page_id: 9, order: 50 })

    const childResult = appendPageToTarget(buildRoutes(), { id: 10, code: 'Intro', title: '章节副本' }, 'group:chapter')
    expect(childResult.key).toBe('child:chapter/intro-2')
    expect(childResult.routes[1].children?.at(-1)).toMatchObject({ route: 'intro-2', page_id: 10, order: 30 })
  })

  it('追加分组应返回可立即选中的键', () => {
    const result = appendGroup(buildRoutes())
    expect(result.key).toBe('group:group')
    expect(result.routes.at(-1)).toMatchObject({ route_type: 'group', group_title: '新分组' })
  })

  it('选中分组时应展开为子页并只写入 patch 中出现的属性', () => {
    const routes = buildRoutes()
    const keys = collectLeafKeysForTargets(routes, ['group:chapter'])
    expect(keys).toEqual(['child:chapter/intro', 'child:chapter/hidden-child'])

    const next = applySlideshowToKeys(routes, ['group:chapter'], {
      transition: { effect: 'none', duration_ms: 0 },
    })
    expect(next[1].children?.[0].transition).toEqual({ effect: 'none', duration_ms: 0 })
    expect(next[1].children?.[0].advance).toBeNull()
    expect(next[1].children?.[1].transition).toEqual({ effect: 'none', duration_ms: 0 })
    expect(next[0].transition).toBeNull()
  })

  it('显式 null 应恢复继承，且不影响未选中的页面', () => {
    const routes = [
      {
        ...buildRoutes()[0],
        transition: { effect: 'push' as const, duration_ms: 600 },
      },
    ]
    const next = applySlideshowToKeys(routes, ['page:cover'], { transition: null })
    expect(next[0].transition).toBeNull()
  })

  it('更新分组不应写入放映字段，更新子页不应写入分组标题', () => {
    const routes = buildRoutes()
    const groupUpdated = updateRouteNode(routes, 'group:chapter', {
      group_title: '新章节',
      transition: { effect: 'push', duration_ms: 600 },
    })
    expect(groupUpdated[1].group_title).toBe('新章节')
    expect(groupUpdated[1].transition).toBeNull()

    const childUpdated = updateRouteNode(routes, 'child:chapter/intro', {
      group_title: '不应写入',
      page_id: 11,
    })
    const child = childUpdated[1].children?.[0]
    expect(child?.page_id).toBe(11)
    expect(child && 'group_title' in child).toBe(false)
  })

  it('删除与选中键应保持稳定', () => {
    const routes = buildRoutes()
    const removedChild = removeRouteNode(routes, 'child:chapter/intro')
    expect(removedChild[1].children).toHaveLength(1)

    const removedGroup = removeRouteNode(routes, 'group:chapter')
    expect(removedGroup).toHaveLength(3)

    expect(getRouteSequenceNumber(routes, 'page:cover')).toBe(1)
    expect(getRouteSequenceNumber(routes, 'child:chapter/intro')).toBe(2)
    expect(getRouteSequenceNumber(routes, 'page:hidden-page')).toBeNull()
    expect(getRouteSequenceNumber(routes, 'page:end')).toBe(3)
  })

  it('节点键在拖动排序后仍应指向同一路由', () => {
    const routes = buildRoutes()
    const key = buildRouteNodeKey({ scope: 'root', routeIndex: 0 }, routes)
    const reordered = [...routes].reverse()
    expect(findRouteNodeByKey(reordered, key)?.item.route).toBe('cover')
  })

  it('完整路径应兼容顶层与子页', () => {
    expect(getRouteFullPath(null, 'cover')).toBe('/cover')
    expect(getRouteFullPath('chapter', 'intro')).toBe('/chapter/intro')
    expect(getRouteFullPath(null, '/cover/')).toBe('/cover')
  })
})
