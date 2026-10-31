// @vitest-environment jsdom
/** 文件功能：验证真实组件预览宿主继承静态上下文并发布静态回执，交互预览仍只允许手势媒体。 */
import { createApp, defineComponent, h, ref } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { initializeRuntimeExecution, resetRuntimeExecutionForTests, useRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { useStaticPresentation } from '@/runtime-kit/public/composables/static/useStaticPresentation.v1'
import ComponentPreviewView from './ComponentPreviewView.vue'

const { load, probe } = vi.hoisted(() => ({ load: vi.fn(), probe: vi.fn() }))
vi.mock('@/core/utils/preview-module', () => ({ importPreviewModule: load }))
vi.mock('@/core/utils/path', () => ({
  getRuntimePreviewContext: () => ({ artifactId: 'component-test' }),
  getRuntimePreloadedConfig: () => ({ component_preview: { component_import_path: '@/components/test.vue', schema: null } }),
}))
vi.mock('@/core/utils/config', () => ({
  DEFAULT_PAGE_CONFIG: { width: 1920, height: 1080, baseFontSize: '20px', iconDefaultStrokeWidth: 2 },
  appPageConfig: { value: { width: 1920, height: 1080, baseFontSize: '20px', iconDefaultStrokeWidth: 2 } },
}))

afterEach(() => {
  document.body.innerHTML = ''
  delete window.__RENDER_READY__
  delete window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__
  delete window.__RENDER_APPLY_SCENARIO__
  load.mockReset()
  probe.mockReset()
  resetRuntimeExecutionForTests()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

it.each(['capture', 'interactive-preview'])('%s 组件宿主保留执行策略且桥状态一致', async context => {
  vi.useFakeTimers()
  initializeRuntimeExecution(`?runtimeExecution=${context}`)
  const prepare = vi.fn()
  let allowsMedia: boolean | undefined
  load.mockResolvedValue({ default: defineComponent({ setup() {
    const root = ref<HTMLElement | null>(null)
    const policy = useRuntimeExecutionPolicy()
    allowsMedia = policy.value.allowMediaPlayback
    useStaticPresentation({ root, mode: 'poster', prepare })
    return () => h('div', { ref: root }, '组件静态内容')
  } }) })
  probe.mockResolvedValue({ ok: true, total: 0, failed: [], pending: [], timedOut: false })
  window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__ = probe
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(ComponentPreviewView)
  app.mount(host)
  try {
    await vi.advanceTimersByTimeAsync(100)
    expect(window.__RENDER_READY__).toMatchObject({ mounted: true, executionContext: context,
      staticPresentation: context === 'capture' ? { status: 'ready' } : null })
    expect(allowsMedia).toBe(context !== 'capture')
    expect(prepare).toHaveBeenCalledTimes(context === 'capture' ? 1 : 0)
    expect(probe).toHaveBeenCalledWith(expect.objectContaining({ staticMedia: context === 'capture' }))
    const post = vi.spyOn(window.parent, 'postMessage')
    const scenario = window.__RENDER_APPLY_SCENARIO__!({ scenarioKey: 'alternate', profileKey: 'default', requestId: 'scenario-1' })
    await vi.advanceTimersByTimeAsync(100)
    expect(await scenario).toEqual({ requestId: 'scenario-1', ok: true, scenarioKey: 'alternate' })
    expect(probe).toHaveBeenCalledTimes(2)
    expect(post).toHaveBeenCalledWith(expect.objectContaining({ type: 'component-preview:render-settled', payload: expect.objectContaining({ requestId: 'scenario-1' }) }), '*')
  } finally { app.unmount() }
})
