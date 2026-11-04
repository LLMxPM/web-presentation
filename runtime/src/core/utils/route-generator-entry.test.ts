// @vitest-environment jsdom

/**
 * 文件用途：用真实 artifact 路由配置验证目录项携带组件路径，并让单页 module 入口反查到与放映一致的页码。
 */

import { afterEach, describe, expect, it } from 'vitest'

import { setRuntimePreloadedConfig } from './path'

const ARTIFACT_ROUTE_CONFIG = {
  app: {
    app: { icon: 'slider', title: '页码反查项目', description: '测试描述', page: { width: 1920, height: 1080, baseFontSize: '16px' } },
  },
  routes: {
    routes: [
      { route: 'cover', component: '@/views/PG001.vue', meta: { title: '封面', order: 0, hidden: false } },
      {
        route: 'chapter',
        meta: { title: '章节', order: 1 },
        children: [
          { route: 'overview', component: '@/views/PG002.vue', meta: { title: '概览', order: 0, hidden: false } },
          { route: 'draft', component: '@/views/PG004.vue', meta: { title: '草稿', order: 1, hidden: true } },
        ],
      },
      { route: 'end', component: 'src/views/PG003.vue', meta: { title: '结束页', order: 2, hidden: false } },
    ],
  },
  icons: { static_icons: [] },
}

/**
 * 把 artifact 路由分段装载进配置状态，模拟预览宿主的预加载上下文。
 */
async function loadArtifactRoutes() {
  setRuntimePreloadedConfig(ARTIFACT_ROUTE_CONFIG)
  const { loadRouteConfig } = await import('./config')
  await loadRouteConfig(true)
  return import('./route-generator')
}

afterEach(() => {
  setRuntimePreloadedConfig(undefined)
})

describe('route generator module entry page number', () => {
  it('目录项的 component 是路由配置里的真实组件路径', async () => {
    const { getAllRouteInfos } = await loadArtifactRoutes()

    expect(Object.fromEntries(getAllRouteInfos().map(info => [info.path, info.component]))).toEqual({
      '/cover': '@/views/PG001.vue',
      '/chapter/overview': '@/views/PG002.vue',
      '/chapter/draft': '@/views/PG004.vue',
      '/end': 'src/views/PG003.vue',
    })
  })

  it('放映路径按目录命中页码，单页 module 入口靠反查得到同一套页码', async () => {
    const { getPageNumberByModuleEntryPath, getPageNumberByPath } = await loadArtifactRoutes()

    expect(getPageNumberByPath('/chapter/overview')).toBe(2)
    // module 入口不会命中目录 path，反查前拿不到页码。
    expect(getPageNumberByPath('/src/views/PG002.vue')).toBeUndefined()
    expect(getPageNumberByModuleEntryPath('/src/views/PG002.vue')).toBe(2)
    expect(getPageNumberByModuleEntryPath('/src/views/PG001.vue')).toBe(1)
    // 组件路径写成 src/ 前缀也归一到同一入口。
    expect(getPageNumberByModuleEntryPath('/src/views/PG003.vue')).toBe(3)
  })

  it('隐藏路由与未挂路由的页面模块都反查不到页码', async () => {
    const { getPageNumberByModuleEntryPath, getRouteInfosSortedByPageNumber } = await loadArtifactRoutes()

    expect(getPageNumberByModuleEntryPath('/src/views/PG004.vue')).toBeUndefined()
    expect(getPageNumberByModuleEntryPath('/src/views/PG999.vue')).toBeUndefined()
    expect(getRouteInfosSortedByPageNumber().map(info => info.pageNumber)).toEqual([1, 2, 3])
  })
})
