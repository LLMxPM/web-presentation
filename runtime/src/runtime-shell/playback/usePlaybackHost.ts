/**
 * 文件功能：把放映控制器接入 Router 会话、页面目录、过渡完成信号与视觉资源就绪。
 * 只有路由提交、过渡结束且当前页必要资源就绪后才上报 ready；旧页面、旧 generation
 * 和卸载后的探测结果都不会启动计时。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch, type ComputedRef, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { getRuntimeSession, navigateRuntimePage } from '@/core/router/runtime-session'
import { playbackConfig } from '@/core/utils/config'
import { getRouteInfosSortedByPageNumber } from '@/core/utils/route-generator'
import { resolvePageAdvance } from '@/core/utils/page-transition'
import { waitForEditorVisualAssets } from '@/core/utils/visual-assets'
import { useRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { mediaPlaybackCoordinator } from '@/core/execution/media-playback-guard'
import {
  createPageMediaSession,
  type PageMediaEvent,
  type PageMediaSession,
  type PageMediaSnapshot,
} from '@/core/media/page-media-session'
import { findPageMotionHandle, type PageMotionHandle } from '@/core/motion/page-motion-contract'
import type { CompiledMotionPlan, MotionTransportSnapshot } from '@/core/motion/types'
import { PlaybackController, type PlaybackPage, type PlaybackSnapshot } from './playback-controller'
import { useScreenWakeLock, type WakeLockState } from './useScreenWakeLock'

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
  /** Screen Wake Lock 状态；不支持或拒绝时放映仍正常进行。 */
  wakeLockState: Readonly<Ref<WakeLockState>>
  /** 会话级静音；不写回项目配置。 */
  muted: Readonly<Ref<boolean>>
  canGoPrevious: ComputedRef<boolean>
  /** 失败态允许跳过当前页；循环时末页也允许。 */
  canGoNext: ComputedRef<boolean>
  start: () => boolean
  pause: () => boolean
  resume: () => boolean
  stop: () => boolean
  retry: () => boolean
  /** 失败态跳到下一页；没有下一页时返回 false。 */
  next: () => boolean
  /** 手动翻页；失败态等价于跳到下一页。 */
  goPrevious: () => boolean
  goNext: () => boolean
  /** 切换本次放映的自动推进；关闭时媒体继续但页面等待用户翻页。 */
  setAutoAdvance: (enabled: boolean) => boolean
  toggleAutoAdvance: () => boolean
  /** 切换会话静音；当前页与后续页的新媒体继承该状态。 */
  toggleMute: () => boolean
  /** 按控制器单调时钟刷新剩余时间，供控制条定时读取。 */
  refresh: () => void
  /** 当前页时间轴快照；没有时间轴时为 null。 */
  motion: Readonly<Ref<MotionTransportSnapshot | null>>
  motionPlan: Readonly<Ref<CompiledMotionPlan | null>>
  /** 定位当前页时间轴；旧页面或未准备时返回 false。 */
  seekMotion: (positionMs: number) => Promise<boolean>
}

