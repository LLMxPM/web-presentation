// @vitest-environment jsdom
/** 文件功能：回归放映翻页前的时间轴初态、嵌套预览海报和静态捕获隔离。 */
/* eslint-disable vue/one-component-per-file */
import { afterEach, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, ref } from 'vue'
import type { ExecutionContextKind } from '@/core/execution/execution-policy'
import { initializeRuntimeExecution, provideRuntimeExecutionScope, resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { settleMotionReadiness } from '@/core/motion/readiness'
import { usePageTimeline, type UsePageTimelineApi } from './usePageTimeline.v1'

const unmounts: Array<() => void> = []
afterEach(() => {
  unmounts.splice(0).forEach(unmount => unmount())
  document.body.innerHTML = ''
  resetRuntimeExecutionForTests()
  vi.restoreAllMocks()
})

/** 模拟真实宿主注入策略：全局项目入口保持 presentation，子画布可收紧为预览或捕获。 */
function mountTimeline(kind: ExecutionContextKind, legacy = false, reduced = false) {
  initializeRuntimeExecution()
  let api!: UsePageTimelineApi
  const Page = defineComponent({ setup() {
    const root = ref<HTMLElement | null>(null)
    const common = { root, bindings: { title: '.title' }, applyPoster: true, visualMode: reduced ? 'reduced' as const : 'full' as const }
    api = usePageTimeline(legacy ? { ...common, definition: {
      schemaVersion: 1, timelineId: 'legacy', poster: { atMs: 1000 },
      tracks: [{ type: 'dom', id: 'title', target: 'title', preset: 'fade', durationMs: 1000 }],
    } } : { ...common, timelineId: 'review', poster: { atLabel: 'readable' }, define: ctx => ({
      plan: ctx.resources().build(), visual(tl) {
        tl.fromTo('.title', { opacity: 0, y: 18 }, { opacity: 1, y: 0, duration: 0.4 }, 0)
        tl.fromTo('.row', { opacity: 0, x: 24 }, { opacity: 1, x: 0, duration: 0.36, stagger: 0.12 }, 0.2)
        tl.addLabel('readable')
      },
    }) })
    return () => h('section', { ref: root }, [h('h1', { class: 'title' }, '复习'),
      ...Array.from({ length: 3 }, (_, index) => h('p', { class: 'row' }, `要点 ${index}`))])
  } })
  const app = createApp(defineComponent({ setup() {
    provideRuntimeExecutionScope(kind)
    return () => h(Page)
  } }))
  const host = document.createElement('div')
  document.body.append(host)
  app.mount(host)
  unmounts.push(() => app.unmount())
  return { api, host }
}

it.each([false, true])('放映挂载即准备初态，不因 applyPoster 显示终态（旧定义=%s）', async legacy => {
  const { api, host } = mountTimeline('presentation', legacy)
  // 首次绘制前就应隐藏入场元素，不能等放映宿主在过渡结束后才 prepare。
  expect(host.querySelector<HTMLElement>('.title')!.style.opacity).toBe('0')
  await api.ready
  expect(api.state.value).toMatchObject({ phase: 'ready', positionMs: 0, intent: 'stopped' })
  expect(host.querySelector<HTMLElement>('.title')!.style.opacity).toBe('0')
  if (!legacy) expect([...host.querySelectorAll<HTMLElement>('.row')].map(row => row.style.opacity)).toEqual(['0', '0', '0'])
})

it('窗口预览读取注入的执行策略并保留完整可读海报', async () => {
  const { api, host } = mountTimeline('interactive-preview')
  await api.ready
  expect(api.state.value).toMatchObject({ positionMs: api.plan.value!.posterTimeMs, intent: 'stopped' })
  expect([...host.querySelectorAll<HTMLElement>('.title,.row')].every(element => element.style.opacity === '1')).toBe(true)
})

it('预览海报准备期间快速离页，不采样已释放的时间轴或上报迟到错误', async () => {
  const log = vi.spyOn(console, 'error').mockImplementation(() => {})
  const { api } = mountTimeline('interactive-preview')
  api.dispose()
  await expect(api.ready).resolves.toBeUndefined()
  expect(api.error.value).toBeNull()
  expect(log).not.toHaveBeenCalled()
})

it.each(['capture', 'thumbnail'] as const)('%s 静态就绪仍显示海报且不启动播放', async kind => {
  const { api, host } = mountTimeline(kind)
  await api.ready
  expect(await settleMotionReadiness(host, true)).toEqual([])
  expect(api.state.value).toMatchObject({ positionMs: api.plan.value!.posterTimeMs, intent: 'stopped' })
  expect(host.querySelector<HTMLElement>('.title')!.style.opacity).toBe('1')
})

it('降动效放映在零点保持可读状态，不闪回完整入场动效', async () => {
  const { api, host } = mountTimeline('presentation', false, true)
  await api.ready
  expect(api.state.value).toMatchObject({ positionMs: 0, intent: 'stopped' })
  expect(host.querySelector<HTMLElement>('.title')!.style.opacity).toBe('1')
})
