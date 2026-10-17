/**
 * 文件功能：原生媒体基础守卫与放映暂停/恢复协调器。
 * 守卫按元素最近的 data-runtime-media 作用域阻断自动播放；协调器只恢复
 * 暂停前确实在播放的媒体，不启动用户手动暂停的元素。
 */
import type { MediaPlaybackMode } from './execution-policy'

export interface MediaPlaybackGuardOptions {
  root?: Document | HTMLElement
  fallbackMode?: MediaPlaybackMode
  now?: () => number
  gestureWindowMs?: number
}

/**
 * 安装文档级媒体播放守卫。
 * 在应用挂载前调用，监听后创建的媒体元素；返回清理函数。
 */
export function installMediaPlaybackGuard(options: MediaPlaybackGuardOptions = {}): () => void {
  const root = options.root ?? (typeof document !== 'undefined' ? document : null)
  if (!root || typeof HTMLMediaElement === 'undefined') return () => {}
  const now = options.now ?? (() => (typeof performance !== 'undefined' ? performance.now() : Date.now()))
  const gestureWindowMs = options.gestureWindowMs ?? 1000
  const fallbackMode = options.fallbackMode ?? 'allow'
  let lastGestureAt = Number.NEGATIVE_INFINITY

  /** 用户手势窗口用于区分自动播放与点击播放；浏览器提供 userActivation 时以其为准。 */
  function markGesture(): void {
    lastGestureAt = now()
  }

  function hasUserActivation(): boolean {
    const activation = (navigator as Navigator & { userActivation?: { isActive?: boolean } }).userActivation
    return Boolean(activation?.isActive) || now() - lastGestureAt <= gestureWindowMs
  }

  function resolveMode(element: Element): MediaPlaybackMode {
    const scope = element.closest('[data-runtime-media]')
    const value = scope?.getAttribute('data-runtime-media')
    if (value === 'allow' || value === 'gesture' || value === 'block') return value
    return fallbackMode
  }

  function handlePlay(event: Event): void {
    const element = event.target
    if (!(element instanceof HTMLMediaElement)) return
    const mode = resolveMode(element)
    if (mode === 'allow') return
    if (mode === 'gesture' && hasUserActivation()) return
    element.pause()
    if (element.hasAttribute('autoplay')) element.removeAttribute('autoplay')
  }

  root.addEventListener('play', handlePlay, true)
  root.addEventListener('pointerdown', markGesture, true)
  root.addEventListener('touchstart', markGesture, true)
  root.addEventListener('keydown', markGesture, true)

  return () => {
    root.removeEventListener('play', handlePlay, true)
    root.removeEventListener('pointerdown', markGesture, true)
    root.removeEventListener('touchstart', markGesture, true)
    root.removeEventListener('keydown', markGesture, true)
  }
}

export interface MediaPlaybackCoordinator {
  suspend(target?: ParentNode | null): number
  resume(): number
  isSuspended(): boolean
  dispose(): void
}

/**
 * 创建放映会话级媒体协调器。
 * suspend 记录当前正在播放的原生音视频并暂停；resume 只重放该记录集合。
 */
export function createMediaPlaybackCoordinator(): MediaPlaybackCoordinator {
  let recorded: HTMLMediaElement[] = []
  let suspended = false

  function suspend(target: ParentNode | null = typeof document !== 'undefined' ? document : null): number {
    if (suspended) return recorded.length
    if (!target) return 0
    recorded = [...target.querySelectorAll<HTMLMediaElement>('audio, video')]
      .filter(element => !element.paused && !element.ended)
    for (const element of recorded) element.pause()
    suspended = true
    return recorded.length
  }

  function resume(): number {
    if (!suspended) return 0
    const elements = recorded
    recorded = []
    suspended = false
    let resumed = 0
    for (const element of elements) {
      if (!element.isConnected || element.ended) continue
      resumed += 1
      try {
        void Promise.resolve(element.play()).catch(() => {})
      } catch {
        // 同步拒绝同样视为恢复失败，等待用户手动播放。
      }
    }
    return resumed
  }

  function dispose(): void {
    recorded = []
    suspended = false
  }

  return { suspend, resume, isSuspended: () => suspended, dispose }
}

/** Runtime 会话共用实例；媒体生命周期工作包在页面离开时调用 suspend/dispose。 */
export const mediaPlaybackCoordinator = createMediaPlaybackCoordinator()
