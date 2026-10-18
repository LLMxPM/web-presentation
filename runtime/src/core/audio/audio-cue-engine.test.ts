/**
 * 文件功能：验证短音效引擎的绑定解析、通道替换、实例池、节流与释放边界。
 */

import { describe, expect, it, vi } from 'vitest'

import { AudioCueEngine, type AudioCueEngineOptions } from './audio-cue-engine'
import { DEFAULT_RUNTIME_AUDIO_CONFIG, type RuntimeAudioConfig } from './audio-config'

/** 记录元素操作的 Audio 替身；不连接真实媒体管线。 */
class FakeAudio {
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
    this.ended = false
    return Promise.resolve()
  })
}

interface Harness {
  engine: AudioCueEngine
  elements: FakeAudio[]
  urls: Map<string, string>
}

/** 创建注入替身与资源映射的引擎。 */
function createHarness(overrides: Partial<AudioCueEngineOptions> = {}, config?: RuntimeAudioConfig): Harness {
  const elements: FakeAudio[] = []
  const urls = new Map<string, string>([
    ['transition.forward', 'https://cdn.example/forward.mp3'],
    ['transition.backward', 'https://cdn.example/backward.mp3'],
    ['interaction.confirm', 'https://cdn.example/confirm.mp3'],
    ['interaction.open', 'https://cdn.example/open.mp3'],
    ['interaction.close', 'https://cdn.example/close.mp3'],
    ['interaction.next', 'https://cdn.example/next.mp3'],
    ['interaction.prev', 'https://cdn.example/prev.mp3'],
  ])
  const engine = new AudioCueEngine({
    config: config ?? createConfig(),
    resolveAssetUrl: name => urls.get(name) ?? null,
    allowPlayback: true,
    createAudio: () => {
      const element = new FakeAudio()
      elements.push(element)
      return element as unknown as HTMLAudioElement
    },
    ...overrides,
  })
  return { engine, elements, urls }
}

/** 默认绑定：切页两方向与五个交互 key。 */
function createConfig(volume = { master: 0.5, narration: 1, effects: 0.5 }): RuntimeAudioConfig {
  return {
    volume,
    cues: Object.fromEntries([
      'transition.forward',
      'transition.backward',
      'interaction.confirm',
      'interaction.open',
      'interaction.close',
      'interaction.next',
      'interaction.prev',
    ].map(key => [key, { assetName: key, gain: 0.8 }])),
  }
}

