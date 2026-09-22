// @vitest-environment jsdom
/** 文件功能：验证页内导航保持模式、显式模式切换和浏览器历史语义。 */
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import { getRuntimeSession, installRuntimeNavigation, switchRuntimeMode } from './runtime-session'

/** 创建带项目与专用预览入口的最小路由器。 */
function makeRouter() {
  const component = defineComponent({ template: '<div />' })
  const router = createRouter({ history: createMemoryHistory(), routes: [
    ...['/a', '/b', '/c'].map(path => ({ path, component, meta: { runtimeProject: true } })),
    { path: '/__component-preview', component },
  ] })
  installRuntimeNavigation(router)
  return router
}

describe('Runtime 页面与模式导航', () => {
  it('兼容直接 push，保留演讲频道但不传播页面业务参数', async () => {
    const router = makeRouter()
    await router.push('/a?runtimeMode=presenter&channel=test&filter=old')
    await router.push('/b?filter=new')
    expect(router.currentRoute.value.query).toEqual({ runtimeMode: 'presenter', channel: 'test', filter: 'new' })
    await switchRuntimeMode(router, 'normal')
    expect(router.currentRoute.value.path).toBe('/b')
    expect(router.currentRoute.value.query).toEqual({ runtimeMode: 'normal', filter: 'new' })
  })

  it('卡片选页保持模式，后退恢复页面及显式模式', async () => {
    const router = makeRouter()
    await router.push('/a?runtimeMode=normal')
    await switchRuntimeMode(router, 'cards')
    await router.push('/b')
    expect(getRuntimeSession(router).mode.value).toBe('cards')
    const completed = new Promise<void>(resolve => { const stop = router.afterEach(() => { stop(); resolve() }) })
    router.back()
    await completed
    expect(router.currentRoute.value.fullPath).toBe('/a?runtimeMode=cards')
  })

  it('深链接恢复模式，非法模式降级，专用预览不带项目模式', async () => {
    const router = makeRouter()
    await router.push('/b?runtimeMode=display&channel=existing')
    expect(getRuntimeSession(router).mode.value).toBe('display')
    await router.push('/c?runtimeMode=unknown')
    expect(router.currentRoute.value.query.runtimeMode).toBe('normal')
    await router.push('/__component-preview')
    expect(router.currentRoute.value.query).toEqual({})
  })
})
