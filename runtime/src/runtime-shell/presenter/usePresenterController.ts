/** 文件功能：管理 Presenter 页面与即时同步；控制台仅发送意图，唯一观众调度者回传完整原子状态。 */
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { routerKey } from 'vue-router'
import { appPageConfig, routeConfigs } from '@/core/utils/config'
import { normalizePresenterRoutePath, createPresenterChannelId } from './presenter-url'
import { buildPresenterPages } from './presenter-pages'
import { createPresenterOwnerEpoch, openPresenterChannel } from './presenter-channel'
import { PresenterSyncReceiver, PresenterSyncSender, resolvePresenterArtifactIdentity,
  type PresenterSyncRole, type PresenterSyncViewMode, type PresenterSyncPlaybackCommandAction,
  type PresenterPlaybackState, type PresenterStateMessage } from './presenter-sync-protocol'
export { buildPresenterPages } from './presenter-pages'
export type { PresenterPage } from './presenter-pages'
export type PresenterViewMode = PresenterSyncViewMode
interface PresenterControllerOptions {
  channelId: string
  initialPath?: string
  role: PresenterSyncRole
  artifactIdentity?: string
  ownerEpoch?: number
  onPlaybackCommand?: (action: PresenterSyncPlaybackCommandAction) => void
}

