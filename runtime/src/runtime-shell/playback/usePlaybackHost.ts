/**
 * 文件功能：把放映控制器接入 Router 会话、页面目录、过渡完成信号与视觉资源就绪。
 * 只有路由提交、过渡结束且当前页必要资源就绪后才上报 ready；旧页面、旧 generation
 * 和卸载后的探测结果都不会启动计时。
 */
import { nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { getRuntimeSession, navigateRuntimePage } from '@/core/router/runtime-session'
import { playbackConfig } from '@/core/utils/config'
import { getRouteInfosSortedByPageNumber } from '@/core/utils/route-generator'
import { resolvePageAdvance } from '@/core/utils/page-transition'
import { waitForEditorVisualAssets } from '@/core/utils/visual-assets'
import { useRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { shouldStartAutomatically } from '@/core/execution/execution-policy'
import { mediaPlaybackCoordinator } from '@/core/execution/media-playback-guard'
import { createPageMediaSession, type PageMediaEvent, type PageMediaSession } from '@/core/media/page-media-session'
import { PlaybackController, type PlaybackPage, type PlaybackSnapshot } from './playback-controller'

const PLAYBACK_READY_TIMEOUT_MS = 15000
const PAGE_MISSING_MESSAGE = '页面节点未就绪，自动放映已暂停。'
const PAGE_ASSET_MESSAGE = '页面资源未就绪，自动放映已暂停。'
const MEDIA_BLOCKED_MESSAGE = '浏览器阻止了媒体播放，请重试、跳到下一页或停止放映。'

interface ReadinessAttempt {
  id: number
  path: string
  generation: number
  settled: boolean
}

export interface PlaybackHost {
  snapshot: Ref<PlaybackSnapshot | null>
  errorMessage: Ref<string>
  start: () => boolean
  pause: () => boolean
  resume: () => boolean
  stop: () => boolean
  retry: () => boolean
  /** 失败态跳到下一页；没有下一页时返回 false。 */
  next: () => boolean
  /** 按控制器单调时钟刷新剩余时间，供控制条定时读取。 */
  refresh: () => void
}

export interface PlaybackHostOptions {
  /** 观众窗口由控制台命令启动，不执行项目 auto_start。 */
  autoStart?: boolean
}

/**
 * 从现有可见叶子目录构建放映序列，不创建第二套路由目录。
 * pageNumber 由现有配置转换器只分配给可见叶子页，隐藏页与分组自然排除。
 */
export function buildPlaybackPages(): PlaybackPage[] {
  return getRouteInfosSortedByPageNumber().map(info => ({
    path: info.path,
    advance: resolvePageAdvance(info.advance),
  }))
}

/** 查找当前稳定页面的真实 DOM 根；过渡结束后只应存在目标层。 */
export function findPlaybackPageElement(path: string): HTMLElement | null {
  if (typeof document === 'undefined') return null
  return Array.from(document.querySelectorAll<HTMLElement>('.runtime-page-print-source'))
    .find(element => element.dataset.runtimeRoutePath === path) ?? null
}

/**
 * 在放映主画布宿主中创建调度链路。
 * 非 presentation 上下文（卡片、缩略图、捕获等）不会创建控制器或计时句柄。
 */
export function usePlaybackHost(options: PlaybackHostOptions = {}): PlaybackHost {
  const router = useRouter()
  const session = getRuntimeSession(router)
  const policy = useRuntimeExecutionPolicy()
  const controller = shallowRef<PlaybackController | null>(null)
  const snapshot = ref<PlaybackSnapshot | null>(null)
  const errorMessage = ref('')
  let unsubscribe: (() => void) | null = null
  let pendingAttempt: ReadinessAttempt | null = null
  let attemptSequence = 0
  let disposed = false
  let mediaSession: PageMediaSession | null = null
  let mediaPath = ''
  let mediaSessionGeneration = -1

  /** 按当前执行策略惰性创建控制器；目录为空时不创建。 */
  function ensureController(): PlaybackController | null {
    if (disposed || !policy.value.allowAutoAdvance || !playbackConfig.value.supported) return null
    if (controller.value) return controller.value
    const pages = buildPlaybackPages()
    if (pages.length === 0) return null
    const instance = new PlaybackController({
      pages,
      loop: playbackConfig.value.loop,
      initialPath: router.currentRoute.value.path,
      navigate: path => navigateRuntimePage(router, path),
    })
    unsubscribe = instance.subscribe(next => {
      snapshot.value = next
      errorMessage.value = next.state === 'error' || next.state === 'blocked' ? next.message : ''
      syncMediaWithSnapshot(instance, next)
    })
    snapshot.value = instance.getSnapshot()
    controller.value = instance
    return instance
  }

  /** 只暂停当前放映页内正在播放的媒体，避免影响侧栏缩略图等其他区域。 */
  function suspendPageMedia(): void {
    const path = controller.value?.getSnapshot().path
    const root = path ? findPlaybackPageElement(path) : null
    if (root) mediaPlaybackCoordinator.suspend(root)
  }

  /** 释放当前页媒体会话；离场、失败与控制器销毁都必须先停播。 */
  function disposePageMedia(): void {
    mediaSession?.dispose()
    mediaSession = null
    mediaPath = ''
    mediaSessionGeneration = -1
  }

  /**
   * 媒体会话事件进入控制器；路径与 generation 必须同时匹配当前页，
   * 旧页、已销毁会话和迟到事件直接丢弃。
   */
  function handleMediaEvent(event: PageMediaEvent): void {
    const session = mediaSession
    const instance = controller.value
    if (!session || !instance) return
    const current = instance.getSnapshot()
    if (current.path !== mediaPath || current.generation !== event.generation) return
    if (event.type === 'error') {
      session.pause()
      instance.reportMediaError(mediaPath, event.generation, event.message)
      return
    }
    if (event.type === 'blocked') {
      session.pause()
      instance.reportMediaBlocked(mediaPath, event.generation, MEDIA_BLOCKED_MESSAGE)
      return
    }
    if (current.state !== 'playing') return
    if (event.type !== 'ended' && event.type !== 'targets') return
    const media = session.getSnapshot()
    if (media.targets.length === 0) {
      instance.reportMediaEmpty(mediaPath, event.generation)
      return
    }
    if (media.allEnded) {
      instance.reportMediaEnded(mediaPath, event.generation)
      return
    }
    if (event.type === 'targets') {
      if (!current.waitingForMedia) {
        instance.reportMediaTargets(mediaPath, event.generation, media.targets.length)
      }
      void playPageMedia(session)
    }
  }

  /** 主动播放当前页媒体；Promise 结果区分阻止、失败与真实成功，不推断 autoplay。 */
  async function playPageMedia(session: PageMediaSession, restart = false): Promise<void> {
    const instance = controller.value
    if (!instance || mediaSession !== session) return
    const path = mediaPath
    if (instance.getSnapshot().state !== 'playing') return
    const result = restart ? await session.restart() : await session.play()
    if (mediaSession !== session || controller.value !== instance) return
    const current = instance.getSnapshot()
    if (current.path !== path || current.generation !== session.generation) return
    if (result.blocked) {
      session.pause()
      instance.reportMediaBlocked(path, session.generation, MEDIA_BLOCKED_MESSAGE)
      return
    }
    const failed = result.attempts.find(attempt => attempt.outcome === 'error')
    if (failed) {
      session.pause()
      instance.reportMediaError(path, session.generation, failed.message)
      return
    }
    if (session.getSnapshot().allEnded) {
      instance.reportMediaEnded(path, session.generation)
    }
  }

  /** 为当前页创建媒体会话；构造期间的上报由显式 play 调用补足。 */
  function createSessionForPage(root: HTMLElement, path: string, generation: number): PageMediaSession {
    disposePageMedia()
    mediaPath = path
    mediaSessionGeneration = generation
    mediaSession = createPageMediaSession({
      root,
      generation,
      allowPlayback: policy.value.allowAutoplay,
      onEvent: handleMediaEvent,
    })
    return mediaSession
  }

  /** 单页循环或停止后重新开始时重建会话；已结束媒体先归零再播放。 */
  function restartPageMedia(instance: PlaybackController, next: PlaybackSnapshot): void {
    const root = findPlaybackPageElement(next.path)
    if (!root) return
    const session = createSessionForPage(root, next.path, next.generation)
    const media = session.getSnapshot()
    instance.reportMediaTargets(next.path, next.generation, media.targets.length)
    const shouldRestart = media.targets.length > 0 && media.targets.every(target => target.ended)
    void playPageMedia(session, shouldRestart)
  }

  /** 控制器状态变化时同步媒体：失败先停播，离场销毁，同页新一代播放重建会话。 */
  function syncMediaWithSnapshot(instance: PlaybackController, next: PlaybackSnapshot): void {
    if (next.state === 'blocked' || next.state === 'error') {
      mediaSession?.pause()
      return
    }
    if (next.state === 'stopped' || next.state === 'ended') {
      disposePageMedia()
      return
    }
    if (next.state !== 'playing' || next.advanceMode !== 'media_end') return
    if (next.generation === mediaSessionGeneration) return
    const generation = next.generation
    queueMicrotask(() => {
      const current = controller.value?.getSnapshot()
      if (!current || current.state !== 'playing' || current.generation !== generation) return
      restartPageMedia(instance, current)
    })
  }

  function disposeController(): void {
    suspendPageMedia()
    disposePageMedia()
    pendingAttempt = null
    attemptSequence += 1
    unsubscribe?.()
    unsubscribe = null
    controller.value?.dispose()
    controller.value = null
    snapshot.value = null
    errorMessage.value = ''
    mediaPlaybackCoordinator.dispose()
  }

  /** 判断探测结果是否仍属于当前页面、generation 与最新一次尝试。 */
  function isAttemptCurrent(attempt: ReadinessAttempt, instance: PlaybackController | null): boolean {
    if (disposed || !instance || controller.value !== instance) return false
    if (pendingAttempt?.id !== attempt.id) return false
    const current = instance.getSnapshot()
    return current.path === attempt.path && current.generation === attempt.generation
  }

  /** 在过渡结束、DOM 提交后探测当前页资源，再上报就绪或可见错误。 */
  async function probeAndReport(attempt: ReadinessAttempt): Promise<void> {
    const instance = controller.value
    if (!isAttemptCurrent(attempt, instance)) return
    await nextTick()
    if (!isAttemptCurrent(attempt, instance)) return
    const root = findPlaybackPageElement(attempt.path)
    if (!root) {
      pendingAttempt = null
      instance?.reportError(attempt.path, attempt.generation, PAGE_MISSING_MESSAGE)
      return
    }
    const result = await waitForEditorVisualAssets({
      root,
      timeoutMs: PLAYBACK_READY_TIMEOUT_MS,
      includeAnimations: false,
    })
    if (!isAttemptCurrent(attempt, instance)) return
    pendingAttempt = null
    if (result.ok) {
      const current = instance?.getSnapshot()
      if (instance && current?.advanceMode === 'media_end') {
        const session = createSessionForPage(root, attempt.path, attempt.generation)
        const targetCount = session.getSnapshot().targets.length
        instance.reportReady(attempt.path, attempt.generation, targetCount)
        if (targetCount > 0) void playPageMedia(session)
      } else {
        disposePageMedia()
        instance?.reportReady(attempt.path, attempt.generation)
      }
      return
    }
    const issue = result.failed[0] || result.pending[0]
    instance?.reportError(
      attempt.path,
      attempt.generation,
      issue?.message ? `${PAGE_ASSET_MESSAGE}（${issue.message}）` : PAGE_ASSET_MESSAGE,
    )
  }

  /**
   * 开始一次页面就绪等待。
   * acceptCurrentSettled 用于启动/恢复/重试当前页：此时已有稳定页，可复用最近一次 settled；
   * 路由切换必须等待新的 settled，避免旧页完成事件启动新页计时。
   */
  function beginReadiness(path: string, acceptCurrentSettled: boolean): void {
    const instance = controller.value
    if (!instance) return
    const current = instance.getSnapshot()
    if (current.path !== path) return
    const attempt: ReadinessAttempt = {
      id: ++attemptSequence,
      path,
      generation: current.generation,
      settled: false,
    }
    pendingAttempt = attempt
    const settled = session.transitionSettled.value
    if (acceptCurrentSettled && settled?.path === path) {
      attempt.settled = true
      void probeAndReport(attempt)
    }
  }

  const stopRouteWatch = watch(() => router.currentRoute.value.path, path => {
    const instance = controller.value
    if (!instance) return
    disposePageMedia()
    if (!instance.notifyPageChange(path)) return
    const state = instance.getSnapshot().state
    if (state === 'preparing' || state === 'paused') beginReadiness(path, false)
  })

  const stopSettledWatch = watch(() => session.transitionSettled.value, event => {
    if (!event) return
    const attempt = pendingAttempt
    if (!attempt || attempt.settled || attempt.path !== event.path) return
    attempt.settled = true
    void probeAndReport(attempt)
  })

  const stopNavigationErrorWatch = watch(() => session.navigationError.value, message => {
    if (!message) return
    const instance = controller.value
    if (!instance) return
    const current = instance.getSnapshot()
    if (current.state !== 'preparing' && current.state !== 'playing') return
    pendingAttempt = null
    instance.reportError(current.path, current.generation, message)
  })

  const stopPolicyWatch = watch(() => policy.value.allowAutoAdvance, allowed => {
    if (allowed) ensureController()
    else disposeController()
  }, { immediate: true })

  /** 开始当前页放映；失败时不创建重复计时。 */
  function startPlayback(): boolean {
    const instance = ensureController()
    if (!instance || !instance.start()) return false
    beginReadiness(instance.getSnapshot().path, true)
    return true
  }

  function pausePlayback(): boolean {
    if (!controller.value?.pause()) return false
    if (mediaSession) mediaSession.suspend()
    else suspendPageMedia()
    return true
  }

  function resumePlayback(): boolean {
    const instance = controller.value
    if (!instance || !instance.resume()) return false
    const current = instance.getSnapshot()
    if (current.state === 'playing' && current.advanceMode === 'media_end') {
      if (mediaSession?.isSuspended()) mediaSession.resume()
      else if (mediaSession) void playPageMedia(mediaSession)
      else restartPageMedia(instance, current)
    } else {
      mediaPlaybackCoordinator.resume()
    }
    if (current.state === 'preparing') beginReadiness(instance.getSnapshot().path, true)
    return true
  }

  function stopPlayback(): boolean {
    if (!controller.value?.stop()) return false
    if (mediaSession) disposePageMedia()
    else suspendPageMedia()
    mediaPlaybackCoordinator.dispose()
    return true
  }

  function retryPlayback(): boolean {
    const instance = controller.value
    if (!instance || !instance.retry()) return false
    disposePageMedia()
    beginReadiness(instance.getSnapshot().path, true)
    return true
  }

  /** 失败态跳到下一页；清掉旧媒体后重新等待目标页就绪。 */
  function nextPlayback(): boolean {
    const instance = controller.value
    if (!instance || !instance.next()) return false
    disposePageMedia()
    mediaPlaybackCoordinator.dispose()
    beginReadiness(instance.getSnapshot().path, false)
    return true
  }

  /** 窗口隐藏时暂停并保留剩余时间；重新可见后等待用户显式继续，不补课。 */
  function handleVisibilityChange(): void {
    if (!document.hidden) return
    const instance = controller.value
    if (!instance) return
    const state = instance.getSnapshot().state
    if (state === 'playing' || state === 'preparing') pausePlayback()
  }

  /**
   * 空格键在放映主画布中切换开始/暂停/继续。
   * 捕获阶段处理后阻止传播，避免与布局层的空格翻页快捷键重复触发。
   */
  function handlePlaybackKeydown(event: KeyboardEvent): void {
    if (event.repeat || event.key !== ' ' || event.altKey || event.ctrlKey || event.metaKey) return
    const target = event.target as HTMLElement | null
    if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return
    const instance = controller.value
    if (!instance) return
    const state = instance.getSnapshot().state
    let handled = false
    if (state === 'stopped' || state === 'ended' || state === 'error' || state === 'blocked') {
      handled = startPlayback()
    } else if (state === 'playing' || state === 'preparing') {
      handled = pausePlayback()
    } else if (state === 'paused') {
      handled = resumePlayback()
    }
    if (!handled) return
    event.preventDefault()
    event.stopImmediatePropagation()
  }

  onMounted(() => {
    document.addEventListener('visibilitychange', handleVisibilityChange)
    document.addEventListener('keydown', handlePlaybackKeydown, true)
    if (disposed || session.autoStartAttempted.value) return
    session.autoStartAttempted.value = true
    if (options.autoStart === false) return
    const instance = ensureController()
    if (!instance) return
    if (!shouldStartAutomatically(policy.value, playbackConfig.value.autoStart)) return
    if (instance.start()) beginReadiness(instance.getSnapshot().path, true)
  })

  onBeforeUnmount(() => {
    disposed = true
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    document.removeEventListener('keydown', handlePlaybackKeydown, true)
    stopRouteWatch()
    stopSettledWatch()
    stopNavigationErrorWatch()
    stopPolicyWatch()
    disposeController()
  })

  return {
    snapshot,
    errorMessage,
    start: startPlayback,
    pause: pausePlayback,
    resume: resumePlayback,
    stop: stopPlayback,
    retry: retryPlayback,
    next: nextPlayback,
    refresh: () => {
      const instance = controller.value
      if (instance) snapshot.value = instance.getSnapshot()
    },
  }
}
