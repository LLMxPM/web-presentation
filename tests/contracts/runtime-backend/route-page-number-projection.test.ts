/**
 * 文件功能：校验 Runtime 页码分配与 Backend 复算的截图身份投影完全一致。
 *
 * 两侧共用同一份 fixture：Runtime 侧直接调用 page-numbers.ts 的纯函数，
 * Backend 侧在 pytest 中读取同一文件。任何一侧规则漂移都会让其中一端失败。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  buildRouteCatalogProjection,
  type RouteNumberingNode,
} from '../../../runtime/src/core/utils/page-numbers'

interface ExpectedCase {
  name: string
  routes: RouteNumberingNode[]
  expected: {
    catalog: Array<Record<string, unknown>>
    totalPages: number
    minPageNumber: number
  }
}

const fixture = JSON.parse(
  readFileSync(resolve(process.cwd(), 'tests/fixtures/route-page-number-cases.json'), 'utf-8'),
) as { schema_version: number; cases: ExpectedCase[] }

describe('runtime-backend route page number projection', () => {
  it('fixture 结构版本应为 1 且用例非空', () => {
    expect(fixture.schema_version).toBe(1)
    expect(fixture.cases.length).toBeGreaterThan(0)
  })

  for (const testCase of fixture.cases) {
    it(`应与 Backend 复算结果一致：${testCase.name}`, () => {
      expect(buildRouteCatalogProjection(testCase.routes)).toEqual(testCase.expected)
    })
  }

  it('分配页码不得修改入参', () => {
    const routes = fixture.cases[0].routes
    const snapshot = JSON.parse(JSON.stringify(routes))
    buildRouteCatalogProjection(routes)
    expect(routes).toEqual(snapshot)
  })

  it('放映字段变化不得改变目录投影', () => {
    const base = [
      { route: 'a', meta: { title: 'A', order: 0, hidden: false } },
    ] as RouteNumberingNode[]
    const withPlayback = [
      {
        route: 'a',
        component: '@/views/a.vue',
        meta: {
          title: 'A',
          order: 0,
          hidden: false,
          speakerNotes: '备注',
          transition: { effect: 'push', durationMs: 800 },
          advance: { mode: 'media_end', delayMs: 1000, mediaTimeoutMs: 60000 },
        },
      },
    ] as RouteNumberingNode[]
    expect(buildRouteCatalogProjection(withPlayback)).toEqual(buildRouteCatalogProjection(base))
  })

  it('调整 order 必须改变投影：order 与 pageNumber 都能被页面目录读到', () => {
    const before = buildRouteCatalogProjection([
      { route: 'a', meta: { title: 'A', order: 0, hidden: false } },
      { route: 'b', meta: { title: 'B', order: 1, hidden: false } },
      { route: 'c', meta: { title: 'C', order: 2, hidden: false } },
    ] as RouteNumberingNode[])
    const movedOrder = buildRouteCatalogProjection([
      { route: 'a', meta: { title: 'A', order: 0, hidden: false } },
      { route: 'b', meta: { title: 'B', order: 1, hidden: false } },
      { route: 'c', meta: { title: 'C', order: 5, hidden: false } },
    ] as RouteNumberingNode[])
    expect(movedOrder).not.toEqual(before)
  })

  it('仅在末尾追加页面时，既有条目页码不变但仍新增目录项', () => {
    const before = buildRouteCatalogProjection([
      { route: 'a', meta: { title: 'A', order: 0, hidden: false } },
      { route: 'b', meta: { title: 'B', order: 1, hidden: false } },
    ] as RouteNumberingNode[])
    const appended = buildRouteCatalogProjection([
      { route: 'a', meta: { title: 'A', order: 0, hidden: false } },
      { route: 'b', meta: { title: 'B', order: 1, hidden: false } },
      { route: 'c', meta: { title: 'C', order: 2, hidden: false } },
    ] as RouteNumberingNode[])
    expect(appended.catalog.slice(0, 2)).toEqual(before.catalog)
    expect(appended.totalPages).toBe(before.totalPages + 1)
  })
})
