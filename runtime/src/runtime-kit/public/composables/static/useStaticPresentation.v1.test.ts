/** 文件功能：验证独立静态声明、动画零构造、作用域隔离、不可呈现和准备期限。 */
import { afterEach, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, ref } from 'vue'
import { initializeRuntimeExecution, resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { initializeRenderReadyHost, markRenderPreviewMounted } from '@/core/utils/render-ready'
import { settleStaticPresentation } from '@/core/static-presentation/registry'
import { usePageScene } from '../motion/usePageScene.v1'
import { useStaticPresentation, type UseStaticPresentationOptions } from './useStaticPresentation.v1'
import captureCases from '../../../../../../tests/fixtures/static-capture-cases.json'

const unmounts: Array<() => void> = []
it.each(captureCases.filter(item => item.receipt))('跨端静态回执：$name', async candidate => {
  const page = mount({ mode: candidate.mode as UseStaticPresentationOptions['mode'], reason: '需要独立静态海报',
    prepare: () => { if (candidate.failure) throw new Error('静态失败') } }, false)
  expect(await page.api?.ready).toEqual(candidate.receipt)
})
afterEach(() => {
  unmounts.splice(0).forEach(unmount => unmount())
  document.body.innerHTML = ''
  delete window.__RENDER_READY__
  delete window.__EDITOR_RUNTIME_PREVIEW_READY__
  resetRuntimeExecutionForTests()
  vi.useRealTimers()
})

/** 挂载真实 Vue 组合式入口，受托管动画故意抛错以证明静态路径不执行 define。 */
function mount(options: Omit<UseStaticPresentationOptions, 'root'> | null, scene = true, context = 'capture') {
  initializeRuntimeExecution(`?runtimeExecution=${context}`)
  const host = document.createElement('div')
  document.body.append(host)
  const define = vi.fn(() => { throw new Error('静态模式不能运行受托管动画') })
  let api: ReturnType<typeof useStaticPresentation> | undefined
  const app = createApp(defineComponent({ setup() {
    const root = ref<HTMLElement | null>(null)
    if (options) api = useStaticPresentation({ ...options, root })
    if (scene) usePageScene({ root, define })
    return () => h('section', { ref: root }, '完整内容')
  } }))
  app.mount(host)
  const unmount = () => app.unmount()
  unmounts.push(unmount)
  return { host, define, api, unmount }
}

it.each(['capture', 'export', 'thumbnail'])('%s 声明可读默认态时不执行动画构造', async context => {
  const prepare = vi.fn()
  const page = mount({ mode: 'default', prepare }, true, context)
  expect(await settleStaticPresentation(page.host)).toMatchObject({ status: 'ready' })
  expect(page.api?.isStatic.value).toBe(true)
  expect(prepare).toHaveBeenCalledOnce()
  expect(page.define).not.toHaveBeenCalled()
  expect(page.host.textContent).toBe('完整内容')
})

it('没有受托管动画的普通页面继续默认静态渲染', async () => {
  const page = mount(null, false)
  expect(await settleStaticPresentation(page.host)).toEqual({ status: 'ready', code: null, message: null })
})

it('动画页面缺失独立声明时返回不可呈现，不能采样海报兜底', async () => {
  const page = mount(null)
  initializeRenderReadyHost({ executionContext: 'capture' })
  await markRenderPreviewMounted()
  expect(window.__RENDER_READY__?.staticPresentation).toMatchObject({ status: 'unsupported', code: 'STATIC_PRESENTATION_UNAVAILABLE' })
  expect(window.__RENDER_READY__?.contentExceptions).toEqual([])
  expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(false)
  expect(page.define).not.toHaveBeenCalled()
})

it('显式 unsupported 保留短原因且不运行准备回调', async () => {
  const prepare = vi.fn()
  const page = mount({ mode: 'unsupported', reason: '需要交互才能呈现', prepare })
  expect(await page.api?.ready).toMatchObject({ status: 'unsupported', message: '需要交互才能呈现' })
  expect(prepare).not.toHaveBeenCalled()
})

it('异步海报准备结束前不就绪，结束后使用独立内容', async () => {
  let complete!: () => void
  const page = mount({ mode: 'poster', prepare: () => new Promise<void>(resolve => { complete = resolve }) })
  await Promise.resolve()
  expect(page.api?.state.value).toBeNull()
  complete()
  expect(await settleStaticPresentation(page.host)).toMatchObject({ status: 'ready' })
})

it('准备异常属于失败，不伪装成不可呈现或成功', async () => {
  const page = mount({ mode: 'poster', prepare: () => { throw new Error('不能暴露的异常详情') } })
  expect(await page.api?.ready).toEqual({ status: 'failed', code: 'STATIC_PRESENTATION_FAILED', message: '静态呈现准备失败。' })
})

it('准备超时终止 signal 并返回稳定失败原因', async () => {
  vi.useFakeTimers()
  let signal!: AbortSignal
  const page = mount({ mode: 'poster', timeoutMs: 30, prepare: input => { signal = input.signal; return new Promise(() => {}) } })
  await vi.advanceTimersByTimeAsync(30)
  expect(await page.api?.ready).toMatchObject({ status: 'failed', code: 'STATIC_PRESENTATION_TIMEOUT' })
  expect(signal.aborted).toBe(true)
  page.unmount()
  unmounts.pop()
})

it('其它画布和卸载页面的不可呈现不污染当前作用域', async () => {
  const other = mount({ mode: 'unsupported' })
  const current = mount({ mode: 'default' })
  expect(await settleStaticPresentation(current.host)).toMatchObject({ status: 'ready' })
  other.unmount()
  unmounts.splice(0, 1)
  expect(await settleStaticPresentation(document)).toMatchObject({ status: 'ready' })
})

it('交互预览不运行静态 prepare', async () => {
  const prepare = vi.fn()
  const page = mount({ mode: 'poster', prepare }, false, 'interactive-preview')
  await page.api?.ready
  expect(page.api?.isStatic.value).toBe(false)
  expect(prepare).not.toHaveBeenCalled()
})
