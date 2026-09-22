/**
 * 文件用途：创建项目演示路由，供普通 Runtime 与 Backend build release 共享。
 */

import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

import { installRuntimeNavigation } from './runtime-session'

import { generateRoutes } from '@/core/utils/route-generator'
import { getDefaultRouteConfigAsync, getRouteConfigsAsync, loadAppConfig } from '@/core/utils/config'

export interface ProjectRouterOptions {
  extraRoutes?: RouteRecordRaw[]
}

/**
 * 解析浏览器标签页标题。
 * @param title 应用配置中的项目名称
 * @returns 去除首尾空白后的项目名称
 */
function resolveBrowserTitle(title: string): string {
  return title.trim()
}

/**
 * 将浏览器标签页标题同步为固定项目名称。
 * @param title 需要展示的项目名称
 */
function syncBrowserTitle(title: string): void {
  if (!title || typeof document === 'undefined') {
    return
  }

  document.title = title
}

/**
 * 异步创建项目路由器。
 * @param options 额外宿主路由配置
 * @returns Vue Router 实例
 */
export async function createProjectRouter(options: ProjectRouterOptions = {}) {
  const [projectAppConfig, routeConfigs, defaultRouteConfig] = await Promise.all([
    loadAppConfig(),
    getRouteConfigsAsync(),
    getDefaultRouteConfigAsync(),
  ])
  const browserTitle = resolveBrowserTitle(projectAppConfig.app.title)
  const generatedRoutes = generateRoutes(routeConfigs)

  const internalPresenterRoutes: RouteRecordRaw[] = [
    {
      path: '/__presenter',
      name: 'RuntimePresenterConsole',
      redirect: to => ({ path: String(to.query.route || '/'), query: { ...to.query, route: undefined, runtimeMode: 'presenter' } }),
      meta: { title: '演讲者控制台', hidden: true },
    },
    {
      path: '/__presenter-display',
      name: 'RuntimePresenterDisplay',
      redirect: to => ({ path: String(to.query.route || '/'), query: { ...to.query, route: undefined, runtimeMode: 'display' } }),
      meta: { title: '演讲展示窗口', hidden: true },
    },
  ]

  const routes: RouteRecordRaw[] = [
    ...internalPresenterRoutes,
    ...(options.extraRoutes || []),
    {
      path: '/',
      component: () => import('@/runtime-shell/layouts/RuntimeProjectShell.vue'),
      meta: { runtimeProject: true },
      children: [
        ...defaultRouteConfig,
        ...generatedRoutes,
      ],
    },
  ]

  const router = createRouter({
    history: createWebHashHistory(),
    routes,
    scrollBehavior(_to, _from, savedPosition) {
      if (savedPosition) {
        return savedPosition
      }
      return { top: 0 }
    },
  })

  installRuntimeNavigation(router)
  syncBrowserTitle(browserTitle)

  router.afterEach(() => {
    syncBrowserTitle(browserTitle)
  })

  return router
}
