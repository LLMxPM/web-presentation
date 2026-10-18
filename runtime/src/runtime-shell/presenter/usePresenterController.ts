/**
 * 文件用途：管理 Runtime 演讲模式页面列表、当前页、平铺尺寸与窗口 BroadcastChannel 同步。
 */

import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { routerKey } from 'vue-router'
import { getRuntimeSession } from '@/core/router/runtime-session'

import { appPageConfig, routeConfigs } from '@/core/utils/config'
import type { RouteConfig } from '@/core/types/navigation'
import { normalizePresenterRoutePath } from '@/runtime-shell/presenter/presenter-url'
import {
  PRESENTER_SYNC_PROTOCOL_VERSION,
  PresenterSyncReceiver,
  PresenterSyncSender,
  resolvePresenterArtifactIdentity,
  parsePresenterSyncMessage,
  isPresenterMessageForOwner,
  type PresenterSyncDisplayStatusMessage,
  type PresenterSyncIdentity,
  type PresenterSyncMessageBody,
  type PresenterSyncMessage,
  type PresenterSyncPlaybackCommandAction,
  type PresenterSyncPlaybackSnapshot,
  type PresenterSyncStateMessage,
  type PresenterSyncViewMode,
  type ReceivedPresenterSync,
} from '@/runtime-shell/presenter/presenter-sync-protocol'

export type PresenterViewMode = PresenterSyncViewMode
export type PresenterRole = 'console' | 'display'
export type PresenterDisplayStatusState = 'unknown' | 'connected' | 'windowed' | 'fullscreen' | 'closed'

export interface PresenterPage {
  path: string
  title: string
  pageNumber: number
  componentPath: string
  speakerNotes: string
}

export interface PresenterDisplayStatus {
  state: PresenterDisplayStatusState
  isFullscreen: boolean
  updatedAt: number
}

export interface PresenterStoredMessage {
  sourceId: string
  sentAt: number
  message: PresenterSyncMessage
}

interface PresenterControllerOptions {
  channelId: string
  initialPath?: string
  role: PresenterRole
  /** 覆盖产物身份，仅用于测试或受控宿主。 */
  artifactIdentity?: string
  /** 覆盖 owner epoch，仅用于测试。 */
  ownerEpoch?: number
  /** 本地时钟注入点，跨窗口只比较本地到达时间。 */
  now?: () => number
  /** 观众窗口处理控制台命令；控制台不提供该回调。 */
  onPlaybackCommand?: (action: PresenterSyncPlaybackCommandAction, autoAdvance?: boolean) => void
}

const TILE_SIZE_STORAGE_KEY = 'web-presentation.presenter.tileSize'
const CHANNEL_NAME_PREFIX = 'web-presentation:presenter:'
const SYNC_STORAGE_KEY_PREFIX = 'web-presentation.presenter.sync.'
const EVENT_STORAGE_KEY_PREFIX = 'web-presentation.presenter.event.'
const DEFAULT_TILE_SIZE = 300
const MIN_TILE_SIZE = 140
const MAX_TILE_SIZE = 420

/**
 * 创建演讲模式控制器。
 * @param options 控制器角色、频道和初始页
 * @returns 页面列表、当前页状态和导航动作
 */
