/**
 * 文件功能：G1 真实浏览器验收夹具；按场景挂载正式 usePageTimeline.v1 入口。
 *
 * 只替换资源来源（真实 WebM/WAV/GLB），不替换 transport、适配器、媒体元素或 Three.js；
 * 断言与证据收集全部在 Node 侧完成，页面只暴露最小控制面。
 */
import { createApp, defineComponent, h, ref } from 'vue'
import ModelViewer from '@/runtime-kit/internal/renderers/ModelViewer.vue'
import { usePageTimeline } from '@/runtime-kit/public/composables/motion/usePageTimeline.v1'
import { initializeRuntimeExecution } from '@/core/execution/execution-scope'
import { installCaptureMotionBridge } from '@/core/motion/capture-bridge'
import { createPageMediaSession } from '@/core/media/page-media-session'

initializeRuntimeExecution('?runtimeExecution=presentation')
installCaptureMotionBridge()

const VIDEO = '/fixtures/clock.webm'
const AUDIO = '/fixtures/tone.wav'
const MODEL = '/fixtures/spin.glb'

export interface ScenarioOptions {
  /** 双模型场景的第二实例裁切起点，用于验证实例隔离。 */
  bInMs?: number
  /** 第二模型显式相机，用于验证相机配置与第一实例隔离。 */
  bCameraPosition?: [number, number, number]
  /** 缓冲场景使用分块慢速视频，真实触发 waiting/buffering。 */
  slowVideo?: boolean
  /** 显式偏好覆盖系统降动效设置。 */
  visualMode?: 'full' | 'reduced'
}

let mounted: { app: ReturnType<typeof createApp>; api: ReturnType<typeof usePageTimeline> } | null = null

