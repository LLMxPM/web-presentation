/** 文件功能：验证构建发布入口的静态资源等待、逐页回执更新与迟到结果隔离。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref, type App } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import type { UseStaticPresentationOptions } from '@/runtime-kit/public/composables/static/useStaticPresentation.v1'

const state = vi.hoisted(() => ({ router: null as Router | null }))
vi.mock('./core/router/project-router', () => ({ createProjectRouter: async () => state.router }))
vi.mock('./core/composables/useTheme', async () => {
  const { ref } = await import('vue')
  return {
    loadThemeConfigs: async () => {},
    useTheme: () => ({ themeClass: ref(''), themeStyles: ref({}) }),
  }
})
vi.mock('./core/utils/config', () => ({ initializeConfig: async () => {} }))
vi.mock('./core/utils/static-icons', () => ({ initializeStaticIcons: () => {} }))
vi.mock('./core/utils/favicon', () => ({ initializeRuntimeFaviconSync: () => {} }))
vi.mock('./core/utils/font-registry', () => ({
  initializeRuntimeFontRegistry: () => {},
  waitForRequiredPlatformFonts: async () => {},
}))

interface PageFixture {
  mode?: UseStaticPresentationOptions['mode']
  prepare?: UseStaticPresentationOptions['prepare']
  modelState?: ReturnType<typeof ref<string>>
}

beforeEach(() => {
  vi.resetModules()
  vi.useFakeTimers()
  document.body.innerHTML = '<div id="app"></div>'
  window.history.replaceState({}, '', '/?runtimeCapture=1')
})

afterEach(() => {
  const mount = document.querySelector('[data-v-app]') as (HTMLElement & { __vue_app__?: App }) | null
  mount?.__vue_app__?.unmount()
  state.router?.options.history.destroy()
  state.router = null
  document.body.innerHTML = ''
  delete window.__RENDER_READY__
  delete window.__EDITOR_RUNTIME_PREVIEW_READY__
  delete window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__
  window.history.replaceState({}, '', '/')
  vi.useRealTimers()
})

/** 仅替换配置与路由来源；通过真实发布根组件、静态声明、资源探针和 Vue Router 启动入口。 */
async function mountBuildRelease(pages: Record<string, PageFixture>): Promise<Router> {
  const { useStaticPresentation } = await import('@/runtime-kit/public/composables/static/useStaticPresentation.v1')
  const routes = Object.entries(pages).map(([path, fixture]) => ({
    path,
    component: defineComponent({
      setup() {
        const root = ref<HTMLElement | null>(null)
        useStaticPresentation({ root, mode: fixture.mode ?? 'default', prepare: fixture.prepare })
        return () => h('main', { ref: root, class: 'runtime-page-print-source' }, [
          h('span', path),
          fixture.modelState ? h('div', { 'data-runtime-model-state': fixture.modelState.value }) : null,
        ])
      },
    }),
  }))
  const router = createRouter({ history: createMemoryHistory(), routes })
  state.router = router
  await router.push(routes[0].path)
  await import('./build-release-main')
  return router
}

/** 等待当前页完成协议聚合；unsupported 等失败回执同样必须有明确 mounted 终态。 */
async function expectMountedRoute(path: string): Promise<void> {
  await vi.waitFor(() => expect(window.__RENDER_READY__).toMatchObject({ mounted: true, routePath: path }))
}

describe('构建发布入口的静态就绪', () => {
  it.each(['ready', 'error'])('模型加载结束为 %s 前不放行，并保留资源检查结果', async result => {
    const modelState = ref('loading')
    await mountBuildRelease({ '/model': { modelState } })
    // 推进首屏布局后模型仍未完成，不能仅凭双帧把画布标成可导出。
    await vi.advanceTimersByTimeAsync(200)
    expect(window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__).toBeTypeOf('function')
    expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(false)
    expect(window.__RENDER_READY__?.mounted).toBe(false)

    modelState.value = result
    await expectMountedRoute('/model')
    expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(result === 'ready')
    expect(window.__RENDER_READY__?.visualAssets).toMatchObject({
      ready: result === 'ready', failed: result === 'error' ? 1 : 0,
    })
  })

  it('换到不可导出页面后撤销首页 ready，后续合法页和同路径新票据可重新就绪', async () => {
    const router = await mountBuildRelease({ '/first': {}, '/unsupported': { mode: 'unsupported' }, '/last': {} })
    await expectMountedRoute('/first')
    expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(true)

    await router.push('/unsupported')
    expect(window.__RENDER_READY__?.staticPresentation).toBeNull()
    expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(false)
    await expectMountedRoute('/unsupported')
    expect(window.__RENDER_READY__?.staticPresentation?.status).toBe('unsupported')
    expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(false)

    await router.push('/last')
    await expectMountedRoute('/last')
    expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(true)
    await router.push('/last?runtimeCaptureTicket=next')
    expect(window.__RENDER_READY__?.mounted).toBe(false)
    expect(window.__RENDER_READY__?.staticPresentation).toBeNull()
    expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(false)
    await expectMountedRoute('/last')
    expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(true)
  })

  it('后续页面必须等静态 prepare 完成，离页后的迟到结果不能覆盖当前回执', async () => {
    let finishPreparation!: () => void
    const preparation = new Promise<void>(resolve => { finishPreparation = resolve })
    const router = await mountBuildRelease({
      '/first': {}, '/pending': { prepare: () => preparation }, '/last': { mode: 'unsupported' },
    })
    await expectMountedRoute('/first')
    await router.push('/pending')
    await vi.advanceTimersByTimeAsync(200)
    expect(window.__RENDER_READY__?.mounted).toBe(false)
    expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(false)

    await router.push('/last')
    await expectMountedRoute('/last')
    finishPreparation()
    await vi.advanceTimersByTimeAsync(200)
    expect(window.__RENDER_READY__).toMatchObject({ routePath: '/last', staticPresentation: { status: 'unsupported' } })
    expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(false)
  })

  it('首屏稳定前发生导航时，首次挂载等待不能覆盖新页回执', async () => {
    const router = await mountBuildRelease({ '/first': {}, '/last': { mode: 'unsupported' } })
    await vi.waitFor(() => expect(document.querySelector('.runtime-page-print-source')).not.toBeNull())
    await router.push('/last')
    await expectMountedRoute('/last')
    expect(window.__RENDER_READY__?.staticPresentation?.status).toBe('unsupported')
    expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(false)
  })
})