export function usePresenterController(options: PresenterControllerOptions) {
  const router = inject(routerKey, undefined)
  const session = router ? getRuntimeSession(router) : undefined
  let remotePath = ''
  let commandSequence = 0
  let applyingRemoteView = false
  const currentPath = ref(normalizePresenterRoutePath(router?.currentRoute.value.path || options.initialPath || ''))
  const viewMode = ref<PresenterViewMode>('focus')
  const tileSize = ref(readStoredTileSize())
  const channelSupported = ref(typeof BroadcastChannel !== 'undefined' || isPresenterStorageSupported())
  const displayStatus = ref<PresenterDisplayStatus>({
    state: 'unknown',
    isFullscreen: false,
    updatedAt: 0,
  })
  const activeDisplayOwnerEpoch = ref<number | null>(null)
  const controllerId = createControllerId()
  const now = options.now ?? (() => Date.now())
  const identity: PresenterSyncIdentity = {
    channelId: options.channelId,
    artifactIdentity: options.artifactIdentity ?? resolvePresenterArtifactIdentity(),
    sourceId: controllerId,
    role: options.role,
    ownerEpoch: options.ownerEpoch ?? createOwnerEpoch(),
  }
  const sender = new PresenterSyncSender(identity)
  const receiver = new PresenterSyncReceiver(identity, options.now)
  const remotePlayback = ref<ReceivedPresenterSync | null>(null)
  const playbackValues = ref<{
    state: PresenterSyncPlaybackSnapshot['state']
    remainingMs: number
    delayMs: number | null
    waitingForMedia: boolean
    autoAdvanceEnabled: boolean
  }>({ state: 'stopped', remainingMs: 0, delayMs: null, waitingForMedia: false, autoAdvanceEnabled: false })
  // 观众窗口先于控制台加载时，ready 已错过；收到控制台状态后补一次身份与状态回执。
  const acknowledgedConsoleSources = new Set<string>()
  let channel: BroadcastChannel | null = null

  const pages = computed<PresenterPage[]>(() => buildPresenterPages(routeConfigs.value))
  const pageViewport = computed(() => appPageConfig.value)
  const currentIndex = computed(() => {
    return Math.max(0, pages.value.findIndex(page => page.path === currentPath.value))
  })
  const currentPage = computed(() => pages.value[currentIndex.value] ?? pages.value[0] ?? null)
  const nextPage = computed(() => pages.value[currentIndex.value + 1] ?? null)
  const previousPage = computed(() => pages.value[currentIndex.value - 1] ?? null)
  const canGoPrevious = computed(() => Boolean(previousPage.value))
  const canGoNext = computed(() => Boolean(nextPage.value))
  const playbackSnapshot = computed<PresenterSyncPlaybackSnapshot>(() => ({
    ...playbackValues.value,
    currentPath: currentPath.value,
    index: currentIndex.value,
    total: pages.value.length,
  }))
  /** 观众窗口全屏后才算可放映；窗口化时控制台显示等待并禁用命令。 */
  const displayAvailable = computed(() => {
    return displayStatus.value.isFullscreen
      && (displayStatus.value.state === 'connected' || displayStatus.value.state === 'fullscreen')
  })

  /**
   * 更新本窗口的放映状态，供下一次 state-sync 携带；不在协议层启动调度。
   * @param value 放映状态片段
   */
  function updatePlayback(
    value: Partial<Pick<
      PresenterSyncPlaybackSnapshot,
      'state' | 'remainingMs' | 'delayMs' | 'waitingForMedia' | 'autoAdvanceEnabled'
    >>,
  ): void {
    playbackValues.value = {
      state: value.state ?? playbackValues.value.state,
      remainingMs: Math.max(0, value.remainingMs ?? playbackValues.value.remainingMs),
      delayMs: value.delayMs === undefined ? playbackValues.value.delayMs : value.delayMs,
      waitingForMedia: value.waitingForMedia ?? playbackValues.value.waitingForMedia,
      autoAdvanceEnabled: value.autoAdvanceEnabled ?? playbackValues.value.autoAdvanceEnabled,
    }
  }

  /**
   * 跳转到指定页面，并按控制台角色向观众窗口同步。
   * @param path 目标页面路径
   */
  function navigateTo(path: string): void {
    const normalizedPath = normalizePresenterRoutePath(path)
    if (!pages.value.some(page => page.path === normalizedPath)) {
      return
    }
    currentPath.value = normalizedPath
    if (router) {
      void router.push({ path: normalizedPath, query: router.currentRoute.value.query })
    } else {
      postMessage({
        type: 'navigate',
        currentPath: normalizedPath,
        playback: playbackSnapshot.value,
        ...buildTargetOwnerField(),
      }, nextCommandId())
    }
  }

  /**
   * 跳转上一页。
   */
  function goPrevious(): void {
    if (previousPage.value) {
      navigateTo(previousPage.value.path)
    }
  }

  /**
   * 跳转下一页。
   */
  function goNext(): void {
    if (nextPage.value) {
      navigateTo(nextPage.value.path)
    }
  }

  /**
   * 更新平铺页尺寸，并持久化到 localStorage。
   * @param value 目标尺寸
   */
  function setTileSize(value: number): void {
    tileSize.value = clampTileSize(value)
    writeStoredTileSize(tileSize.value)
    postState()
  }

  /**
   * 向同频道窗口发送当前完整状态。
   */
  function postState(targetOwnerEpoch?: number): void {
    postMessage({
      type: 'state-sync',
      currentPath: currentPath.value,
      viewMode: viewMode.value,
      tileSize: tileSize.value,
      playback: playbackSnapshot.value,
      ...(targetOwnerEpoch === undefined ? {} : { targetOwnerEpoch }),
    })
  }

  /**
   * 观众窗口上报自身播放快照；控制台只回显，不据此启动本地计时。
   */
  function postPlaybackState(): void {
    if (options.role !== 'display') return
    postMessage({ type: 'playback-state', playback: playbackSnapshot.value })
  }

  /**
   * 控制台向当前观众 owner 发送放映命令；没有已连接观众时拒绝发送。
   * @param action 命令动作
   * @param autoAdvance set-auto-advance 的目标状态
   */
  function sendPlaybackCommand(
    action: PresenterSyncPlaybackCommandAction,
    autoAdvance?: boolean,
  ): boolean {
    if (options.role !== 'console' || activeDisplayOwnerEpoch.value === null) return false
    postMessage({
      type: 'playback-command',
      action,
      ...(action === 'set-auto-advance' ? { autoAdvance: Boolean(autoAdvance) } : {}),
      targetOwnerEpoch: activeDisplayOwnerEpoch.value,
    }, nextCommandId())
    return true
  }

  /**
   * 发送窗口关闭通知。
   */
  function postClose(): void {
    postMessage({ type: 'close' })
  }

  /**
   * 上报观众窗口状态，供控制台回显。
   * @param state 观众窗口状态
   * @param isFullscreen 是否处于 DOM 全屏
   */
  function postDisplayStatus(state: PresenterDisplayStatusState, isFullscreen: boolean): void {
    postMessage({
      type: 'display-status',
      status: {
        state,
        isFullscreen,
        updatedAt: now(),
      },
    })
  }

  /**
   * 发送频道消息。
   * @param message 消息体
   * @param commandId 可选命令 ID
   */
  function postMessage(message: PresenterSyncMessageBody, commandId?: string): void {
    const envelope = sender.create(message, commandId)
    channel?.postMessage(envelope)
    writeStoredSyncMessage(envelope)
  }

  /**
   * 处理 BroadcastChannel 收到的跨窗口消息。
   * @param event 消息事件
   */
  function handleChannelMessage(event: MessageEvent<unknown>): void {
    const result = receiver.receive(event.data)
    if (!result.accepted || !result.received) return
    const { message } = result.received
    if (options.role === 'console' && isDisplayOriginMessage(message)) {
      // 新观众 owner 接管后，旧观众后续的非权威状态与导航一律失效。
      if (activeDisplayOwnerEpoch.value !== null && message.ownerEpoch < activeDisplayOwnerEpoch.value) return
      activeDisplayOwnerEpoch.value = message.ownerEpoch
    }
    if ((message.type === 'state-sync' || message.type === 'navigate')) {
      if (options.role === 'display' && message.role !== 'console') return
      if (!isPresenterMessageForOwner(message, identity.ownerEpoch)) return
      if (options.role === 'display') acknowledgeConsole(message.sourceId)
      remotePlayback.value = result.received
      applyIncomingState(message)
      return
    }
    if (message.type === 'playback-state' && options.role === 'console' && message.role === 'display') {
      remotePlayback.value = result.received
      return
    }
    if (message.type === 'playback-command' && options.role === 'display' && message.role === 'console') {
      if (!isPresenterMessageForOwner(message, identity.ownerEpoch)) return
      options.onPlaybackCommand?.(message.action, message.autoAdvance)
      return
    }
    if (message.type === 'ready' && options.role === 'console' && message.role === 'display') {
      postState(message.ownerEpoch)
      return
    }
    if (message.type === 'display-status' && options.role === 'console' && message.role === 'display') {
      applyDisplayStatus(message.status)
      return
    }
    if (message.type === 'close' && options.role === 'display' && message.role === 'console') {
      window.close()
    }
  }

  /**
   * 处理 localStorage 兜底同步消息。
   * @param event storage 事件
   */
  function handleStorageMessage(event: StorageEvent): void {
    if (!options.channelId || !event.newValue) {
      return
    }
    if (event.key !== buildPresenterStorageKey(options.channelId)
      && event.key !== buildPresenterEventStorageKey(options.channelId)) {
      return
    }
    const storedMessage = parseStoredSyncMessage(event.newValue)
    if (!storedMessage || storedMessage.sourceId === controllerId) {
      return
    }
    handleChannelMessage({ data: storedMessage.message } as MessageEvent<unknown>)
  }

  /**
   * 应用外部窗口传来的页面和视图状态。
   * @param message 状态或导航消息
   */
  function applyIncomingState(message: PresenterSyncStateMessage | Extract<PresenterSyncMessage, { type: 'navigate' }>): void {
    const normalizedPath = normalizePresenterRoutePath(message.currentPath)
    if (pages.value.some(page => page.path === normalizedPath)) {
      currentPath.value = normalizedPath
      if (router && router.currentRoute.value.path !== normalizedPath) {
        remotePath = normalizedPath
        if (session) session.suppressTransition.value = message.type === 'state-sync'
        void router.replace({ path: normalizedPath, query: router.currentRoute.value.query }).finally(async () => {
          await nextTick()
          if (session) session.suppressTransition.value = false
        })
      }
    }
    if (message.type === 'state-sync') {
      applyingRemoteView = true
      viewMode.value = message.viewMode
      void nextTick(() => { applyingRemoteView = false })
      tileSize.value = clampTileSize(message.tileSize)
    }
  }

  /**
   * 应用观众窗口状态回显。
   * @param status 观众窗口状态
   */
  function applyDisplayStatus(status: PresenterDisplayStatus): void {
    if (!status || typeof status !== 'object' || !isPresenterDisplayStatusState(status.state)) {
      return
    }
    displayStatus.value = {
      state: status.state,
      isFullscreen: Boolean(status.isFullscreen),
      updatedAt: Number.isFinite(status.updatedAt) ? status.updatedAt : now(),
    }
  }

  /** 生成单次导航命令 ID；同一命令跨通道重发时复用。 */
  function nextCommandId(): string {
    commandSequence += 1
    return `${controllerId}:command:${commandSequence}`
  }

  /** 只有观众窗口发送的消息能更新控制台的命令目标 owner。 */
  function isDisplayOriginMessage(message: PresenterSyncMessage): boolean {
    return message.role === 'display'
  }

  /**
   * 观众窗口为每个控制台补发一次身份与播放回执，避免控制台晚于观众窗口加载时丢失 ready。
   * @param sourceId 控制台控制器标识
   */
  function acknowledgeConsole(sourceId: string): void {
    if (acknowledgedConsoleSources.has(sourceId)) return
    acknowledgedConsoleSources.add(sourceId)
    const fullscreen = typeof document !== 'undefined' && Boolean(document.fullscreenElement)
    postDisplayStatus(fullscreen ? 'fullscreen' : 'connected', fullscreen)
    postPlaybackState()
  }

  /** 控制台只向已连接的观众 owner 发送路径命令；观众自身导航不限定目标。 */
  function buildTargetOwnerField(): { targetOwnerEpoch?: number } {
    if (options.role !== 'console' || activeDisplayOwnerEpoch.value === null) return {}
    return { targetOwnerEpoch: activeDisplayOwnerEpoch.value }
  }

  onMounted(() => {
    const initialPage = pages.value.find(page => page.path === currentPath.value) ?? pages.value[0]
    if (initialPage && !router) {
      currentPath.value = initialPage.path
    }
    if (!router || options.role === 'display') applyStoredSyncMessage()
    if (options.channelId && isPresenterStorageSupported()) {
      window.addEventListener('storage', handleStorageMessage)
    }

    if (!options.channelId) return
    if (typeof BroadcastChannel === 'undefined') {
      channelSupported.value = isPresenterStorageSupported()
    } else {
      channel = new BroadcastChannel(`${CHANNEL_NAME_PREFIX}${options.channelId}`)
      channel.addEventListener('message', handleChannelMessage as EventListener)
    }
    // 握手对两种通道都生效，避免降级后控制台一直拿不到观众 owner。
    if (options.role === 'display') {
      postMessage({ type: 'ready' })
      postDisplayStatus(document.fullscreenElement ? 'fullscreen' : 'connected', Boolean(document.fullscreenElement))
    } else {
      postState()
    }
  })

  onBeforeUnmount(() => {
    if (options.role === 'console') {
      postClose()
    } else if (options.role === 'display') {
      postDisplayStatus('closed', false)
    }
    channel?.removeEventListener('message', handleChannelMessage as EventListener)
    channel?.close()
    channel = null
    window.removeEventListener('storage', handleStorageMessage)
  })

  if (router) {
    watch(() => router.currentRoute.value.path, path => {
      if (!pages.value.some(page => page.path === path)) return
      currentPath.value = path
      if (path === remotePath) { remotePath = ''; return }
      postMessage({
        type: 'navigate',
        currentPath: path,
        playback: playbackSnapshot.value,
        ...buildTargetOwnerField(),
      }, nextCommandId())
    })
  }

  watch(currentPage, (page) => {
    if (!router && page && currentPath.value !== page.path) {
      currentPath.value = page.path
    }
  })

  watch(viewMode, () => {
    if (options.role === 'console' && !applyingRemoteView) {
      postState()
    }
  })

  return {
    pages,
    pageViewport,
    currentPath,
    currentPage,
    nextPage,
    previousPage,
    canGoPrevious,
    canGoNext,
    displayStatus,
    displayAvailable,
    viewMode,
    tileSize,
    channelSupported,
    playbackSnapshot,
    remotePlayback,
    updatePlayback,
    navigateTo,
    goPrevious,
    goNext,
    setTileSize,
    postState,
    postPlaybackState,
    sendPlaybackCommand,
    postClose,
    postDisplayStatus,
  }

  /**
   * 写入 localStorage 兜底同步消息；实时命令/回执使用独立键，避免覆盖页面恢复快照。
   * @param message 已补齐信封的协议消息
   */
  function writeStoredSyncMessage(message: PresenterSyncMessage): void {
    if (!options.channelId || !isPresenterStorageSupported()) {
      return
    }
    const storedMessage: PresenterStoredMessage = {
      sourceId: controllerId,
      sentAt: now(),
      message,
    }
    try {
      const key = isPresenterPersistedMessage(message)
        ? buildPresenterStorageKey(options.channelId)
        : buildPresenterEventStorageKey(options.channelId)
      localStorage.setItem(key, JSON.stringify(storedMessage))
    } catch {
      // localStorage 只是 BroadcastChannel 的兜底通道，失败时不影响主同步链路。
    }
  }

  /**
   * 读取并应用已持久化的最新同步消息；仍通过接收器去重与校验身份。
   */
  function applyStoredSyncMessage(): void {
    if (!options.channelId || !isPresenterStorageSupported()) {
      return
    }
    const storedMessage = parseStoredSyncMessage(localStorage.getItem(buildPresenterStorageKey(options.channelId)))
    if (!storedMessage || storedMessage.sourceId === controllerId) {
      return
    }
    const result = receiver.receive(storedMessage.message)
    if (!result.accepted || !result.received) return
    const { message } = result.received
    if (message.type !== 'navigate' && message.type !== 'state-sync') return
    remotePlayback.value = result.received
    applyIncomingState(message)
  }
}

