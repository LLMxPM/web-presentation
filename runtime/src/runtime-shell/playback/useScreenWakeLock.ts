/**
 * 文件功能：在放映播放期间请求 Screen Wake Lock，并在不可见、权限拒绝、系统回收和卸载时安全收敛。
 * 能力缺失或拒绝时不影响普通放映，只在显式重新开始时再尝试。
 */
import { onBeforeUnmount, readonly, ref, type Ref } from 'vue'

export type WakeLockState = 'unsupported' | 'idle' | 'active' | 'denied' | 'error'

interface WakeLockSentinelLike {
  released: boolean
  release: () => Promise<void>
  addEventListener: (type: 'release', listener: () => void) => void
  removeEventListener: (type: 'release', listener: () => void) => void
}

interface WakeLockLike {
  request: (type: 'screen') => Promise<WakeLockSentinelLike>
}

export interface ScreenWakeLock {
  state: Readonly<Ref<WakeLockState>>
  request: () => void
  release: () => void
}

function resolveWakeLockApi(): WakeLockLike | null {
  if (typeof navigator === 'undefined') return null
  const api = (navigator as Navigator & { wakeLock?: WakeLockLike }).wakeLock
  return api && typeof api.request === 'function' ? api : null
}

function isPermissionDenied(error: unknown): boolean {
  const name = (error as { name?: unknown } | null)?.name
  return name === 'NotAllowedError' || name === 'SecurityError'
}

/**
 * 创建放映防休眠句柄。
 * request 只在播放中调用；release 必须在暂停、停止、失败和卸载时调用。
 */
export function useScreenWakeLock(): ScreenWakeLock {
  const api = resolveWakeLockApi()
  const state = ref<WakeLockState>(api ? 'idle' : 'unsupported')
  let desired = false
  let sentinel: WakeLockSentinelLike | null = null
  let requestSequence = 0
  let disposed = false

  /** 系统或浏览器回收锁后，在可见且仍播放时重新申请；隐藏期间交给恢复流程。 */
  function handleSentinelRelease(): void {
    sentinel = null
    if (disposed || !desired) {
      state.value = api ? 'idle' : 'unsupported'
      return
    }
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
      state.value = 'idle'
      return
    }
    void acquire()
  }

  /** 申请屏幕锁；并发请求以最新一次为准，过期 Promise 立即释放。 */
  async function acquire(): Promise<void> {
    if (!api || disposed || !desired) return
    if (sentinel && !sentinel.released) {
      state.value = 'active'
      return
    }
    const sequence = ++requestSequence
    try {
      const next = await api.request('screen')
      if (disposed || !desired || sequence !== requestSequence) {
        await next.release().catch(() => undefined)
        return
      }
      sentinel = next
      state.value = 'active'
      next.addEventListener('release', handleSentinelRelease)
    } catch (error) {
      if (disposed || sequence !== requestSequence) return
      sentinel = null
      state.value = isPermissionDenied(error) ? 'denied' : 'error'
    }
  }

  /** 播放状态进入可放映阶段时调用；权限拒绝后不在自动翻页中反复弹权限。 */
  function request(): void {
    if (disposed) return
    if (desired && (state.value === 'denied' || state.value === 'error')) return
    desired = true
    void acquire()
  }

  /** 暂停、停止、失败和卸载统一释放；下一次 request 会重新尝试申请。 */
  function release(): void {
    desired = false
    requestSequence += 1
    const current = sentinel
    sentinel = null
    state.value = api ? 'idle' : 'unsupported'
    if (current && !current.released) {
      current.removeEventListener('release', handleSentinelRelease)
      void current.release().catch(() => undefined)
    }
  }

  /** 页面重新可见且仍处于播放期望时补申请；隐藏时浏览器可能已自动释放。 */
  function handleVisibilityChange(): void {
    if (typeof document === 'undefined' || document.visibilityState === 'hidden') return
    if (((desired && !sentinel) || state.value === 'active') && state.value !== 'denied' && state.value !== 'error') {
      void acquire()
    }
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityChange)
  }
  onBeforeUnmount(() => {
    disposed = true
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
    release()
  })

  return { state: readonly(state) as Readonly<Ref<WakeLockState>>, request, release }
}
