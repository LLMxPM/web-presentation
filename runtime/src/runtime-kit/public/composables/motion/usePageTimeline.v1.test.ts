// @vitest-environment jsdom
/**
 * 文件功能：验证公开 usePageTimeline.v1 的目标绑定、句柄注册、poster 与释放语义。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, nextTick, ref } from 'vue'

import { initializeRuntimeExecution, resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import {
  findPageMotionHandle,
  PAGE_MOTION_ATTR,
  readPageMotionHandle,
} from '@/core/motion/page-motion-contract'
import { usePageTimeline, type PageTimelineAuthoringDefinition, type PageTimelineBindingMap, type UsePageTimelineApi } from './usePageTimeline.v1'

const BINDING_ATTR = 'data-runtime-motion-binding'

function flushAsync(): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, 0))
    .then(() => nextTick())
    .then(() => new Promise(resolve => setTimeout(resolve, 0)))
    .then(() => nextTick())
}

type MountOptions = {
  definition: PageTimelineAuthoringDefinition<string>
  bindings: PageTimelineBindingMap
  pagePath?: string
}

function mountTimeline(options: MountOptions) {
  const root = ref<HTMLElement | null>(null)
  let api!: UsePageTimelineApi
  const App = defineComponent({
    setup() {
      api = usePageTimeline({ ...options, root })
      return () => h('div', { ref: root }, [h('h1', { class: 'title' }, '标题')])
    },
  })
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp(App)
  app.mount(host)
  return { app, api, get root() { return root.value }, host }
}

afterEach(() => {
  resetRuntimeExecutionForTests()
  document.body.innerHTML = ''
  delete window.__RENDER_READY__
})

describe('usePageTimeline.v1', () => {
  it('同源码 ref 绑定重复挂载后的计划与状态摘要保持一致', async () => {
    const digests: string[] = []
    for (let index = 0; index < 2; index++) {
      let api!: UsePageTimelineApi
      const host = document.createElement('div')
      document.body.append(host)
      const app = createApp(defineComponent({ setup() {
        const root = ref<HTMLElement | null>(null)
        const title = ref<HTMLElement | null>(null)
        api = usePageTimeline({ root, bindings: { title }, applyPoster: false, definition: {
          schemaVersion: 1, timelineId: 'stable', tracks: [{ type: 'dom', id: 'title', target: 'title', preset: 'fade', durationMs: 1000 }],
        } })
        return () => h('section', { ref: root }, [h('h1', { ref: title }, '标题')])
      } }))
      app.mount(host)
      await api.ready
      digests.push(JSON.stringify([api.plan.value?.planDigest, (await api.sampleAt(500)).stateDigest]))
      app.unmount()
      host.remove()
    }
    expect(digests[0]).toBe(digests[1])
  })

  it('公开原生填充入口支持纯视觉、getter 根与默认 poster', async () => {
    initializeRuntimeExecution('?runtimeMode=cards')
    let api!: UsePageTimelineApi
    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(defineComponent({ setup() {
      const root = ref<HTMLElement | null>(null)
      api = usePageTimeline({ root: () => root.value, bindings: {}, timelineId: 'native', poster: { atMs: 500 },
        define: context => ({ plan: context.resources().build(), visual(timeline) {
          timeline.fromTo('.title', { opacity: 0 }, { opacity: 1, duration: 1 }, 0)
        } }),
      })
      return () => h('section', { ref: root }, [h('h1', { class: 'title' }, '标题')])
    } }))
    app.mount(host)
    await api.ready
    expect(api.plan.value?.visual?.durationMs).toBe(1000)
    expect(Number(host.querySelector('h1')!.style.opacity)).toBeCloseTo(0.5)
    app.unmount()
  })
  it('把绑定 key 翻译为选择器并在页面根注册句柄', async () => {
    const mounted = mountTimeline({
      definition: {
        schemaVersion: 1,
        timelineId: 'intro',
        tracks: [{ type: 'dom', id: 'title-in', target: 'title', preset: 'fade', durationMs: 400 }],
      },
      bindings: { title: '.title' },
      pagePath: '/cover',
    })
    await flushAsync()

    expect(mounted.api.plan.value?.tracks[0]).toMatchObject({ target: '.title' })
    expect(mounted.api.state.value?.timelineId).toBe('intro')
    expect(mounted.root?.getAttribute(PAGE_MOTION_ATTR)).toBe('v1')
    expect(readPageMotionHandle(mounted.root)?.plan.timelineId).toBe('intro')
    expect(findPageMotionHandle(mounted.root!)).not.toBeNull()

    mounted.app.unmount()
  })

  it('元素绑定写实例级临时属性，卸载后清理', async () => {
    const title = document.createElement('h2')
    document.body.appendChild(title)
    const mounted = mountTimeline({
      definition: {
        schemaVersion: 1,
        timelineId: 'element-binding',
        tracks: [{ type: 'dom', id: 'title-in', target: 'title', preset: 'fade-up', durationMs: 400 }],
      },
      bindings: { title },
    })
    await flushAsync()

    expect(title.getAttribute(BINDING_ATTR)).toBe('binding-title')
    const pageRoot = mounted.root
    expect(readPageMotionHandle(pageRoot)?.plan.tracks[0]).toMatchObject({
      target: `[${BINDING_ATTR}="${title.getAttribute(BINDING_ATTR)}"]`,
    })

    mounted.app.unmount()
    expect(title.hasAttribute(BINDING_ATTR)).toBe(false)
    expect(pageRoot?.hasAttribute(PAGE_MOTION_ATTR)).toBe(false)
  })

  it('绑定缺失时记录可定位错误且不注册句柄', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const mounted = mountTimeline({
      definition: {
        schemaVersion: 1,
        timelineId: 'missing-binding',
        tracks: [{ type: 'dom', id: 'title-in', target: 'missing', preset: 'fade', durationMs: 400 }],
      } as never,
      bindings: { title: '.title' },
    })
    await flushAsync()

    expect(mounted.api.error.value).toMatchObject({
      code: 'TIMELINE_TARGET_INVALID',
      fieldPath: 'timeline.tracks.title-in.target',
    })
    expect(readPageMotionHandle(mounted.root)).toBeNull()

    mounted.app.unmount()
    consoleError.mockRestore()
  })

  it('交互式预览自动应用 poster，页面根可直接被捕获桥读取', async () => {
    initializeRuntimeExecution('?runtimeMode=cards')
    const mounted = mountTimeline({
      definition: {
        schemaVersion: 1,
        timelineId: 'poster',
        poster: { atMs: 250 },
        tracks: [{ type: 'dom', id: 'title-in', target: 'title', preset: 'fade', durationMs: 1000 }],
      },
      bindings: { title: '.title' },
    })
    await flushAsync()

    const handle = readPageMotionHandle(mounted.root)
    expect(handle?.getSnapshot()).toMatchObject({
      timelineId: 'poster',
      phase: 'ready',
      positionMs: 250,
      intent: 'stopped',
    })

    mounted.app.unmount()
  })
})