/**
 * 从 Runtime 路由配置构建可演讲页面列表。
 * @param configs Runtime 路由配置
 * @returns 按页码排序的页面列表
 */
export function buildPresenterPages(configs: RouteConfig[]): PresenterPage[] {
  const pages: PresenterPage[] = []
  for (const route of configs) {
    if (route.children?.length) {
      for (const child of route.children) {
        appendPresenterPage(pages, child, `/${route.path}/${child.path}`)
      }
      continue
    }
    appendPresenterPage(pages, route, `/${route.path}`)
  }
  return pages.sort((left, right) => left.pageNumber - right.pageNumber)
}

/**
 * 把单个 Runtime 路由追加为演讲页。
 * @param target 目标列表
 * @param route 路由配置
 * @param path 页面路径
 */
function appendPresenterPage(target: PresenterPage[], route: RouteConfig, path: string): void {
  if (route.meta?.hidden || route.pageNumber === undefined) {
    return
  }
  const componentPath = typeof route.meta?.componentPath === 'string' ? route.meta.componentPath : ''
  const speakerNotes = typeof route.meta?.speakerNotes === 'string' ? route.meta.speakerNotes : ''
  target.push({
    path: normalizePresenterRoutePath(path.replace(/\/+/g, '/')),
    title: route.title,
    pageNumber: route.pageNumber,
    componentPath,
    speakerNotes,
  })
}