describe('AudioCueEngine', () => {
  it('切页 cue 使用 master × effects × gain 并设置资源地址', () => {
    const { engine, elements } = createHarness()

    expect(engine.playTransition('transition.forward')).toBe('played')
    expect(elements).toHaveLength(1)
    expect(elements[0].src).toBe('https://cdn.example/forward.mp3')
    expect(elements[0].preload).toBe('auto')
    expect(elements[0].volume).toBeCloseTo(0.2)
    expect(elements[0].play).toHaveBeenCalledTimes(1)
  })

  it('新切页立即停止上一段并复用同一实例', () => {
    const { engine, elements } = createHarness()

    engine.playTransition('transition.forward')
    expect(elements[0].paused).toBe(false)
    expect(elements[0].pause).toHaveBeenCalledTimes(1)
    expect(engine.playTransition('transition.backward')).toBe('played')

    expect(elements).toHaveLength(1)
    expect(elements[0].pause).toHaveBeenCalledTimes(2)
    expect(elements[0].src).toBe('https://cdn.example/backward.mp3')
  })

  it('缺绑定、缺资源或静态上下文返回 unavailable 且不创建元素', () => {
    const { engine, elements } = createHarness()
    expect(engine.playTransition('transition.missing')).toBe('unavailable')
    expect(engine.playInteraction('interaction.missing')).toBe('unavailable')

    const noUrl = createHarness({ resolveAssetUrl: () => null })
    expect(noUrl.engine.playTransition('transition.forward')).toBe('unavailable')
    expect(noUrl.elements).toHaveLength(0)

    const blocked = createHarness({ allowPlayback: false })
    expect(blocked.engine.playTransition('transition.forward')).toBe('unavailable')
    expect(blocked.elements).toHaveLength(0)
    expect(elements).toHaveLength(0)
  })

  it('会话静音或音量为零时跳过播放', () => {
    const muted = createHarness({ isMuted: () => true })
    expect(muted.engine.playInteraction('interaction.confirm')).toBe('skipped')
    expect(muted.elements).toHaveLength(0)

    const silent = createHarness({}, createConfig({ master: 0, narration: 1, effects: 1 }))
    expect(silent.engine.playInteraction('interaction.confirm')).toBe('skipped')
    expect(silent.elements).toHaveLength(0)
  })

  it('交互池最多四个实例，池满后复用最旧实例', () => {
    let clock = 0
    const { engine, elements } = createHarness({ now: () => clock })

    for (const key of ['interaction.confirm', 'interaction.open', 'interaction.close', 'interaction.next']) {
      clock += 100
      expect(engine.playInteraction(key)).toBe('played')
    }
    expect(elements).toHaveLength(4)

    clock += 100
    expect(engine.playInteraction('interaction.prev')).toBe('played')
    expect(elements).toHaveLength(4)
    // 最旧的 confirm 实例被暂停并复用。
    expect(elements[0].pause).toHaveBeenCalledTimes(1)
    expect(elements[0].src).toBe('https://cdn.example/prev.mp3')
  })

  it('同一交互 key 80ms 内节流，边界值允许再次播放', () => {
    let clock = 0
    const { engine, elements } = createHarness({ now: () => clock })

    expect(engine.playInteraction('interaction.confirm')).toBe('played')
    clock = 79
    expect(engine.playInteraction('interaction.confirm')).toBe('skipped')
    clock = 80
    expect(engine.playInteraction('interaction.confirm')).toBe('played')
    expect(elements).toHaveLength(2)
  })

  it('切页通道不被交互池占用', () => {
    let clock = 0
    const { engine, elements } = createHarness({ now: () => clock })

    for (const key of ['interaction.confirm', 'interaction.open', 'interaction.close', 'interaction.next']) {
      clock += 100
      engine.playInteraction(key)
    }
    clock += 100
    engine.playTransition('transition.forward')

    expect(elements).toHaveLength(5)
    expect(elements.at(-1)?.src).toBe('https://cdn.example/forward.mp3')
  })

  it('suspend 停止全部实例，resume 允许后续 cue 但不补播', () => {
    const { engine, elements } = createHarness()
    engine.playTransition('transition.forward')
    engine.playInteraction('interaction.confirm')

    engine.suspend()
    expect(elements.every(element => element.pause.mock.calls.length > 0)).toBe(true)
    expect(engine.playTransition('transition.backward')).toBe('unavailable')
    expect(engine.playInteraction('interaction.open')).toBe('unavailable')

    engine.resume()
    expect(engine.playInteraction('interaction.open')).toBe('played')
  })

  it('dispose 释放实例与节流状态，重复调用安全', () => {
    const { engine, elements } = createHarness()
    engine.playTransition('transition.forward')
    engine.playInteraction('interaction.confirm')

    engine.dispose()
    engine.dispose()
    expect(elements.every(element => element.pause.mock.calls.length > 0)).toBe(true)
    expect(engine.playTransition('transition.forward')).toBe('unavailable')
    expect(engine.playInteraction('interaction.confirm')).toBe('unavailable')
  })

  it('播放 Promise 拒绝或同步抛错只影响本次音效', async () => {
    const rejectingElement = new FakeAudio()
    rejectingElement.play.mockImplementation(() => Promise.reject(new Error('blocked')))
    const rejecting = createHarness({ createAudio: () => rejectingElement as unknown as HTMLAudioElement })

    expect(rejecting.engine.playTransition('transition.forward')).toBe('played')
    await Promise.resolve()
    expect(rejectingElement.pause).toHaveBeenCalled()

    const throwingElement = new FakeAudio()
    throwingElement.play.mockImplementation(() => { throw new Error('decode') })
    const throwing = createHarness({ createAudio: () => throwingElement as unknown as HTMLAudioElement })

    expect(throwing.engine.playTransition('transition.forward')).toBe('skipped')
    expect(throwingElement.pause).toHaveBeenCalled()
  })

  it('1000 次切页与交互后实例数保持恒定并可全部释放', () => {
    let clock = 0
    const { engine, elements } = createHarness({ now: () => clock })

    for (let index = 0; index < 1000; index += 1) {
      clock += 100
      engine.playTransition(index % 2 === 0 ? 'transition.forward' : 'transition.backward')
      const keys = ['interaction.confirm', 'interaction.open', 'interaction.close', 'interaction.next', 'interaction.prev']
      engine.playInteraction(keys[index % keys.length])
    }

    // 1 个切页通道 + 4 个交互池槽位，不随触发次数增长。
    expect(elements).toHaveLength(5)
    engine.dispose()
    expect(elements.every(element => element.pause.mock.calls.length > 0)).toBe(true)
    expect(engine.playTransition('transition.forward')).toBe('unavailable')
  })

  it('浏览器不提供 Audio 时返回 unavailable', () => {
    const engine = new AudioCueEngine({
      config: DEFAULT_RUNTIME_AUDIO_CONFIG,
      resolveAssetUrl: () => 'https://cdn.example/forward.mp3',
      allowPlayback: true,
      createAudio: () => null,
    })
    expect(engine.playTransition('transition.forward')).toBe('unavailable')
  })
})