/** 解析场景定义；每个场景返回绑定表、定义与渲染函数。 */
function buildScenario(name: string, options: ScenarioOptions) {
  const bindings = {
    title: '.title',
    sub: '.sub',
    steps: '.steps',
    tail: '.tail',
    'model-a': '.model-a',
    'model-b': '.model-b',
  }
  switch (name) {
    case 'A03-dom-layout':
      return {
        bindings,
        definition: {
          schemaVersion: 1 as const,
          timelineId: 'dom-layout',
          tracks: [
            { type: 'dom' as const, id: 'title', target: 'title', preset: 'fade-up' as const, durationMs: 600 },
            { type: 'dom' as const, id: 'sub', target: 'sub', from: { opacity: 0, y: 24 }, to: { opacity: 1, y: 0 }, durationMs: 400, startMs: 200 },
            { type: 'dom' as const, id: 'steps', target: 'steps', from: { opacity: 0 }, to: { opacity: 1 }, durationMs: 300, afterTrack: 'title', offsetMs: -300 },
          ],
        },
        render: root => h('section', { class: 'stage', ref: root }, [
          h('h1', { class: 'title' }, '标题'),
          h('p', { class: 'sub' }, '副标题'),
          h('ul', { class: 'steps' }, [h('li', '一'), h('li', '二')]),
        ]),
      }
    case 'A06-media-clock':
    case 'A10-media-ownership':
      return {
        bindings,
        timelineId: 'media-clock',
        define: (ctx: { resources: () => { video: Function } }) => ({
          plan: [
            ...ctx.resources().video('main', { asset: 'demo', selector: '.video', outMs: 3000, role: 'primary', muted: true }).build(),
          ],
          visual(timeline: { fromTo: Function }) {
            timeline.fromTo('.title', { opacity: 0 }, { opacity: 1, duration: 3, ease: 'none' })
          },
        }),
        render: root => h('section', { class: 'stage', ref: root }, [
          h('h1', { class: 'title' }, '媒体时钟'),
          h('video', { class: 'video', muted: true, preload: 'auto', src: VIDEO, width: 320 }),
          ...(name === 'A10-media-ownership'
            ? [h('audio', { class: 'independent', muted: true, preload: 'auto', src: AUDIO })] : []),
        ]),
      }
    case 'A07-buffer-pause':
      return {
        bindings,
        timelineId: 'buffer-pause',
        define: (ctx: { resources: () => { video: Function } }) => ({
          plan: [
            ...ctx.resources().video('main', { asset: 'demo', selector: '.video', outMs: 6000, role: 'primary', muted: true }).build(),
          ],
          visual(timeline: { fromTo: Function }) {
            timeline.fromTo('.title', { opacity: 0 }, { opacity: 1, duration: 6, ease: 'none' })
          },
        }),
        render: root => h('section', { class: 'stage', ref: root }, [
          h('h1', { class: 'title' }, '缓冲与暂停'),
          h('video', { class: 'video', muted: true, preload: 'auto', src: options.slowVideo ? `${VIDEO}?slow=1` : VIDEO, width: 320 }),
        ]),
      }
    case 'A07-optional-failure':
      return {
        bindings,
        timelineId: 'optional-failure',
        define: (ctx: { resources: () => { video: Function } }) => ({
          plan: [
            ...ctx.resources().video('main', { asset: 'demo', selector: '.video', outMs: 3000, role: 'primary', muted: true }).build(),
            { type: 'audio' as const, id: 'decoration', asset: 'missing', selector: '.audio', outMs: 3000, role: 'decoration' as const, muted: true },
          ],
          visual(timeline: { fromTo: Function }) {
            timeline.fromTo('.title', { opacity: 0 }, { opacity: 1, duration: 3, ease: 'none' })
          },
        }),
        render: root => h('section', { class: 'stage', ref: root }, [
          h('h1', { class: 'title' }, '可选媒体失败'),
          h('video', { class: 'video', muted: true, preload: 'auto', src: VIDEO, width: 320 }),
          h('audio', { class: 'audio', muted: true, preload: 'auto', src: '/fixtures/missing.wav' }),
        ]),
      }
    case 'A07-secondary-buffer':
      return {
        bindings,
        timelineId: 'secondary-buffer',
        define: (ctx: { resources: () => { video: Function } }) => ({
          plan: [
            ...ctx.resources().video('main', { asset: 'demo', selector: '.video', outMs: 3000, role: 'primary', muted: true }).build(),
            { type: 'video' as const, id: 'secondary', asset: 'second', selector: '.secondary', outMs: 3000, role: 'content' as const, muted: true },
          ],
          visual(timeline: { fromTo: Function }) {
            timeline.fromTo('.title', { opacity: 0 }, { opacity: 1, duration: 3, ease: 'none' })
          },
        }),
        render: root => h('section', { class: 'stage', ref: root }, [
          h('h1', { class: 'title' }, '次要媒体缓冲'),
          h('video', { class: 'video', muted: true, preload: 'auto', src: VIDEO, width: 320 }),
          h('video', { class: 'secondary', muted: true, preload: 'auto', src: `${VIDEO}?slow=1`, width: 160 }),
        ]),
      }
    case 'A08-autoplay':
      return {
        bindings,
        timelineId: 'autoplay',
        define: (ctx: { resources: () => { voice: Function } }) => ({
          plan: [
            ...ctx.resources().voice('voice', { asset: 'narration', selector: '.audio', outMs: 2000, muted: false }).build(),
          ],
          visual(timeline: { fromTo: Function }) {
            timeline.fromTo('.title', { opacity: 0 }, { opacity: 1, duration: 2, ease: 'none' })
          },
        }),
        render: root => h('section', { class: 'stage', ref: root }, [
          h('h1', { class: 'title' }, '自动播放策略'),
          h('audio', { class: 'audio', preload: 'auto', src: AUDIO }),
        ]),
      }
    case 'A09-seek-handover':
      return {
        bindings,
        timelineId: 'seek-handover',
        define: (ctx: { resources: () => { video: Function } }) => ({
          plan: [
            ...ctx.resources().video('main', { asset: 'demo', selector: '.video', outMs: 900, role: 'primary', muted: true }).build(),
            { type: 'dom' as const, id: 'tail', target: 'tail', from: { opacity: 0 }, to: { opacity: 1 }, durationMs: 1200, afterTrack: 'main' },
          ],
          visual(timeline: { fromTo: Function }) {
            timeline.fromTo('.title', { opacity: 0 }, { opacity: 1, duration: 2.1, ease: 'none' })
          },
        }),
        render: root => h('section', { class: 'stage', ref: root }, [
          h('h1', { class: 'title' }, '定位与交接'),
          h('video', { class: 'video', muted: true, preload: 'auto', src: VIDEO, width: 320 }),
          h('div', { class: 'tail' }, '收尾'),
        ]),
      }
    case 'A13-capture':
      return {
        bindings,
        definition: {
          schemaVersion: 1 as const,
          timelineId: 'capture',
          poster: { atLabel: 'readable' },
          tracks: [
            { type: 'dom' as const, id: 'title', target: 'title', preset: 'fade' as const, durationMs: 1000 },
            { type: 'video' as const, id: 'clip', asset: 'demo', selector: '.video', outMs: 2000, muted: true },
            { type: 'dom' as const, id: 'tail', target: 'tail', from: { opacity: 0 }, to: { opacity: 1 }, durationMs: 200, startMs: 800, label: 'readable' },
          ],
        },
        render: root => h('section', { class: 'stage', ref: root }, [
          h('h1', { class: 'title' }, '指定状态捕获'),
          h('video', { class: 'video', muted: true, preload: 'auto', src: VIDEO, width: 320 }),
          h('div', { class: 'tail' }, '可读状态'),
        ]),
      }
    case 'A04-model-instances': {
      const bInMs = options.bInMs ?? 600
      return {
        bindings,
        definition: {
          schemaVersion: 1 as const,
          timelineId: 'model-instances',
          tracks: [
            { type: 'model3d' as const, id: 'a', asset: 'model-a', selector: 'model-a', clip: { index: 0, name: 'Spin', durationMs: 2000 },
              inMs: 0, outMs: 2000, startMs: 0, transform: { from: { rotationY: 0 }, to: { rotationY: 60 } } },
            { type: 'model3d' as const, id: 'b', asset: 'model-b', selector: 'model-b', clip: { index: 0, name: 'Spin', durationMs: 2000 },
              inMs: bInMs, outMs: 2000, startMs: 0, transform: { from: { rotationY: 0 }, to: { rotationY: -60 } } },
          ],
        },
        render: root => h('section', { class: 'stage model-row', ref: root }, [
          h(ModelViewer, { class: 'model-a', name: 'model-a', src: MODEL, background: 'transparent' }),
          h(ModelViewer, { class: 'model-b', name: 'model-b', src: MODEL, background: 'transparent',
            cameraPosition: options.bCameraPosition, cameraTarget: options.bCameraPosition ? [0, 0, 0] : undefined }),
        ]),
      }
    }
    default:
      throw new Error(`未知场景 ${name}`)
  }
}

