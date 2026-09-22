/** 文件功能：规范项目页面导航与展示模式，保留页内链接的 Runtime 上下文。 */
import { computed, ref } from 'vue'
import type { Router, RouteLocationNormalized, LocationQueryRaw } from 'vue-router'

export type RuntimeMode = 'normal' | 'cards' | 'presenter' | 'display'
const modes: RuntimeMode[] = ['normal', 'cards', 'presenter', 'display']
const sessions = new WeakMap<Router, ReturnType<typeof createSession>>()

/** 解析合法模式；非法值回到普通模式。 */
export function resolveRuntimeMode(value: unknown): RuntimeMode {
  return modes.includes(value as RuntimeMode) ? value as RuntimeMode : 'normal'
}

/** 创建与路由器同生命周期的界面状态，不依赖页面或布局的挂载。 */
function createSession(router: Router) {
  return {
    mode: computed(() => resolveRuntimeMode(router.currentRoute.value.query.runtimeMode)),
    navigationError: ref(''),
    requestedPath: ref(''),
    collapsed: ref(false),
    bottomCollapsed: ref(false),
    suppressTransition: ref(false),
  }
}

/** 获取项目会话；每个应用/捕获窗口使用独立实例。 */
export function getRuntimeSession(router: Router) {
  let session = sessions.get(router)
  if (!session) {
    session = createSession(router)
    sessions.set(router, session)
  }
  return session
}

/** 显式切换模式，保留页面及业务参数；退出演讲时清除频道。 */
export function switchRuntimeMode(router: Router, mode: RuntimeMode, extra: LocationQueryRaw = {}) {
  const query: LocationQueryRaw = { ...router.currentRoute.value.query, ...extra, runtimeMode: mode }
  if (mode === 'normal' || mode === 'cards') {
    delete query.channel
    delete query.displayBlocked
  }
  return router.push({ path: router.currentRoute.value.path, query })
}

/** 提交页面导航并立即记录意图，使模块加载期间的连续翻页能够累计。 */
export async function navigateRuntimePage(router: Router, path: string): Promise<void> {
  const session = getRuntimeSession(router)
  session.requestedPath.value = path
  try { await router.push(path) } finally {
    if (session.requestedPath.value === path) session.requestedPath.value = ''
  }
}

/** 安装页内链接兼容层；专用预览入口不参与模式路由。 */
export function installRuntimeNavigation(router: Router): void {
  const session = getRuntimeSession(router)
  router.onError((error, to) => {
    console.error('[runtime-navigation] 页面加载失败', error)
    session.navigationError.value = '页面加载失败，请重试或选择其他页面。'
    if (session.requestedPath.value === to.path) session.requestedPath.value = ''
  })
  router.afterEach((to, _from, failure) => {
    if (!failure) session.navigationError.value = ''
    if (session.requestedPath.value === to.path) session.requestedPath.value = ''
  })
  router.beforeEach((to, from) => {
    if (!to.matched.some(record => record.meta.runtimeProject)) return
    session.requestedPath.value = to.path
    const explicit = to.query.runtimeMode !== undefined
    const mode = resolveRuntimeMode(explicit ? to.query.runtimeMode : from.query.runtimeMode)
    const query: LocationQueryRaw = { ...to.query, runtimeMode: mode }
    if (mode === 'presenter' || mode === 'display') {
      query.channel = to.query.channel || from.query.channel || createChannelId()
    } else {
      delete query.channel
      delete query.displayBlocked
    }
    if (!sameQuery(to, query)) return { path: to.path, hash: to.hash, query }
  })
}

/** 比较规范化参数，避免导航守卫循环。 */
function sameQuery(to: RouteLocationNormalized, query: LocationQueryRaw): boolean {
  return JSON.stringify(to.query) === JSON.stringify(query)
}

/** 地址缺少频道时创建会话标识，不自动打开新窗口。 */
function createChannelId(): string {
  return globalThis.crypto?.randomUUID?.() || `runtime-${Date.now()}-${Math.random().toString(36).slice(2)}`
}