/** 控制台从 state 一次替换所有展示字段，重开只请求当前事实，不恢复旧命令。 */
export function usePresenterController(options: PresenterControllerOptions) {
  const router = inject(routerKey, undefined)
  const currentPath = ref(normalizePresenterRoutePath(options.initialPath || router?.currentRoute.value.path || '/'))
  const viewMode = ref<PresenterViewMode>('focus')
  const tileSize = ref(readTileSize())
  const channelSupported = ref(false)
  const remotePlayback = ref<PresenterStateMessage | null>(null)
  const identity = { channelId: options.channelId, artifactIdentity: options.artifactIdentity ?? resolvePresenterArtifactIdentity(),
    sourceId: createPresenterChannelId(), role: options.role, ownerEpoch: options.ownerEpoch ?? createPresenterOwnerEpoch(options.channelId) }
  const sender = new PresenterSyncSender(identity), receiver = new PresenterSyncReceiver(identity)
  let channel: ReturnType<typeof openPresenterChannel> | null = null
  let retired = false
  let playback: PresenterPlaybackState = { page: currentPath.value, phase: 'stopped', held: false, fullscreen: false, issue: null }
  const pages = computed(() => buildPresenterPages(routeConfigs.value))
  const pageViewport = computed(() => appPageConfig.value)
  const currentIndex = computed(() => Math.max(0, pages.value.findIndex(page => page.path === currentPath.value)))
  const currentPage = computed(() => pages.value[currentIndex.value] ?? null)
  const nextPage = computed(() => pages.value[currentIndex.value + 1] ?? null)
  const previousPage = computed(() => pages.value[currentIndex.value - 1] ?? null)
  const canGoNext = computed(() => Boolean(nextPage.value)), canGoPrevious = computed(() => Boolean(previousPage.value))
  const displayStatus = computed(() => ({ state: !remotePlayback.value ? 'unknown' : remotePlayback.value.phase === 'closed' ? 'closed' : remotePlayback.value.fullscreen ? 'fullscreen' : 'windowed', isFullscreen: remotePlayback.value?.fullscreen ?? false }))
  const displayAvailable = computed(() => Boolean(remotePlayback.value && remotePlayback.value.phase !== 'closed' && remotePlayback.value.fullscreen))

  /** 观众一次替换完整 Deck 事实；错误摘要有界，状态发布与快照更新不可拆成两条消息。 */
  function updatePlayback(value: Omit<PresenterPlaybackState, 'fullscreen'>): void {
    if (options.role !== 'display' || retired) return
    playback = { ...value, fullscreen: playback.fullscreen, issue: value.issue ? { code: value.issue.code.slice(0, 128), message: value.issue.message.slice(0, 500) } : null }
    postPlaybackState()
  }
  /** 只有仍持有 owner 的观众窗口可发布状态。 */
  function postPlaybackState(): void {
    if (options.role === 'display' && !retired) channel?.send(sender.create({ type: 'state', ownerId: identity.sourceId, ...playback }))
  }
  /** 控制台显式请求当前状态；不是推送本地猜测的播放状态。 */
  function postState(): void { channel?.send(sender.create({ type: 'request-state' })) }
  /** 所有命令针对已发现的观众 owner；没有 owner 时不暂存、不重放。 */
  function sendPlaybackCommand(action: PresenterSyncPlaybackCommandAction, page?: string): void {
    if (options.role !== 'console' || !receiver.ownerId || remotePlayback.value?.phase === 'closed') return
    channel?.send(sender.create({ type: 'intent', ownerId: receiver.ownerId, action, ...(action === 'navigate' ? { page } : {}) }))
  }
  /** 导航也由观众窗口执行并回传，控制台不提前改变当前页。 */
  function navigateTo(path: string): void {
    const normalized = normalizePresenterRoutePath(path)
    if (!pages.value.some(page => page.path === normalized)) return
    if (options.role === 'console') sendPlaybackCommand('navigate', normalized)
    else applyNavigation(normalized)
  }
  /** 仅观众路由可驱动 Deck；保留 runtimeMode/channel 等宿主参数。 */
  function applyNavigation(path: string): void {
    if (router) void router.push({ path, query: router.currentRoute.value.query })
    else { currentPath.value = path; if (playback.phase === 'stopped') playback = { ...playback, page: path }; postPlaybackState() }
  }
  /** 上一页是显式导航，不恢复页面历史播放位置。 */
  function goPrevious(): void { if (previousPage.value) navigateTo(previousPage.value.path) }
  /** 停止状态只导航，正在放映时由 Deck 推进或跳过失败页。 */
  function goNext(): void { if (remotePlayback.value?.phase === 'stopped') { if (nextPage.value) navigateTo(nextPage.value.path) } else sendPlaybackCommand('next') }
  /** 平铺大小只影响控制台本地 UI，不进入观众状态。 */
  function setTileSize(value: number): void {
    tileSize.value = Math.max(140, Math.min(420, Number.isFinite(value) ? value : 300))
    try { localStorage.setItem('web-presentation.presenter.tileSize', String(tileSize.value)) } catch { /* 不阻断控制台。 */ }
  }
  /** 全屏与关闭也通过同一个原子 state 发布。 */
  function postDisplayStatus(state: string, fullscreen: boolean): void {
    playback = { ...playback, fullscreen, ...(state === 'closed' ? { phase: 'closed' } : {}) }; postPlaybackState()
  }
  /** 退出控制台只发送一次关闭意图，不写恢复快照。 */
  function postClose(): void { sendPlaybackCommand('close') }

  watch(() => router?.currentRoute.value.path, path => {
    if (options.role !== 'display' || !path || retired) return
    currentPath.value = normalizePresenterRoutePath(path)
    if (playback.phase === 'stopped') { playback = { ...playback, page: currentPath.value }; postPlaybackState() }
  })
  onMounted(() => {
    if (!options.channelId) return
    channel = openPresenterChannel(options.channelId, input => {
      const result = receiver.receive(input), message = result.message
      if (!result.accepted || !message) return
      if (message.type === 'request-state') { if (options.role === 'display') postPlaybackState(); return }
      if (message.type === 'state') {
        if (options.role === 'display') { retired = true; options.onPlaybackCommand?.('stop'); return }
        remotePlayback.value = message
        currentPath.value = message.page
        if (router && router.currentRoute.value.path !== message.page) void router.replace({ path: message.page, query: router.currentRoute.value.query })
        return
      }
      if (message.action === 'navigate') { if (message.page) navigateTo(message.page); return }
      if (message.action === 'close') { options.onPlaybackCommand?.('stop'); postDisplayStatus('closed', false); window.close(); return }
      options.onPlaybackCommand?.(message.action)
    })
    channelSupported.value = channel.supported
    if (options.role === 'display') postPlaybackState()
    else postState()
  })
  onBeforeUnmount(() => { if (options.role === 'display') postDisplayStatus('closed', false); channel?.close(); channel = null })
  return { pages, pageViewport, currentPath, currentPage, nextPage, previousPage, canGoPrevious, canGoNext,
    displayStatus, displayAvailable, viewMode, tileSize, channelSupported, remotePlayback, updatePlayback,
    navigateTo, goPrevious, goNext, setTileSize, postState, postPlaybackState, sendPlaybackCommand, postClose, postDisplayStatus }
}
/** 读取可选的 UI 首选项；播放状态与命令从不从存储恢复。 */
function readTileSize(): number {
  try { const value = Number(localStorage.getItem('web-presentation.presenter.tileSize')); return value >= 140 && value <= 420 ? value : 300 } catch { return 300 }
}