/**
 * 读取本地持久化的平铺尺寸。
 * @returns 合法的平铺尺寸
 */
function readStoredTileSize(): number {
  if (typeof localStorage === 'undefined') {
    return DEFAULT_TILE_SIZE
  }
  const storedText = localStorage.getItem(TILE_SIZE_STORAGE_KEY)
  if (!storedText) {
    return DEFAULT_TILE_SIZE
  }
  const storedValue = Number(storedText)
  return clampTileSize(Number.isFinite(storedValue) ? storedValue : DEFAULT_TILE_SIZE)
}

/**
 * 判断消息是否使用持久化快照键；其它消息仅供已挂载窗口实时接收。
 * @param message 协议消息
 * @returns 是否为持久化同步消息
 */
function isPresenterPersistedMessage(
  message: PresenterSyncMessage,
): message is PresenterSyncStateMessage
  | Extract<PresenterSyncMessage, { type: 'navigate' }>
  | Extract<PresenterSyncMessage, { type: 'close' }>
  | PresenterSyncDisplayStatusMessage {
  return message.type === 'state-sync'
    || message.type === 'navigate'
    || message.type === 'close'
    || message.type === 'display-status'
}

/**
 * 判断字符串是否为合法观众窗口状态。
 * @param state 状态值
 * @returns 是否合法
 */