export interface PlaybackHostOptions {
  /** 挂载时是否立即启动会话；默认 false，由全屏放映壳显式开启。 */
  autoStart?: boolean
  /** 会话初始自动推进状态；全屏放映由项目 auto_start 决定。 */
  initialAutoAdvance?: boolean
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

/** 只保留参与完成判定的媒体；循环背景与冲突旁白不阻塞 media_end。 */
function participatingTargets(media: PageMediaSnapshot) {
  return media.targets.filter(target => target.participating)
}

/** 当前页所有参与媒体是否都已结束；没有参与媒体时不视为完成。 */
function allParticipatingEnded(media: PageMediaSnapshot): boolean {
  const targets = participatingTargets(media)
  return targets.length > 0 && targets.every(target => target.ended)
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
  const wakeLock = useScreenWakeLock()
  const muted = session.audioMuted
  const motion = ref<MotionTransportSnapshot | null>(null)
  const motionPlan = shallowRef<CompiledMotionPlan | null>(null)
  let unsubscribe: (() => void) | null = null
  let pendingAttempt: ReadinessAttempt | null = null
  let attemptSequence = 0
  let disposed = false
  let mediaSession: PageMediaSession | null = null
  let mediaPath = ''
  let mediaSessionGeneration = -1
  let motionHandle: PageMotionHandle | null = null
  let motionPath = ''
  let motionGeneration = -1
  let motionUnsubscribe: (() => void) | null = null

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
      autoAdvance: options.initialAutoAdvance ?? true,
      navigate: path => navigateRuntimePage(router, path),
    })
    unsubscribe = instance.subscribe(next => {
      snapshot.value = next
      errorMessage.value = next.state === 'error' || next.state === 'blocked' ? next.message : ''
      syncWakeLock(next)
      syncMediaWithSnapshot(next)
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

  /** 释放页面时间轴句柄引用；transport 由页面组件持有，宿主不 dispose。 */
  function disposePageMotion(): void {
    motionUnsubscribe?.()
    motionUnsubscribe = null
    motionHandle?.pause()
    motionHandle = null
    motionPath = ''
    motionGeneration = -1
    motion.value = null
    motionPlan.value = null
  }

  /** 读取页面根注册的时间轴句柄并订阅状态；旧页面句柄不保留。 */
  function attachPageMotion(root: HTMLElement, path: string, generation: number): PageMotionHandle | null {
    disposePageMotion()
    const handle = findPageMotionHandle(root)
    if (!handle) return null
    motionHandle = handle
    motionPath = path
    motionGeneration = generation
    motionPlan.value = handle.plan
    motion.value = handle.getSnapshot()
    handle.setMuted(muted.value)
    let lastPhase = motion.value.phase
    motionUnsubscribe = handle.subscribe(snapshot => {
      if (!motionHandle || motionPath !== path || motionGeneration !== generation) return
      motion.value = snapshot
      const instance = controller.value
      const current = instance?.getSnapshot()
      if (!instance || !current || current.path !== path || current.generation !== generation) return
      if (snapshot.phase !== lastPhase) {
        // 缓冲期间冻结 timeline_end 超时预算，恢复后继续使用剩余预算。
        if (snapshot.phase === 'buffering') {
          instance.reportTimelineBuffering(path, generation, true)
        } else if (lastPhase === 'buffering') {
          instance.reportTimelineBuffering(path, generation, false)
        }
        lastPhase = snapshot.phase
      }
      if (snapshot.phase === 'completed') {
        if (current.advanceMode === 'timeline_end') instance.reportTimelineEnded(path, generation)
        return
      }
      if (snapshot.phase === 'blocked') {
        instance.reportBlocked(path, generation, snapshot.errorMessage || MEDIA_BLOCKED_MESSAGE)
        return
      }
      if (snapshot.phase === 'error') {
        instance.reportError(path, generation, snapshot.errorMessage || '页内时间轴执行失败。')
      }
    })
    return handle
  }

  /** 按当前放映状态启停页面时间轴；浏览器拒绝时进入统一受阻态。 */
  async function playPageMotion(handle: PageMotionHandle, path: string, generation: number): Promise<void> {
    const instance = controller.value
    const current = instance?.getSnapshot()
    if (!instance || !current || current.path !== path || current.generation !== generation) return
    try {
      await handle.play()
    } catch (error) {
      if (motionHandle !== handle || motionPath !== path || motionGeneration !== generation) return
      const latest = instance.getSnapshot()
      if (latest.path !== path || latest.generation !== generation) return
      const message = error instanceof Error ? error.message : '页内时间轴播放失败。'
      if ((error as { code?: string }).code === 'TIMELINE_MEDIA_BLOCKED') {
        instance.reportBlocked(path, generation, message)
      } else {
        instance.reportError(path, generation, message)
      }
      return
    }
    if (motionHandle !== handle || motionPath !== path || motionGeneration !== generation) return
    const snapshot = handle.getSnapshot()
    motion.value = snapshot
    if (snapshot.phase === 'blocked') {
      instance.reportBlocked(path, generation, snapshot.errorMessage || MEDIA_BLOCKED_MESSAGE)
    } else if (snapshot.phase === 'error') {
      instance.reportError(path, generation, snapshot.errorMessage || '页内时间轴执行失败。')
    }
  }

  /** 控制器 generation 变化（单页循环/重试/重新开始）时重新驱动同一页面时间轴。 */
  function syncMotionWithSnapshot(next: PlaybackSnapshot): void {
    if (!motionHandle || next.path !== motionPath) return
    if (next.generation !== motionGeneration) {
      motionGeneration = next.generation
      if (next.state === 'playing') void playPageMotion(motionHandle, next.path, next.generation)
      return
    }
    if (next.state === 'paused' || next.state === 'blocked' || next.state === 'error'
      || next.state === 'stopped' || next.state === 'ended') {
      motionHandle.pause()
    }
  }

  async function seekMotion(positionMs: number): Promise<boolean> {
    const instance = controller.value
    const current = instance?.getSnapshot()
    if (!motionHandle || !current) return false
    if (current.path !== motionPath || current.generation !== motionGeneration) return false
    if (!Number.isFinite(positionMs)) return false
    await motionHandle.seek(positionMs)
    motion.value = motionHandle.getSnapshot()
    return true
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
    if (event.type === 'contract-error') {
      session.pause()
      instance.reportMediaError(mediaPath, event.generation, event.message || MEDIA_BLOCKED_MESSAGE)
      return
    }
    if (event.type === 'error') {
      // manual/timer 下的内容音频由用户控制，单个资源失败不应阻塞整场放映；
      // 旁白与 media_end 参与媒体仍进入统一错误链路。
      const failed = session.getSnapshot().targets.find(target => target.id === event.targetId)
      if (current.advanceMode !== 'media_end' && current.advanceMode !== 'timeline_end' && failed?.purpose !== 'narration') return
      session.pause()
      instance.reportMediaError(mediaPath, event.generation, event.message || MEDIA_BLOCKED_MESSAGE)
      return
    }
    if (event.type === 'blocked') {
      session.pause()
      instance.reportMediaBlocked(mediaPath, event.generation, MEDIA_BLOCKED_MESSAGE)
      return
    }
    if (current.state !== 'playing') return
    if (event.type !== 'ended' && event.type !== 'targets') return
    // 只有 media_end 页面由媒体完成集合推进；manual/timer 页面旁白结束不改变推进。
    if (current.advanceMode !== 'media_end') return
    const media = session.getSnapshot()
    const participating = participatingTargets(media)
    if (participating.length === 0) {
      instance.reportMediaEmpty(mediaPath, event.generation)
      return
    }
    if (allParticipatingEnded(media)) {
      instance.reportMediaEnded(mediaPath, event.generation)
      return
    }
    if (event.type === 'targets') {
      if (!current.waitingForMedia) {
        instance.reportMediaTargets(mediaPath, event.generation, participating.length)
      }
      void playPageMedia(session)
    }
  }

  /** 主动播放当前页媒体；Promise 结果区分阻止、失败与真实成功，不推断 autoplay。 */
  async function playPageMedia(
    session: PageMediaSession,
    options: { restart?: boolean; autoplayOnly?: boolean } = {},
  ): Promise<void> {
    const instance = controller.value
    if (!instance || mediaSession !== session) return
    const path = mediaPath
    if (instance.getSnapshot().state !== 'playing') return
    const result = options.restart
      ? await session.restart()
      : options.autoplayOnly
        ? await session.playAutoplay()
        : await session.play()
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
    if (!options.autoplayOnly && allParticipatingEnded(session.getSnapshot())) {
      instance.reportMediaEnded(path, session.generation)
    }
  }

  /** 为当前页创建媒体会话；构造期间的上报由显式 play 调用补足。 */
  function createSessionForPage(
    root: HTMLElement,
    path: string,
    generation: number,
    motion: PageMotionHandle | null = null,
  ): PageMediaSession {
    disposePageMedia()
    mediaPath = path
    mediaSessionGeneration = generation
    mediaSession = createPageMediaSession({
      root,
      generation,
      allowPlayback: policy.value.allowAutoplay,
      onEvent: handleMediaEvent,
      // 已由时间轴认领的媒体只交给 transport，旧会话不得暂停、归零或计入完成集合。
      isExternallyOwned: element => motion?.isElementClaimed(element) ?? false,
    })
    mediaSession.setMuted(muted.value)
    return mediaSession
  }

  /** 单页循环或停止后重新开始时重建会话；已结束媒体先归零再播放。 */
  function restartPageMedia(instance: PlaybackController, next: PlaybackSnapshot): void {
    const root = findPlaybackPageElement(next.path)
    if (!root) return
    const session = createSessionForPage(root, next.path, next.generation, motionHandle)
    const media = session.getSnapshot()
    const participating = participatingTargets(media)
    instance.reportMediaTargets(next.path, next.generation, participating.length)
    const shouldRestart = participating.length > 0 && participating.every(target => target.ended)
    void playPageMedia(session, { restart: shouldRestart })
  }

  /** 自动翻页的准备阶段保持申请，避免逐页释放/重试；暂停、失败、结束和停止立即释放。 */
  function syncWakeLock(next: PlaybackSnapshot): void {
    if ((next.state === 'playing' || next.state === 'preparing') && policy.value.allowAutoAdvance) {
      wakeLock.request()
    } else {
      wakeLock.release()
    }
  }

  /** 控制器状态变化时同步媒体：失败先停播，离场销毁，旧 generation 会话立即释放。 */
  function syncMediaWithSnapshot(next: PlaybackSnapshot): void {
    syncMotionWithSnapshot(next)
    if (next.state === 'blocked' || next.state === 'error') {
      mediaSession?.pause()
      return
    }
    if (next.state === 'stopped' || next.state === 'ended') {
      disposePageMedia()
      return
    }
    if (next.state !== 'playing') return
    if (mediaSession && (next.generation !== mediaSessionGeneration || next.path !== mediaPath)) {
      disposePageMedia()
    }
  }

  function disposeController(): void {
    wakeLock.release()
    suspendPageMedia()
    disposePageMedia()
    disposePageMotion()
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
      if (!instance || !current) return
      // 先准备页内时间轴，再由其目标注册表过滤旧媒体会话；未注册媒体保持旧行为。
      const motion = attachPageMotion(root, attempt.path, attempt.generation)
      let motionReady = false
      if (motion) {
        try {
          await motion.prepare()
        } catch (error) {
          const latest = instance.getSnapshot()
          if (disposed || latest.path !== attempt.path || latest.generation !== attempt.generation) return
          const message = error instanceof Error ? error.message : '页内时间轴准备失败。'
          instance.reportError(attempt.path, attempt.generation, message)
          return
        }
        const latest = instance.getSnapshot()
        if (disposed || latest.path !== attempt.path || latest.generation !== attempt.generation) return
        motionReady = true
      }
      // 每个稳定放映页都建立会话；是否自动播放由用途、推进模式与执行策略决定。
      const session = createSessionForPage(root, attempt.path, attempt.generation, motion)
      const media = session.getSnapshot()
      if (media.contractError) {
        instance.reportMediaError(attempt.path, attempt.generation, media.contractError)
        return
      }
      if (current.advanceMode === 'timeline_end') {
        if (!motion || !motionReady) {
          instance.reportTimelineUnavailable(attempt.path, attempt.generation)
          return
        }
        const participating = participatingTargets(media)
        instance.reportReady(attempt.path, attempt.generation, participating.length, 1)
        if (media.targets.length > 0) void playPageMedia(session)
        void playPageMotion(motion, attempt.path, attempt.generation)
      } else if (current.advanceMode === 'media_end') {
        const participating = participatingTargets(media)
        instance.reportReady(attempt.path, attempt.generation, participating.length)
        if (media.targets.length > 0) void playPageMedia(session)
        if (motionReady && motion) void playPageMotion(motion, attempt.path, attempt.generation)
      } else {
        instance.reportReady(attempt.path, attempt.generation)
        if (policy.value.allowAutoplay && media.targets.some(target => target.autoplayEligible)) {
          void playPageMedia(session, { autoplayOnly: true })
        }
        if (motionReady && motion) void playPageMotion(motion, attempt.path, attempt.generation)
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
    disposePageMotion()
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
    motionHandle?.pause()
    if (mediaSession) mediaSession.suspend()
    else suspendPageMedia()
    return true
  }

  function resumePlayback(): boolean {
    const instance = controller.value
    if (!instance || !instance.resume()) return false
    const current = instance.getSnapshot()
    if (current.state === 'playing') {
      if (motionHandle) void playPageMotion(motionHandle, current.path, current.generation)
      if (mediaSession?.isSuspended()) mediaSession.resume()
      else if (mediaSession && current.advanceMode === 'media_end') void playPageMedia(mediaSession)
      else if (!mediaSession && current.advanceMode === 'media_end') restartPageMedia(instance, current)
      else mediaPlaybackCoordinator.resume()
    }
    if (current.state === 'preparing') beginReadiness(instance.getSnapshot().path, true)
    return true
  }

  /** 切换会话自动推进；只影响计时，不改变当前页、路由或已播放媒体。 */
  function setAutoAdvance(enabled: boolean): boolean {
    return controller.value?.setAutoAdvance(enabled) ?? false
  }

  function stopPlayback(): boolean {
    if (!controller.value?.stop()) return false
    motionHandle?.pause()
    if (mediaSession) disposePageMedia()
    else suspendPageMedia()
    mediaPlaybackCoordinator.dispose()
    return true
  }

  function retryPlayback(): boolean {
    const instance = controller.value
    if (!instance || !instance.retry()) return false
    disposePageMedia()
    disposePageMotion()
    beginReadiness(instance.getSnapshot().path, true)
    return true
  }

  /** 失败态跳到下一页；清掉旧媒体后重新等待目标页就绪。 */
  function nextPlayback(): boolean {
    const instance = controller.value
    if (!instance || !instance.next()) return false
    disposePageMedia()
    disposePageMotion()
    mediaPlaybackCoordinator.dispose()
    beginReadiness(instance.getSnapshot().path, false)
    return true
  }

  const canGoPrevious = computed(() => {
    const current = snapshot.value
    if (!current || current.index <= 0) return false
    return current.state !== 'error' && current.state !== 'blocked'
  })

  const canGoNext = computed(() => {
    const current = snapshot.value
    if (!current || current.index < 0) return false
    if (current.state === 'error' || current.state === 'blocked') {
      return current.index < current.total - 1 || current.loop
    }
    return current.index < current.total - 1
  })

  /**
   * 在放映序列内手动翻页；手动模式不绕回。
   * 失败态交给控制器 next() 以清除旧媒体并重新就绪。
   */
  function goBy(offset: -1 | 1): boolean {
    const instance = controller.value
    const current = instance?.getSnapshot()
    if (!instance || !current || current.index < 0) return false
    if (current.state === 'error' || current.state === 'blocked') {
      return offset === 1 ? nextPlayback() : false
    }
    const targetIndex = current.index + offset
    if (targetIndex < 0 || targetIndex >= current.total) return false
    const target = buildPlaybackPages()[targetIndex]
    if (!target) return false
    void navigateRuntimePage(router, target.path).catch(error => {
      console.error('[runtime-playback] 手动翻页失败', error)
    })
    return true
  }

  function toggleAutoAdvance(): boolean {
    const instance = controller.value
    const current = instance?.getSnapshot()
    if (!instance || !current) return false
    return instance.setAutoAdvance(!current.autoAdvanceEnabled)
  }

  /** 切换会话级静音；只影响本地播放，不写回项目或创建额外计时。 */
  function toggleMute(): boolean {
    if (disposed) return false
    muted.value = !muted.value
    mediaSession?.setMuted(muted.value)
    motionHandle?.setMuted(muted.value)
    return true
  }

  /** 窗口隐藏、页面冻结或 bfcache 恢复时暂停；等待用户显式继续，不补课。 */
  function pauseForInterruption(): void {
    const instance = controller.value
    if (!instance) return
    const state = instance.getSnapshot().state
    if (state === 'playing' || state === 'preparing') pausePlayback()
  }

  function handleVisibilityChange(): void {
    if (!document.hidden) return
    pauseForInterruption()
  }

  function handlePageFreeze(): void {
    pauseForInterruption()
  }

  function handlePageShow(event: PageTransitionEvent): void {
    if (event.persisted) pauseForInterruption()
  }

  onMounted(() => {
    document.addEventListener('visibilitychange', handleVisibilityChange)
    document.addEventListener('freeze', handlePageFreeze)
    window.addEventListener('pageshow', handlePageShow)
    if (disposed || options.autoStart !== true) return
    const instance = ensureController()
    if (!instance) return
    if (instance.start()) beginReadiness(instance.getSnapshot().path, true)
  })

  onBeforeUnmount(() => {
    disposed = true
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    document.removeEventListener('freeze', handlePageFreeze)
    window.removeEventListener('pageshow', handlePageShow)
    stopRouteWatch()
    stopSettledWatch()
    stopNavigationErrorWatch()
    stopPolicyWatch()
    disposeController()
  })

  return {
    snapshot,
    errorMessage,
    wakeLockState: wakeLock.state,
    muted,
    canGoPrevious,
    canGoNext,
    start: startPlayback,
    pause: pausePlayback,
    resume: resumePlayback,
    stop: stopPlayback,
    retry: retryPlayback,
    next: nextPlayback,
    goPrevious: () => goBy(-1),
    goNext: () => goBy(1),
    setAutoAdvance,
    toggleAutoAdvance,
    toggleMute,
    motion,
    motionPlan,
    seekMotion,
    refresh: () => {
      const instance = controller.value
      if (instance) snapshot.value = instance.getSnapshot()
    },
  }
}