/** 挂载指定场景；返回可直接调用的公开编排句柄。 */
async function mount(name: string, options: ScenarioOptions = {}): Promise<void> {
  unmount()
  const scenario = buildScenario(name, options)
  const host = document.createElement('div')
  host.className = 'harness-host'
  document.body.append(host)

  let api!: ReturnType<typeof usePageTimeline>
  const app = createApp(defineComponent({
    setup() {
      const root = ref<HTMLElement | null>(null)
      api = usePageTimeline({
        root,
        bindings: scenario.bindings,
        applyPoster: false,
        visualMode: options.visualMode,
        ...('definition' in scenario
          ? { definition: scenario.definition }
          : { timelineId: (scenario as { timelineId: string }).timelineId, define: (scenario as { define: unknown }).define }),
      } as never)
      Object.assign(window, { probe: api })
      return () => scenario.render(root)
    },
  }))
  app.mount(host)
  mounted = { app, api }
  await api.ready
}

/** 卸载当前场景并释放 transport。 */
function unmount(): void {
  mounted?.api.dispose()
  mounted?.app.unmount()
  mounted = null
  document.body.innerHTML = ''
}

Object.assign(window, {
  harness: {
    mount,
    unmount,
    /** 建立正式旧媒体会话，以真实元素核对时间轴所有权过滤。 */
    createLegacyMediaSession() {
      const root = document.querySelector<HTMLElement>('.stage')!
      const handle = (root as HTMLElement & {
        __runtimePageMotionV1: { isElementClaimed(element: Element): boolean }
      }).__runtimePageMotionV1
      const session = createPageMediaSession({
        root, generation: 1,
        isExternallyOwned: element => handle.isElementClaimed(element),
      })
      Object.assign(window, { legacySession: session })
      return session.getSnapshot()
    },
    /** 测试静态父作用域对媒体播放的硬限制。 */
    setExecution(kind: 'presentation' | 'capture') {
      initializeRuntimeExecution(`?runtimeExecution=${kind}`)
    },
    /** 读取真实 DOM 状态，供 Node 侧断言；不接受在页面内伪造结果。 */
    read(selector: string) {
      const element = document.querySelector<HTMLElement>(selector)
      if (!element) return null
      const style = getComputedStyle(element)
      const rect = element.getBoundingClientRect()
      return {
        opacity: Number(style.opacity),
        transform: style.transform,
        offsetLeft: element.offsetLeft,
        offsetTop: element.offsetTop,
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      }
    },
  },
})

// 浏览器自行在加载后发起播放，避免 Playwright 的 evaluate 人为赋予用户激活。
if (new URLSearchParams(window.location.search).has('autoplayProbe')) {
  void mount('A08-autoplay').then(() => {
    setTimeout(async () => {
      const activation = { active: navigator.userActivation.isActive, ever: navigator.userActivation.hasBeenActive }
      const ok = await mounted!.api.play()
      const state = (document.querySelector('[data-runtime-page-motion]') as HTMLElement & {
        __runtimePageMotionV1?: { getSnapshot(): { phase: string; errorCode: string | null } }
      } | null)?.__runtimePageMotionV1?.getSnapshot()
      Object.assign(window, { autoplayFirst: { ok, activation, phase: state?.phase, error: state?.errorCode } })
    }, 100)
  })
}
