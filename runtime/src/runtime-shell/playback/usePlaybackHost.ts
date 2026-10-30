/** 文件功能：把唯一 Deck/Scene 调度接入全屏、Router 和执行策略，正式播放不再发现旧时间轴或创建媒体会话。 */
import { computed, onBeforeUnmount, onMounted, shallowRef, ref, watch, type Ref, type ComputedRef } from 'vue'
import { useRouter } from 'vue-router'
import { getRuntimeSession } from '@/core/router/runtime-session'
import { useRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { mediaPlaybackCoordinator } from '@/core/execution/media-playback-guard'
import { playbackConfig } from '@/core/utils/config'
import { getRouteInfosSortedByPageNumber } from '@/core/utils/route-generator'
import { resolvePageAdvance } from '@/core/utils/page-transition'
import { SceneSessionError, type SceneSnapshot } from '@/core/scene/types'
import { createPageSceneStage } from './page-scene-stage'
import { DeckPlaybackSession } from './playback-controller'
import { findPlaybackPageElement } from './playback-page-root'
import { useScreenWakeLock, type WakeLockState } from './useScreenWakeLock'
import type { DeckPage, DeckSnapshot } from './deck-types'
import { runtimeAudioBus } from '@/core/audio/runtime-audio-bus'

export { findPlaybackPageElement } from './playback-page-root'
export interface PlaybackHostOptions { startOnMount?: boolean }
export interface PlaybackHost {
  snapshot: Ref<DeckSnapshot | null>
  scene: ComputedRef<SceneSnapshot | null>
  errorMessage: ComputedRef<string>
  wakeLockState: Readonly<Ref<WakeLockState>>
  muted: Readonly<Ref<boolean>>
  canGoPrevious: ComputedRef<boolean>
  canGoNext: ComputedRef<boolean>
  start(): boolean
  stop(): boolean
  retry(): boolean
  hold(): boolean
  release(): boolean
  toggleHold(): boolean
  goPrevious(): boolean
  goNext(): boolean
  toggleMute(): boolean
  refresh(): void
}

/** 复用现有可见叶子页目录；旧模式明确拒绝，由 B5 负责持久配置的 Schema 升级。 */
export function buildPlaybackPages(): DeckPage[] {
  return getRouteInfosSortedByPageNumber().map(info => {
    const advance = resolvePageAdvance(info.advance)
    if (advance.mode !== 'manual' && advance.mode !== 'timer' && advance.mode !== 'scene_end') {
      throw new SceneSessionError('DECK_ADVANCE_UNSUPPORTED', '项目仍包含旧推进模式，请改为 manual、timer 或 scene_end。')
    }
    return { path: info.path, advance: { mode: advance.mode, delayMs: advance.delayMs, completionDelayMs: advance.completionDelayMs } }
  })
}

/** 非全屏和静态/交互预览不创建放映会话；退出立即撤销 Scene 与准备。 */
export function usePlaybackHost(options: PlaybackHostOptions = {}): PlaybackHost {
  const router = useRouter(), session = getRuntimeSession(router), policy = useRuntimeExecutionPolicy(), wakeLock = useScreenWakeLock()
  const snapshot = shallowRef<DeckSnapshot | null>(null), setupError = ref('')
  const scene = computed(() => snapshot.value?.scene ?? null)
  const errorMessage = computed(() => snapshot.value?.issue?.message ?? setupError.value)
  let deck: DeckPlaybackSession | null = null, unsubscribe: (() => void) | null = null, disposed = false, frozen = false

  /** 放映只能由根元素全屏窗口拥有，视频自身全屏不创建 Deck。 */
  function allowed(): boolean {
    return !disposed && policy.value.allowAutoAdvance && policy.value.kind === 'presentation'
      && document.fullscreenElement === document.documentElement
  }

  /** 惰性创建唯一控制器；没有配置或合法页面时给出可见状态，不启动旁路。 */
  function ensureDeck(): DeckPlaybackSession | null {
    if (!allowed() || !playbackConfig.value.supported) return null
    if (deck) return deck
    try {
      const pages = buildPlaybackPages()
      if (!pages.length) return null
      deck = new DeckPlaybackSession({ pages, loop: playbackConfig.value.loop, initialPath: router.currentRoute.value.path, stage: createPageSceneStage(router) })
      deck.setSuspended(document.hidden || frozen)
      unsubscribe = deck.subscribe(value => {
        snapshot.value = value
        if (!value.suspended && ['preparing', 'playing', 'blocked'].includes(value.state)) wakeLock.request()
        else wakeLock.release()
      })
      snapshot.value = deck.getSnapshot(); setupError.value = ''
      return deck
    } catch (error) {
      setupError.value = error instanceof SceneSessionError ? error.message : '放映配置初始化失败。'
      return null
    }
  }

  /** 显式用户播放与全屏壳挂载共用入口，先交还开发调试的页面所有权。 */
  function start(): boolean {
    if (!allowed()) return false
    window.__RUNTIME_SCENE_DEBUG__?.stop()
    return ensureDeck()?.start(router.currentRoute.value.path) ?? false
  }

  /** Scene 负责受管资源清理；媒体守卫只作为退出时手动内容媒体的停止屏障。 */
  function stop(): boolean {
    const root = snapshot.value ? findPlaybackPageElement(snapshot.value.path) : null
    const stopped = deck?.stop() ?? false
    if (root) mediaPlaybackCoordinator.suspend(root)
    runtimeAudioBus.stopOwner('content'); runtimeAudioBus.stopOwner('deck')
    wakeLock.release()
    return stopped
  }

  /** 宿主卸载或策略收紧销毁整个所有权，不允许迟到事件复活。 */
  function disposeDeck(): void {
    unsubscribe?.(); unsubscribe = null
    deck?.dispose(); deck = null
    wakeLock.release(); snapshot.value = null
  }

  const stopRouteWatch = watch(() => router.currentRoute.value.path, path => { deck?.visit(path) }, { flush: 'sync' })
  const stopPolicyWatch = watch(() => policy.value.allowAutoAdvance, value => { if (!value) disposeDeck() })
  /** 隐藏/冻结仅使用内部暂挂；不引入可由页面或 Presenter 控制的暂停接口。 */
  const visibility = () => deck?.setSuspended(document.hidden || frozen)
  const freeze = () => { frozen = true; visibility() }
  const resume = () => { frozen = false; visibility() }
  const pageShow = (event: PageTransitionEvent) => {
    if (!event.persisted) return
    deck?.setSuspended(true); resume()
  }
  const fullscreen = () => { if (!allowed()) stop() }

  onMounted(() => {
    document.addEventListener('visibilitychange', visibility)
    document.addEventListener('freeze', freeze)
    document.addEventListener('resume', resume)
    document.addEventListener('fullscreenchange', fullscreen)
    window.addEventListener('pageshow', pageShow)
    if (options.startOnMount) start()
  })
  onBeforeUnmount(() => {
    disposed = true; stopRouteWatch(); stopPolicyWatch(); disposeDeck()
    document.removeEventListener('visibilitychange', visibility)
    document.removeEventListener('freeze', freeze)
    document.removeEventListener('resume', resume)
    document.removeEventListener('fullscreenchange', fullscreen)
    window.removeEventListener('pageshow', pageShow)
  })

  return { snapshot, scene, errorMessage, wakeLockState: wakeLock.state, muted: session.audioMuted,
    canGoPrevious: computed(() => (snapshot.value?.index ?? 0) > 0),
    canGoNext: computed(() => Boolean(snapshot.value && snapshot.value.index >= 0 && snapshot.value.index < snapshot.value.total - 1)),
    start, stop, retry: () => allowed() && (deck?.retry() ?? false),
    hold: () => deck?.hold() ?? false, release: () => deck?.release() ?? false,
    toggleHold: () => snapshot.value?.held ? deck?.release() ?? false : deck?.hold() ?? false,
    goPrevious: () => allowed() && (deck?.go(-1) ?? false), goNext: () => allowed() && (deck?.go(1) ?? false),
    toggleMute() { if (!allowed()) return false; session.audioMuted.value = !session.audioMuted.value; return true },
    refresh() { if (deck) snapshot.value = deck.getSnapshot() },
  }
}
