// @vitest-environment jsdom
/**
 * 文件功能：验证放映宿主音频服务的作用域、会话静音、方向映射与公开 composable 注入。
 */

import { createApp, defineComponent, h, nextTick, ref, type App } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { initializeRuntimeExecution, resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { getRuntimeSession } from '@/core/router/runtime-session'
import type { RuntimePreloadedConfigBundle } from '@/core/shared/runtime-preview'
import { loadAudioConfig } from '@/core/utils/config'
import { setRuntimePreloadedConfig } from '@/core/utils/path'
import { useAudioCue } from '@/runtime-kit/public/composables/audio/useAudioCue.v1'
import { useAudioCues, type RuntimeAudioCues } from './useAudioCues'

/** 记录创建与播放操作的 Audio 替身。 */
class FakeAudio {
  static instances: FakeAudio[] = []
  src = ''
  volume = 1
  muted = false
  preload = ''
  currentTime = 0
  paused = true
  ended = false
  pause = vi.fn((): void => { this.paused = true })
  play = vi.fn((): Promise<void> => {
    this.paused = false
    return Promise.resolve()
  })

  constructor() {
    FakeAudio.instances.push(this)
  }
}

const mountedApps: App[] = []

beforeEach(async () => {
  FakeAudio.instances = []
  vi.stubGlobal('Audio', FakeAudio)
  resetRuntimeExecutionForTests()
  setRuntimePreloadedConfig({
    audio: {
      volume: { master: 0.5, narration: 1, effects: 0.5 },
      cues: {
        'transition.forward': { assetName: 'forward-sound', gain: 1 },
        'transition.backward': { assetName: 'backward-sound', gain: 1 },
        'interaction.confirm': { assetName: 'confirm-sound', gain: 0.8 },
        'interaction.open': { assetName: 'open-sound', gain: 1 },
        'interaction.after-resume': { assetName: 'resume-sound', gain: 1 },
      },
    },
    manifest: {
      artifact_id: 'audio-test',
      assets: {
        'forward-sound': 'forward.mp3',
        'backward-sound': 'backward.mp3',
        'confirm-sound': 'confirm.mp3',
        'open-sound': 'open.mp3',
        'resume-sound': 'resume.mp3',
      },
      asset_base_url: 'https://cdn.example/assets/',
    },
  } as unknown as RuntimePreloadedConfigBundle)
  await loadAudioConfig(true)
})

afterEach(async () => {
  mountedApps.splice(0).forEach(app => app.unmount())
  setRuntimePreloadedConfig(undefined)
  resetRuntimeExecutionForTests()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  Reflect.deleteProperty(document, 'hidden')
  document.body.innerHTML = ''
  await loadAudioConfig(true)
})

interface AudioHarness {
  router: ReturnType<typeof createRouter>
  active: { value: boolean }
  host: RuntimeAudioCues
  pagePlay: (key: string) => string
}

/** 挂载同时暴露 shell API 与页面 composable 的最小宿主。 */
async function mountAudio(activeValue = true): Promise<AudioHarness> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: defineComponent({ render: () => h('div') }) }],
  })
  await router.push('/')
  await router.isReady()

  const active = ref(activeValue)
  let hostApi: RuntimeAudioCues | undefined
  let pagePlay: ((key: string) => string) | undefined
  const Page = defineComponent({
    setup() {
      const { playCue } = useAudioCue()
      pagePlay = playCue
      return () => h('div', { 'data-testid': 'page' })
    },
  })
  const Root = defineComponent({
    setup() {
      hostApi = useAudioCues(active)
      return () => h(Page)
    },
  })

  const app = createApp(Root)
  app.use(router)
  const element = document.createElement('div')
  document.body.append(element)
  app.mount(element)
  mountedApps.push(app)
  await nextTick()

  return { router, active, host: hostApi!, pagePlay: pagePlay! }
}

