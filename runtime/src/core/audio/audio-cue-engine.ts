/** 文件功能：维护 Deck 的切页 cue 单通道与有限交互池；播放、静音、音量和许可统一委托 AudioBus。 */
import { resolveAudioCue, type RuntimeAudioConfig } from './audio-config'
import type { AudioBus, AudioLease } from './audio-bus'

export type AudioCueResult = 'played' | 'skipped' | 'unavailable'
export interface AudioCueEngineOptions {
  bus: AudioBus
  config: RuntimeAudioConfig | (() => RuntimeAudioConfig)
  resolveAssetUrl(name: string): string | null
  allowPlayback: boolean
  createAudio?: () => HTMLAudioElement | null
  now?: () => number
}
interface CueSlot { element: HTMLAudioElement; lease: AudioLease; lastUsedAt: number; request: number }

/** 此类仅维护 cue 业务的通道选择与 80ms 节流，不拥有独立静音或浏览器许可状态。 */
export class AudioCueEngine {
  private transition: CueSlot | null = null
  private readonly interactions: CueSlot[] = []
  private readonly lastPlayed = new Map<string, number>()
  private suspended = false
  private disposed = false
  constructor(private readonly options: AudioCueEngineOptions) {}

  /** 新切页 cue 停止上一 cue，只有真实 play 成功才返回 played。 */
  async playTransition(key: string): Promise<AudioCueResult> {
    const cue = this.resolve(key)
    if (typeof cue === 'string') return cue
    this.transition ??= this.createSlot()
    if (!this.transition) return 'unavailable'
    this.stop(this.transition)
    return this.start(this.transition, cue)
  }
  /** 交互最多四个实例，池满复用最旧者；缺失绑定与受阻均不影响页面导航或完成。 */
  async playInteraction(key: string): Promise<AudioCueResult> {
    const cue = this.resolve(key)
    if (typeof cue === 'string') return cue
    const now = this.options.now?.() ?? Date.now(), previous = this.lastPlayed.get(key)
    if (previous !== undefined && now - previous < 80) return 'skipped'
    this.lastPlayed.set(key, now)
    let slot = this.interactions.find(slot => slot.element.paused || slot.element.ended)
    if (!slot && this.interactions.length < 4) { slot = this.createSlot() ?? undefined; if (slot) this.interactions.push(slot) }
    if (!slot) { slot = [...this.interactions].sort((a, b) => a.lastUsedAt - b.lastUsedAt)[0]; if (slot) this.stop(slot) }
    if (!slot) return 'unavailable'
    slot.lastUsedAt = now
    return this.start(slot, cue)
  }
  /** 交还当前放映 scope，不补播离开期间错过的 cue。 */
  suspend(): void { this.suspended = true; if (this.transition) this.stop(this.transition); this.interactions.forEach(slot => this.stop(slot)) }
  /** 仅恢复新 cue 资格。 */
  resume(): void { this.suspended = false }
  /** 释放本 Deck 的租约，不能销毁同窗口内容或 Scene 仍持有的总线通道。 */
  dispose(): void { if (this.disposed) return; this.disposed = true; this.suspend(); this.transition?.lease.release(); this.interactions.forEach(slot => slot.lease.release()); this.transition = null; this.interactions.length = 0; this.lastPlayed.clear() }

  /** 配置按当前项目读取，音量仅由总线计算一次。 */
  private resolve(key: string): { url: string; gain: number } | AudioCueResult {
    if (this.disposed || this.suspended || !this.options.allowPlayback || !this.options.bus.canPlay('deck')) return 'unavailable'
    const config = typeof this.options.config === 'function' ? this.options.config() : this.options.config
    const cue = resolveAudioCue(config, key)
    if (!cue) return 'unavailable'
    if (this.options.bus.muted.value || config.volume.master * config.volume.effects * cue.gain <= 0) return 'skipped'
    const url = this.options.resolveAssetUrl(cue.assetName)
    return url ? { url, gain: cue.gain } : 'unavailable'
  }
  /** 原生 Audio 只在真正请求 cue 时创建；静态和未绑定场景零创建。 */
  private createSlot(): CueSlot | null {
    const element = this.options.createAudio ? this.options.createAudio() : typeof Audio !== 'undefined' ? new Audio() : null
    return element ? { element, lease: this.options.bus.claim(element, { owner: 'deck', group: 'effects' }), lastUsedAt: 0, request: 0 } : null
  }
  /** cue 不登记自动媒体重试，播放许可失败只跳过本次，不阻塞 Scene。 */
  private async start(slot: CueSlot, cue: { url: string; gain: number }): Promise<AudioCueResult> {
    const token = ++slot.request
    slot.element.preload = 'auto'; slot.element.src = cue.url
    try { slot.element.currentTime = 0 } catch { /* 无定位数据时允许从资源起点加载。 */ }
    slot.lease.configure({ gain: cue.gain })
    const result = await slot.lease.play()
    if (token !== slot.request || this.disposed) return 'unavailable'
    if (result === 'played') return 'played'
    this.stop(slot); return result === 'unavailable' ? 'unavailable' : 'skipped'
  }
  /** 停止通过持有租约进行，不能抢占 Scene 或普通内容元素。 */
  private stop(slot: CueSlot): void { slot.request += 1; slot.lease.pause(); try { slot.element.currentTime = 0 } catch { /* 同上，定位失败不影响释放。 */ } }
}
