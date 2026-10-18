/**
 * 文件功能：实现项目级短音效引擎，提供切页单通道与 interaction 小型实例池。
 *
 * 首版只使用 HTMLAudioElement；缺失绑定、静态上下文、静音、节流和播放失败都
 * 返回稳定结果，不向页面业务事件抛错，也不改变导航或放映状态。
 */

import {
  resolveAudioCue,
  resolveCueVolume,
  type RuntimeAudioConfig,
} from './audio-config'

export type AudioCueResult = 'played' | 'skipped' | 'unavailable'

export interface AudioCueEngineOptions {
  config: RuntimeAudioConfig
  /** 把资源逻辑名解析为当前 artifact 的可播放地址；未命中的资源返回空串。 */
  resolveAssetUrl: (name: string) => string | null
  /** 是否允许发声；thumbnail/capture/export 等静态上下文为 false。 */
  allowPlayback: boolean
  /** 读取会话级静音；运行时切换无需重建引擎。 */
  isMuted?: () => boolean
  /** 测试替换音频元素工厂；生产环境使用 Audio。 */
  createAudio?: () => HTMLAudioElement | null
  /** 测试注入单调时钟。 */
  now?: () => number
}

interface InteractionSlot {
  element: HTMLAudioElement
  lastUsedAt: number
}

const INTERACTION_POOL_SIZE = 4
const INTERACTION_THROTTLE_MS = 80

export class AudioCueEngine {
  private readonly config: RuntimeAudioConfig
  private readonly resolveAssetUrl: (name: string) => string | null
  private readonly allowPlayback: boolean
  private readonly isMuted: () => boolean
  private readonly createAudio: () => HTMLAudioElement | null
  private readonly now: () => number
  private transitionElement: HTMLAudioElement | null = null
  private readonly interactionPool: InteractionSlot[] = []
  private readonly lastPlayedAt = new Map<string, number>()
  private disposed = false
  private suspended = false

  constructor(options: AudioCueEngineOptions) {
    this.config = options.config
    this.resolveAssetUrl = options.resolveAssetUrl
    this.allowPlayback = options.allowPlayback
    this.isMuted = options.isMuted ?? (() => false)
    this.createAudio = options.createAudio ?? (() => (
      typeof Audio === 'undefined' ? null : new Audio()
    ))
    this.now = options.now ?? (() => Date.now())
  }

  /** 播放切页 cue；新 cue 会立即停止并归零上一段，不叠加。 */
  playTransition(key: string): AudioCueResult {
    const resolution = this.resolvePlayableCue(key)
    if (typeof resolution === 'string') return resolution
    const element = this.transitionElement ?? this.createAudio()
    if (!element) return 'unavailable'
    this.transitionElement = element
    element.preload = 'auto'
    this.stop(element)
    if (!this.start(element, resolution.url, resolution.volume)) return 'skipped'
    return 'played'
  }

  /** 播放交互 cue；同一 key 80ms 内节流，池满时复用最旧实例。 */
  playInteraction(key: string): AudioCueResult {
    const resolution = this.resolvePlayableCue(key)
    if (typeof resolution === 'string') return resolution
    const now = this.now()
    const lastPlayedAt = this.lastPlayedAt.get(key)
    if (lastPlayedAt !== undefined && now - lastPlayedAt < INTERACTION_THROTTLE_MS) {
      return 'skipped'
    }
    this.lastPlayedAt.set(key, now)

    let slot = this.interactionPool.find(item => item.element.paused || item.element.ended)
    if (!slot && this.interactionPool.length < INTERACTION_POOL_SIZE) {
      const element = this.createAudio()
      if (!element) return 'unavailable'
      slot = { element, lastUsedAt: now }
      this.interactionPool.push(slot)
    }
    if (!slot) {
      // 池满：复用最旧的非关键播放，保持元素数量恒定。
      slot = [...this.interactionPool].sort((left, right) => left.lastUsedAt - right.lastUsedAt)[0]
      this.stop(slot.element)
    }
    slot.lastUsedAt = now
    slot.element.preload = 'auto'
    if (!this.start(slot.element, resolution.url, resolution.volume)) return 'skipped'
    return 'played'
  }

  /** 隐藏、freeze 或离开放映时暂停全部短音效；恢复不补播。 */
  suspend(): void {
    this.suspended = true
    if (this.transitionElement) this.stop(this.transitionElement)
    for (const slot of this.interactionPool) this.stop(slot.element)
  }

  /** 恢复新 cue 的播放资格；已经错过的短音效不会重放。 */
  resume(): void {
    this.suspended = false
  }

  /** 释放全部元素与节流记录；重复调用无副作用。 */
  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.suspend()
    this.transitionElement = null
    this.interactionPool.length = 0
    this.lastPlayedAt.clear()
  }

  /** 校验用途、绑定、静音、静态上下文和音量，返回可播放信息或稳定状态。 */
  private resolvePlayableCue(
    key: string,
  ): { url: string; volume: number } | AudioCueResult {
    if (this.disposed || !this.allowPlayback || this.suspended) return 'unavailable'
    const cue = resolveAudioCue(this.config, key)
    if (!cue) return 'unavailable'
    if (this.isMuted()) return 'skipped'
    const volume = resolveCueVolume(this.config, cue)
    if (volume <= 0) return 'skipped'
    const url = this.resolveAssetUrl(cue.assetName)
    if (!url) return 'unavailable'
    return { url, volume }
  }

  /** 设置源和音量并开始播放；同步拒绝在内部吞掉，不阻塞业务。 */
  private start(element: HTMLAudioElement, url: string, volume: number): boolean {
    try {
      element.muted = false
      element.volume = Math.min(1, Math.max(0, volume))
      element.src = url
      element.currentTime = 0
      const result = element.play()
      if (result && typeof result.catch === 'function') {
        void result.catch(() => {
          // 浏览器策略或解码失败只影响本次音效；保留元素供后续重试复用。
          this.stop(element)
        })
      }
      return true
    } catch {
      this.stop(element)
      return false
    }
  }

  /** 尽量暂停并归零；未加载元数据时忽略 currentTime 写入失败。 */
  private stop(element: HTMLAudioElement): void {
    try {
      element.pause()
      element.currentTime = 0
    } catch {
      // 未加载可定位媒体时浏览器可能拒绝写入 currentTime。
    }
  }
}