function isPresenterDisplayStatusState(state: unknown): state is PresenterDisplayStatusState {
  return state === 'unknown'
    || state === 'connected'
    || state === 'windowed'
    || state === 'fullscreen'
    || state === 'closed'
}

/**
 * 构建演讲模式本地同步键。
 * @param channelId 通信频道 ID
 * @returns localStorage key
 */
export function buildPresenterStorageKey(channelId: string): string {
  return `${SYNC_STORAGE_KEY_PREFIX}${channelId}`
}

/** 构建实时事件同步键；挂载恢复只读取快照键，不重放旧放映命令。 */
function buildPresenterEventStorageKey(channelId: string): string {
  return `${EVENT_STORAGE_KEY_PREFIX}${channelId}`
}

/**
 * 写入演讲模式入口的初始导航状态，供观众页先于控制台加载时兜底读取。
 * @param channelId 通信频道 ID
 * @param currentPath 当前演讲页路径
 * @param autoAdvance 观众窗口继承的初始自动/手动模式
 * @param artifactIdentity 产物身份；默认读取当前 Runtime 产物
 */
export function writePresenterInitialNavigateMessage(
  channelId: string,
  currentPath: string,
  autoAdvance = false,
  artifactIdentity = resolvePresenterArtifactIdentity(),
): void {
  if (!channelId || !isPresenterStorageSupported()) {
    return
  }
  const path = normalizePresenterRoutePath(currentPath)
  const storedMessage: PresenterStoredMessage = {
    sourceId: 'presenter-entry',
    sentAt: Date.now(),
    message: {
      protocol: PRESENTER_SYNC_PROTOCOL_VERSION,
      channelId,
      artifactIdentity,
      sourceId: 'presenter-entry',
      role: 'console',
      ownerEpoch: 0,
      revision: 0,
      eventId: 'presenter-entry:1',
      type: 'navigate',
      currentPath: path,
      playback: {
        state: 'stopped',
        currentPath: path,
        remainingMs: 0,
        delayMs: null,
        waitingForMedia: false,
        autoAdvanceEnabled: autoAdvance,
        index: 0,
        total: 0,
      },
    },
  }
  try {
    localStorage.setItem(buildPresenterStorageKey(channelId), JSON.stringify(storedMessage))
  } catch {
    // localStorage 可能被浏览器策略禁用；此时仍可依赖 URL 初始路由和 BroadcastChannel。
  }
}

