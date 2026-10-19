// @vitest-environment jsdom
/** 文件功能：验证 AudioViewer 的原生属性、稳定媒体标记、事件和静态执行策略。 */
import { createApp, nextTick, type App } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  initializeRuntimeExecution,
  resetRuntimeExecutionForTests,
} from '@/core/execution/execution-scope'
import type { RuntimePreloadedConfigBundle } from '@/core/shared/runtime-preview'
import { loadAudioConfig } from '@/core/utils/config'
import { setRuntimePreloadedConfig } from '@/core/utils/path'
import AudioViewer from './AudioViewer.vue'

const mountedApps: App<Element>[] = []
const pauseMock = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  Object.defineProperty(HTMLMediaElement.prototype, 'pause', { configurable: true, value: pauseMock })
})

afterEach(async () => {
  for (const app of mountedApps.splice(0)) app.unmount()
  setRuntimePreloadedConfig(undefined)
  await loadAudioConfig(true)
  resetRuntimeExecutionForTests()
  document.body.innerHTML = ''
})

/** 挂载音频渲染器并等待媒体 ref 注册。 */
async function mountViewer(props: Record<string, unknown> = {}) {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(AudioViewer, { src: '/assets/voice.mp3', ...props })
  mountedApps.push(app)
  const instance = app.mount(host) as InstanceType<typeof AudioViewer>
  await nextTick()
  await nextTick()
  return { host, instance, app }
}

describe('AudioViewer', () => {
  it('内容音频应使用原生控件、默认参数和稳定媒体标记，且不出现 autoplay', async () => {
    const { host, instance } = await mountViewer()
    const root = host.querySelector<HTMLElement>('.audio-viewer')
    const audio = host.querySelector<HTMLAudioElement>('audio')

    expect(root?.dataset.runtimeKitMedia).toBe('v1')
    expect(root?.dataset.runtimeKitMediaKind).toBe('audio')
    expect(root?.dataset.runtimeAudioState).toBe('ready')
    expect(audio?.dataset.runtimeMediaTarget).toBe('audio')
    expect(audio?.dataset.runtimeMediaPurpose).toBe('content')
    expect(audio?.controls).toBe(true)
    expect(audio?.preload).toBe('metadata')
    expect(audio?.volume).toBe(1)
    expect(audio?.playbackRate).toBe(1)
    expect(audio?.hasAttribute('autoplay')).toBe(false)
    expect(instance.getMediaElement()).toBe(audio)
  })

  it('旁白默认隐藏控件并支持合法音量、速率和 preload', async () => {
    const { host } = await mountViewer({
      purpose: 'narration',
      volume: 0.6,
      playbackRate: 1.25,
      preload: 'auto',
    })
    const audio = host.querySelector<HTMLAudioElement>('audio')

    expect(audio?.dataset.runtimeMediaPurpose).toBe('narration')
    expect(audio?.controls).toBe(false)
    expect(audio?.volume).toBe(0.6)
    expect(audio?.playbackRate).toBe(1.25)
    expect(audio?.preload).toBe('auto')
  })

  it('旁白叠加项目 master × narration，内容音频不受项目音量影响', async () => {
    setRuntimePreloadedConfig({
      audio: { volume: { master: 0.5, narration: 0.4, effects: 1 }, cues: {} },
    } as unknown as RuntimePreloadedConfigBundle)
    await loadAudioConfig(true)

    const narration = await mountViewer({ purpose: 'narration', volume: 0.5 })
    expect(narration.host.querySelector<HTMLAudioElement>('audio')?.volume).toBeCloseTo(0.1)

    const content = await mountViewer({ volume: 0.5 })
    expect(content.host.querySelector<HTMLAudioElement>('audio')?.volume).toBeCloseTo(0.5)
  })

  it('主资源失败时切换到兜底且不报最终错误，兜底再失败才上报', async () => {
    const onError = vi.fn()
    const { host } = await mountViewer({
      fallbackSrc: '/fallback.mp3',
      fallbackMessage: '音频不可用',
      onError,
    })

    host.querySelector('audio')!.dispatchEvent(new Event('error'))
    await nextTick()
    expect(onError).not.toHaveBeenCalled()
    expect(host.querySelector('audio')?.getAttribute('src')).toBe('/fallback.mp3')

    host.querySelector('audio')!.dispatchEvent(new Event('error'))
    await nextTick()
    expect(onError).toHaveBeenCalledTimes(1)
    expect(host.querySelector('audio')).toBeNull()
    expect(host.textContent).toContain('音频不可用')
  })

  it('旁白循环或数值越界时应进入有界错误状态且不渲染媒体', async () => {
    const narrationLoop = await mountViewer({ purpose: 'narration', loop: true })
    expect(narrationLoop.host.querySelector('audio')).toBeNull()
    expect(narrationLoop.host.querySelector('.audio-viewer')?.getAttribute('data-runtime-audio-state')).toBe('error')
    expect(narrationLoop.host.textContent).toContain('页面旁白不允许循环播放')

    const badVolume = await mountViewer({ volume: 1.1 })
    expect(badVolume.host.querySelector('audio')).toBeNull()
    expect(badVolume.host.textContent).toContain('0 到 1')
  })

  it('捕获等静态上下文应强制 preload=none 且仍不产生 autoplay', async () => {
    initializeRuntimeExecution('?runtimeCapture=1')
    const { host } = await mountViewer({ preload: 'auto' })
    const audio = host.querySelector<HTMLAudioElement>('audio')

    expect(audio?.preload).toBe('none')
    expect(audio?.hasAttribute('autoplay')).toBe(false)
  })

  it('卸载时应暂停并复位媒体', async () => {
    const { host, app } = await mountViewer()
    const audio = host.querySelector<HTMLAudioElement>('audio')!
    audio.currentTime = 9

    app.unmount()

    expect(pauseMock).toHaveBeenCalled()
    expect(audio.currentTime).toBe(0)
    mountedApps.splice(mountedApps.indexOf(app), 1)
  })
})