describe('useAudioCues', () => {
  it('窗口化预览不发声，即使页面请求 cue 也返回 unavailable', async () => {
    const { host, pagePlay } = await mountAudio(false)

    expect(host.playInteractionCue('interaction.confirm')).toBe('unavailable')
    expect(host.playTransitionCue(1)).toBe('unavailable')
    expect(pagePlay('interaction.confirm')).toBe('unavailable')
    expect(FakeAudio.instances).toHaveLength(0)
  })

  it('放映态页面通过公开 composable 播放绑定音效并应用音量', async () => {
    const { pagePlay } = await mountAudio(true)

    expect(pagePlay('interaction.confirm')).toBe('played')
    expect(FakeAudio.instances).toHaveLength(1)
    expect(FakeAudio.instances[0].src).toBe('https://cdn.example/assets/confirm.mp3')
    expect(FakeAudio.instances[0].volume).toBeCloseTo(0.2)
  })

  it('空 key 返回 unavailable，不创建音频元素', async () => {
    const { pagePlay } = await mountAudio(true)

    expect(pagePlay('')).toBe('unavailable')
    expect(pagePlay('   ')).toBe('unavailable')
    expect(FakeAudio.instances).toHaveLength(0)
  })

  it('方向映射到前进/后退绑定并复用切页通道', async () => {
    const { host } = await mountAudio(true)

    expect(host.playTransitionCue(1)).toBe('played')
    expect(FakeAudio.instances[0].src).toBe('https://cdn.example/assets/forward.mp3')
    expect(host.playTransitionCue(-1)).toBe('played')
    expect(FakeAudio.instances).toHaveLength(1)
    expect(FakeAudio.instances[0].src).toBe('https://cdn.example/assets/backward.mp3')
  })

  it('会话静音优先于绑定，解除后继续播放', async () => {
    const { router, pagePlay } = await mountAudio(true)
    const session = getRuntimeSession(router)

    session.audioMuted.value = true
    expect(pagePlay('interaction.confirm')).toBe('skipped')
    expect(FakeAudio.instances).toHaveLength(0)

    session.audioMuted.value = false
    expect(pagePlay('interaction.confirm')).toBe('played')
  })

  it('非播放执行上下文不创建引擎，切页与页面 cue 全部 no-op', async () => {
    initializeRuntimeExecution('?runtimeMode=cards')
    const { host, pagePlay } = await mountAudio(true)

    expect(host.playTransitionCue(1)).toBe('unavailable')
    expect(pagePlay('interaction.confirm')).toBe('unavailable')
    expect(FakeAudio.instances).toHaveLength(0)
  })

  it('绑定资产未进入 manifest 映射时 no-op，不回退猜测路径', async () => {
    setRuntimePreloadedConfig({
      audio: {
        volume: { master: 1, narration: 1, effects: 1 },
        cues: { 'interaction.confirm': { assetName: 'missing-sound', gain: 1 } },
      },
      manifest: { artifact_id: 'audio-test', assets: {}, asset_base_url: 'https://cdn.example/assets/' },
    } as unknown as RuntimePreloadedConfigBundle)
    await loadAudioConfig(true)
    const { pagePlay } = await mountAudio(true)

    expect(pagePlay('interaction.confirm')).toBe('unavailable')
    expect(FakeAudio.instances).toHaveLength(0)
  })

  it('窗口隐藏与冻结暂停音效，恢复可见后允许新的 cue', async () => {
    const { pagePlay } = await mountAudio(true)
    expect(pagePlay('interaction.confirm')).toBe('played')
    expect(FakeAudio.instances[0].paused).toBe(false)

    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    document.dispatchEvent(new Event('visibilitychange'))
    expect(FakeAudio.instances[0].paused).toBe(true)
    expect(pagePlay('interaction.open')).toBe('unavailable')

    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    document.dispatchEvent(new Event('visibilitychange'))
    expect(pagePlay('interaction.open')).toBe('played')

    document.dispatchEvent(new Event('freeze'))
    expect(FakeAudio.instances.at(-1)?.paused).toBe(true)

    window.dispatchEvent(new Event('pageshow'))
    expect(pagePlay('interaction.after-resume')).toBe('played')
  })

  it('卸载时移除监听并释放正在播放的音频', async () => {
    const removeDocument = vi.spyOn(document, 'removeEventListener')
    const removeWindow = vi.spyOn(window, 'removeEventListener')
    const { pagePlay } = await mountAudio(true)
    expect(pagePlay('interaction.confirm')).toBe('played')
    const element = FakeAudio.instances[0]
    const app = mountedApps.pop()

    app?.unmount()

    expect(element.paused).toBe(true)
    expect(removeDocument).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
    expect(removeDocument).toHaveBeenCalledWith('freeze', expect.any(Function))
    expect(removeWindow).toHaveBeenCalledWith('pageshow', expect.any(Function))
    expect(pagePlay('interaction.confirm')).toBe('unavailable')
  })
})