/**
 * 解析本地同步消息；协议版本、信封和消息体都必须合法。
 * @param value localStorage 原始值
 * @returns 合法消息或 null
 */
export function parseStoredSyncMessage(value: string | null): PresenterStoredMessage | null {
  if (!value) {
    return null
  }
  try {
    const parsed = JSON.parse(value) as PresenterStoredMessage
    if (!parsed || typeof parsed !== 'object' || typeof parsed.sourceId !== 'string') {
      return null
    }
    const message = parsePresenterSyncMessage(parsed.message)
    if (!message || message.sourceId !== parsed.sourceId) {
      return null
    }
    return { sourceId: parsed.sourceId, sentAt: Number(parsed.sentAt) || 0, message }
  } catch {
    return null
  }
}

/**
 * 创建当前控制器实例标识，避免处理自身写入的兜底消息。
 * @returns 实例 ID
 */
function createControllerId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `presenter-controller-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

let lastOwnerEpoch = 0

/** 同一浏览器内保证新控制台窗口的 owner epoch 严格递增，旧 owner 消息随后失效。 */
function createOwnerEpoch(): number {
  lastOwnerEpoch = Math.max(Date.now(), lastOwnerEpoch + 1)
  return lastOwnerEpoch
}

/**
 * 检查 localStorage 兜底通道是否可用。
 * @returns 是否支持 localStorage
 */
function isPresenterStorageSupported(): boolean {
  return typeof window !== 'undefined' && typeof localStorage !== 'undefined'
}

/**
 * 写入本地持久化的平铺尺寸。
 * @param value 合法的平铺尺寸
 */
function writeStoredTileSize(value: number): void {
  if (typeof localStorage === 'undefined') {
    return
  }
  localStorage.setItem(TILE_SIZE_STORAGE_KEY, String(value))
}

/**
 * 限制平铺尺寸范围。
 * @param value 原始尺寸
 * @returns 合法尺寸
 */
function clampTileSize(value: number): number {
  if (!Number.isFinite(value)) {
    return DEFAULT_TILE_SIZE
  }
  return Math.min(MAX_TILE_SIZE, Math.max(MIN_TILE_SIZE, Math.round(value)))
}
