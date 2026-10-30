/** 文件功能：按窗口统一媒体所有权、音量、静音、播放许可及本地重试；不推测 play Promise 的结果。 */
import { ref, watch } from 'vue'
import { DEFAULT_RUNTIME_AUDIO_CONFIG, type RuntimeAudioConfig } from './audio-config'

export type AudioOwner = 'content' | 'scene' | 'deck'
export type AudioGroup = 'content' | 'narration' | 'effects'
export type AudioPlayResult = 'played' | 'blocked' | 'failed' | 'unavailable'
export interface AudioChannelOptions { owner: AudioOwner; group: AudioGroup; gain?: number; muted?: boolean }
export interface AudioLease {
  play(): Promise<AudioPlayResult>
  pause(): void
  configure(options: Partial<Pick<AudioChannelOptions, 'gain' | 'muted'>>): void
  release(): void
}
interface Channel { element: HTMLMediaElement; options: AudioChannelOptions; lease: AudioLease; permission: AudioPlayResult | 'unknown'; released: boolean; attempt: number; cancelWait?: () => void }
const managed = new WeakSet<HTMLMediaElement>()

/** 媒体守卫可跳过已被总线持有的元素，避免旧 DOM 协调器重复暂停/恢复。 */
export function isAudioBusManaged(element: HTMLMediaElement): boolean { return managed.has(element) }

/** 一条原生媒体只允许一个所有者；播放许可依据真实 Promise 回执，cue 与旁白不维护第二份静音状态。 */
export class AudioBus {
  readonly muted = ref(false)
  readonly state = ref<{ channels: number; blocked: number; suspended: boolean; permission: 'unknown' | AudioPlayResult }>({ channels: 0, blocked: 0, suspended: false, permission: 'unknown' })
  private readonly channels = new Map<HTMLMediaElement, Channel>()
  private readonly retries = new Map<AudioLease, () => Promise<void>>()
  private suspended = false
  private disposed = false
  private readonly stopMuteWatch: () => void

  constructor(private readonly options: { config?: () => RuntimeAudioConfig; allowed?: (owner: AudioOwner) => boolean } = {}) {
    this.stopMuteWatch = watch(this.muted, () => this.refresh(), { flush: 'sync' })
  }

  /** 声明资源所有权，不自动开始播放；静态执行由宿主 allowed 阻断。 */
  claim(element: HTMLMediaElement, input: AudioChannelOptions): AudioLease {
    if (this.disposed || this.channels.has(element) || managed.has(element)) throw new Error('媒体已经被其它所有者持有或 AudioBus 已释放。')
    const channel: Channel = { element, options: { ...input }, lease: null!, permission: 'unknown', released: false, attempt: 0 }
    const lease: AudioLease = {
      play: async () => {
        if (channel.released || this.disposed || this.suspended || this.options.allowed?.(input.owner) === false) return 'unavailable'
        channel.cancelWait?.()
        const attempt = ++channel.attempt
        const cancelled = new Promise<boolean>(resolve => { channel.cancelWait = () => resolve(false) })
        this.apply(channel)
        try {
          const success = await Promise.race([Promise.resolve(element.play()).then(() => true), cancelled])
          if (!success) return 'unavailable'
          if (channel.released || attempt !== channel.attempt || this.suspended || this.options.allowed?.(input.owner) === false) return 'unavailable'
          channel.permission = 'played'; this.publish(); return 'played'
        } catch (error) {
          if (channel.released || attempt !== channel.attempt) return 'unavailable'
          const name = error instanceof Error || error instanceof DOMException ? error.name : ''
          channel.permission = name === 'NotAllowedError' || name === 'AbortError' ? 'blocked' : 'failed'
          this.publish(); return channel.permission
        } finally {
          if (attempt === channel.attempt) channel.cancelWait = undefined
        }
      },
      pause: () => { channel.attempt += 1; channel.cancelWait?.(); channel.cancelWait = undefined; try { element.pause() } catch { /* 已释放的浏览器元素仍允许清理。 */ } },
      configure: value => { channel.options = { ...channel.options, ...value }; this.apply(channel) },
      release: () => {
        if (channel.released) return
        channel.released = true; lease.pause(); this.retries.delete(lease); this.channels.delete(element); managed.delete(element); this.publish()
      },
    }
    channel.lease = lease; this.channels.set(element, channel); managed.add(element); this.apply(channel); this.publish()
    return lease
  }

  /** 只登记仍属于当前 Scene 的本地恢复，离页 release 同时移除，旧 Promise 不会复活旧任务。 */
  setRetry(lease: AudioLease, retry: (() => Promise<void>) | null): void {
    if (retry && [...this.channels.values()].some(channel => channel.lease === lease && channel.options.owner === 'scene')) this.retries.set(lease, retry)
    else this.retries.delete(lease)
    this.publish()
  }

  /** 必须由当前 frame 的用户点击调用；在本次同步手势栈内发起所有原生 play，不借用跨窗口手势。 */
  async retryBlocked(): Promise<void> {
    if (this.disposed || this.suspended) return
    await Promise.allSettled([...this.retries.values()].map(retry => retry()))
  }

  /** 冻结暂停所有通道；恢复只恢复新播放资格，内容与错过的 cue 不补播。 */
  setSuspended(value: boolean): void {
    if (this.suspended === value) return
    this.suspended = value
    if (value) for (const channel of this.channels.values()) channel.lease.pause()
    this.publish()
  }
  /** 配置变化重算所有通道音量，不重建原生媒体或抢占所有权。 */
  refresh(): void { for (const channel of this.channels.values()) this.apply(channel); this.publish() }
  /** 停止某一层拥有的通道，普通内容用户控制与 Deck/Scene 互不抢占。 */
  stopOwner(owner: AudioOwner): void { for (const channel of [...this.channels.values()]) if (channel.options.owner === owner) channel.lease.pause() }
  /** 窗口销毁时统一清理；重复调用安全。 */
  dispose(): void { if (this.disposed) return; this.disposed = true; for (const channel of [...this.channels.values()]) channel.lease.release(); this.stopMuteWatch(); this.retries.clear() }

  /** master、分组与组件增益只在此相乘一次；页面静音与总线静音相或。 */
  private apply(channel: Channel): void {
    if (channel.released) return
    const config = this.options.config?.() ?? DEFAULT_RUNTIME_AUDIO_CONFIG
    const gain = channel.options.gain ?? 1
    const group = channel.options.group === 'narration' ? config.volume.narration : channel.options.group === 'effects' ? config.volume.effects : 1
    const volume = config.volume.master * group * gain
    channel.element.volume = Number.isFinite(volume) ? Math.min(1, Math.max(0, volume)) : 0
    channel.element.muted = this.muted.value || Boolean(channel.options.muted)
  }
  /** 状态有界，不回传元素、URL、凭证或任意浏览器错误。 */
  private publish(): void {
    const permissions = [...this.channels.values()].map(channel => channel.permission)
    const permission = permissions.includes('blocked') ? 'blocked' : permissions.includes('failed') ? 'failed' : permissions.includes('played') ? 'played' : 'unknown'
    this.state.value = { channels: this.channels.size, blocked: this.retries.size, suspended: this.suspended, permission }
  }
}
