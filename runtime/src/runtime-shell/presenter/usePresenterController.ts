/**
 * 文件用途：管理 Runtime 演讲模式页面列表、当前页、平铺尺寸与窗口 BroadcastChannel 同步。
 */

import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { routerKey } from 'vue-router'
import { getRuntimeSession } from '@/core/router/runtime-session'

import { appPageConfig, routeConfigs } from '@/core/utils/config'
import type { RouteConfig } from '@/core/types/navigation'
import { normalizePresenterRoutePath } from '@/runtime-shell/presenter/presenter-url'

export type PresenterViewMode = 'focus' | 'grid'
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

interface PresenterStateMessage {
  type: 'state-sync'
  currentPath: string
  viewMode: PresenterViewMode
  tileSize: number
}

interface PresenterNavigateMessage {
  type: 'navigate'
  currentPath: string
}

interface PresenterReadyMessage {
  type: 'ready'
}

interface PresenterCloseMessage {
  type: 'close'
}

interface PresenterDisplayStatusMessage {
  type: 'display-status'
  status: PresenterDisplayStatus
}

type PresenterMessageBody =
  | PresenterStateMessage
  | PresenterNavigateMessage
  | PresenterReadyMessage
  | PresenterCloseMessage
  | PresenterDisplayStatusMessage

type PresenterMessage = PresenterMessageBody & { eventId?: string; sourceId?: string }

export interface PresenterStoredMessage {
  sourceId: string
  sentAt: number
  message: PresenterStateMessage | PresenterNavigateMessage | PresenterCloseMessage | PresenterDisplayStatusMessage
}

interface PresenterControllerOptions {
  channelId: string
  initialPath?: string
  role: PresenterRole
}

