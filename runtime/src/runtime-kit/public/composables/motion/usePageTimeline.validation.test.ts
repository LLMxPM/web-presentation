/** 文件功能：回归时间轴初始化/准备失败的渲染校验上报、实例隔离和末尾标签海报。 */
import { afterEach, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, ref } from 'vue'
import { initializeRuntimeExecution, resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { initializeRenderReadyHost, markRenderPreviewMounted } from '@/core/utils/render-ready'
import { usePageTimeline, type UsePageTimelineApi } from './usePageTimeline.v1'

const unmounts: Array<() => void> = []
afterEach(() => {
  unmounts.splice(0).forEach(unmount => unmount())
  document.body.innerHTML = ''
  delete window.__RENDER_READY__
  delete window.__EDITOR_RUNTIME_PREVIEW_READY__
  resetRuntimeExecutionForTests()
  vi.restoreAllMocks()
})

/** 在真实 Vue 生命周期创建独立画布；测试本身不替换时间轴编译或适配器。 */
function mount(make: (root: ReturnType<typeof ref<HTMLElement | null>>) => UsePageTimelineApi, count = 1, thumbnail = false) {
  initializeRuntimeExecution('?runtimeExecution=capture')
  initializeRenderReadyHost({ executionContext: 'capture' })
  vi.spyOn(console, 'error').mockImplementation(() => {})
  const host = document.createElement('div')
  if (!thumbnail) host.className = 'runtime-view-preview-source'
  document.body.append(host)
  let api!: UsePageTimelineApi
  const app = createApp(defineComponent({ setup() {
    const root = ref<HTMLElement | null>(null)
    api = make(root)
    return () => h('section', { ref: root }, [h('h1', { class: 'title' }, '标题'),
      ...Array.from({ length: count }, (_, index) => h('p', { class: 'step' }, `步骤 ${index + 1}`))])
  } }))
  app.mount(host)
  unmounts.push(() => app.unmount())
  return { api, host }
}

it('海报越界被渲染协议记录，不能静态降级后标记校验就绪', async () => {
  const { api } = mount(root => usePageTimeline({ root, bindings: {}, timelineId: 'invalid-poster', poster: { atMs: 3000 },
    define: ctx => ({ plan: ctx.resources().build(), visual(tl) {
      tl.fromTo('.title', { opacity: 0 }, { opacity: 1, duration: 2.57 }, 0)
    } }),
  }))
  await expect(api.ready).rejects.toMatchObject({code:'TIMELINE_SCHEMA_INVALID',fieldPath:'timeline.poster.atMs'})
  await markRenderPreviewMounted()
  expect(window.__RENDER_READY__?.contentExceptions).toEqual([expect.objectContaining({
    code: 'TIMELINE_SCHEMA_INVALID', fieldPath: 'timeline.poster.atMs', message: expect.stringContaining('3000'),
  })])
  expect(window.__RENDER_READY__?.contentExceptions[0].message).toContain('2570')
  expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(false)
})

it('未自动应用海报的静态上下文也必须等待适配器准备失败', async () => {
  const { api } = mount(root => usePageTimeline({ root, bindings: { title: '.missing' }, applyPoster: false,
    definition: { schemaVersion: 1, timelineId: 'missing-target', tracks: [
      {type:'dom',id:'title',target:'title',preset:'fade',durationMs:1000},
    ] },
  }))
  await api.ready
  await markRenderPreviewMounted()
  expect(window.__RENDER_READY__?.contentExceptions).toEqual([expect.objectContaining({
    code: 'TIMELINE_TARGET_INVALID', trackId: 'title',
  })])
  expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(false)
})

it.each([1, 3, 5])('末尾标签随 %i 个错峰目标变化，静态校验固化可读海报', async count => {
  const { api, host } = mount(root => usePageTimeline({ root, bindings: {}, timelineId: 'labels', poster: { atLabel:'readable' },
    define: ctx => ({ plan: ctx.resources().build(), visual(tl) {
      tl.fromTo('.title', {opacity:0,y:24}, {opacity:1,y:0,duration:0.4}, 0)
      tl.fromTo('.step', {opacity:0,x:32}, {opacity:1,x:0,duration:0.35,stagger:0.15}, 0.5)
      tl.addLabel('readable')
    } }),
  }), count)
  await api.ready
  await markRenderPreviewMounted()
  expect(api.plan.value?.posterTimeMs).toBe(api.plan.value?.durationMs)
  expect(window.__RENDER_READY__?.contentExceptions).toEqual([])
  expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(true)
  expect([...host.querySelectorAll<HTMLElement>('.title,.step')].every(element => element.style.opacity === '1')).toBe(true)
})

it('其它缩略图实例的失败不污染当前画布，卸载实例不留校验任务', async () => {
  const bad = mount(root => usePageTimeline({root,bindings:{},timelineId:'thumbnail',poster:{atMs:9999},
    define:ctx=>({plan:ctx.resources().build(),visual(tl){tl.fromTo('.title',{opacity:0},{opacity:1,duration:1})}}),
  }),1,true)
  await expect(bad.api.ready).rejects.toBeDefined()
  const active = mount(root => usePageTimeline({root,bindings:{},timelineId:'active',poster:{atMs:1000},
    define:ctx=>({plan:ctx.resources().build(),visual(tl){tl.fromTo('.title',{opacity:0},{opacity:1,duration:1})}}),
  }))
  await active.api.ready
  await markRenderPreviewMounted()
  expect(window.__RENDER_READY__?.contentExceptions).toEqual([])
  bad.api.dispose()
  active.api.dispose()
  active.host.remove()
  await markRenderPreviewMounted()
  expect(window.__RENDER_READY__?.contentExceptions).toEqual([])
})