const TILE_SIZE_STORAGE_KEY = 'web-presentation.presenter.tileSize'
const CHANNEL_NAME_PREFIX = 'web-presentation:presenter:'
const SYNC_STORAGE_KEY_PREFIX = 'web-presentation.presenter.sync.'
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
  const seenEvents = new Set<string>()
  let sequence = 0
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
  const controllerId = createControllerId()
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
      postMessage({ type: 'navigate', currentPath: normalizedPath })
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
  function postState(): void {
    postMessage({
      type: 'state-sync',
      currentPath: currentPath.value,
      viewMode: viewMode.value,
      tileSize: tileSize.value,
    })
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
        updatedAt: Date.now(),
      },
    })
  }

  /**
   * 发送频道消息。
   * @param message 消息体
   */
  function postMessage(message: PresenterMessage): void {
    const envelope: PresenterMessage = { ...message, sourceId: controllerId, eventId: `${controllerId}:${++sequence}` }
    channel?.postMessage(envelope)
    writeStoredSyncMessage(envelope)
  }

  /**
   * 处理 BroadcastChannel 收到的跨窗口消息。
   * @param event 消息事件
   */
  function handleChannelMessage(event: MessageEvent<PresenterMessage>): void {
    const message = event.data
    if (!message || typeof message !== 'object') {
      return
    }
    if (message.sourceId === controllerId || (message.eventId && seenEvents.has(message.eventId))) return
    if (message.eventId) {
      seenEvents.add(message.eventId)
      if (seenEvents.size > 256) seenEvents.delete(seenEvents.values().next().value!)
    }
    if (message.type === 'ready' && options.role === 'console') {
      postState()
      return
    }
    if (message.type === 'state-sync' || message.type === 'navigate') {
      applyIncomingState(message)
      return
    }
    if (message.type === 'display-status') {
      applyDisplayStatus(message.status)
      return
    }
    if (message.type === 'close' && options.role === 'display') {
      window.close()
    }
  }

  /**
   * 处理 localStorage 兜底同步消息。
   * @param event storage 事件
   */
  function handleStorageMessage(event: StorageEvent): void {
    if (!options.channelId || event.key !== buildPresenterStorageKey(options.channelId) || !event.newValue) {
      return
    }
    const storedMessage = parseStoredSyncMessage(event.newValue)
    if (!storedMessage || storedMessage.sourceId === controllerId) {
      return
    }
    handleChannelMessage({ data: storedMessage.message } as MessageEvent<PresenterMessage>)
  }

  /**
   * 应用外部窗口传来的页面和视图状态。
   * @param message 状态或导航消息
   */
  function applyIncomingState(message: PresenterStateMessage | PresenterNavigateMessage): void {
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
      updatedAt: Number.isFinite(status.updatedAt) ? status.updatedAt : Date.now(),
    }
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

    if (!options.channelId || typeof BroadcastChannel === 'undefined') {
      channelSupported.value = isPresenterStorageSupported()
      return
    }
    channel = new BroadcastChannel(`${CHANNEL_NAME_PREFIX}${options.channelId}`)
    channel.addEventListener('message', handleChannelMessage as EventListener)
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
      postMessage({ type: 'navigate', currentPath: path })
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
    viewMode,
    tileSize,
    channelSupported,
    navigateTo,
    goPrevious,
    goNext,
    setTileSize,
    postState,
    postClose,
    postDisplayStatus,
  }

  /**
   * 写入 localStorage 兜底同步消息。
   * @param message 频道消息
   */
  function writeStoredSyncMessage(message: PresenterMessage): void {
    if (!options.channelId || !isPresenterPersistedMessage(message) || !isPresenterStorageSupported()) {
      return
    }
    const storedMessage: PresenterStoredMessage = {
      sourceId: controllerId,
      sentAt: Date.now(),
      message,
    }
    try {
      localStorage.setItem(buildPresenterStorageKey(options.channelId), JSON.stringify(storedMessage))
    } catch {
      // localStorage 只是 BroadcastChannel 的兜底通道，失败时不影响主同步链路。
    }
  }

  /**
   * 读取并应用已持久化的最新同步消息。
   */
  function applyStoredSyncMessage(): void {
    if (!options.channelId || !isPresenterStorageSupported()) {
      return
    }
    const storedMessage = parseStoredSyncMessage(localStorage.getItem(buildPresenterStorageKey(options.channelId)))
    if (!storedMessage || storedMessage.sourceId === controllerId) {
      return
    }
    if (storedMessage.message.type === 'navigate' || storedMessage.message.type === 'state-sync') {
      applyIncomingState({ type: 'state-sync', currentPath: storedMessage.message.currentPath, viewMode: 'focus', tileSize: tileSize.value })
    }
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
 * 判断消息是否需要写入本地存储兜底通道。
 * @param message 频道消息
 * @returns 是否为可兜底同步的消息
 */
function isPresenterPersistedMessage(
  message: PresenterMessage,
): message is PresenterStateMessage | PresenterNavigateMessage | PresenterCloseMessage | PresenterDisplayStatusMessage {
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

/**
 * 写入演讲模式入口的初始导航状态，供观众页先于控制台加载时兜底读取。
 * @param channelId 通信频道 ID
 * @param currentPath 当前演讲页路径
 */
export function writePresenterInitialNavigateMessage(channelId: string, currentPath: string): void {
  if (!channelId || !isPresenterStorageSupported()) {
    return
  }
  const storedMessage: PresenterStoredMessage = {
    sourceId: 'presenter-entry',
    sentAt: Date.now(),
    message: {
      type: 'navigate',
      currentPath: normalizePresenterRoutePath(currentPath),
    },
  }
  try {
    localStorage.setItem(buildPresenterStorageKey(channelId), JSON.stringify(storedMessage))
  } catch {
    // localStorage 可能被浏览器策略禁用；此时仍可依赖 URL 初始路由和 BroadcastChannel。
  }
}

/**
 * 解析本地同步消息。
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
    if (!parsed.message || !isPresenterPersistedMessage(parsed.message)) {
      return null
    }
    return parsed
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
