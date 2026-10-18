/**
 * 文件功能：定义演讲者双窗口同步协议、消息校验、去重与本地时钟基准重建。
 *
 * 协议只承载命令与可验证状态，不驱动第二个调度器。跨窗口不比较 performance.now：
 * 接收方以本地到达时间和消息里的 remainingMs 重建截止时间。
 */

import { getRuntimePreloadedConfig, getRuntimePreviewContext } from '@/core/utils/path'

export const PRESENTER_SYNC_PROTOCOL_VERSION = 2
const MAX_SEEN_EVENTS = 256

export type PresenterSyncViewMode = 'focus' | 'grid'
export type PresenterSyncPlaybackState =
  | 'stopped'
  | 'preparing'
  | 'playing'
  | 'paused'
  | 'ended'
  | 'blocked'
  | 'error'

export interface PresenterSyncPlaybackSnapshot {
  state: PresenterSyncPlaybackState
  currentPath: string
  remainingMs: number
  /** timer 的停留时间；manual/media_end 等待时为 null。 */
  delayMs: number | null
  waitingForMedia: boolean
  index: number
  total: number
}

export interface PresenterSyncEnvelope {
  protocol: number
  channelId: string
  artifactIdentity: string
  sourceId: string
  ownerEpoch: number
  revision: number
  eventId: string
  commandId?: string
}

export interface PresenterSyncStateMessage extends PresenterSyncEnvelope {
  type: 'state-sync'
  currentPath: string
  viewMode: PresenterSyncViewMode
  tileSize: number
  playback: PresenterSyncPlaybackSnapshot
}

export interface PresenterSyncNavigateMessage extends PresenterSyncEnvelope {
  type: 'navigate'
  currentPath: string
  playback: PresenterSyncPlaybackSnapshot
}

export interface PresenterSyncReadyMessage extends PresenterSyncEnvelope {
  type: 'ready'
}

export interface PresenterSyncCloseMessage extends PresenterSyncEnvelope {
  type: 'close'
}

export interface PresenterSyncDisplayStatusMessage extends PresenterSyncEnvelope {
  type: 'display-status'
  status: {
    state: 'unknown' | 'connected' | 'windowed' | 'fullscreen' | 'closed'
    isFullscreen: boolean
    updatedAt: number
  }
}

export type PresenterSyncMessage =
  | PresenterSyncStateMessage
  | PresenterSyncNavigateMessage
  | PresenterSyncReadyMessage
  | PresenterSyncCloseMessage
  | PresenterSyncDisplayStatusMessage

/** 发送方只需提供消息体；协议版本、身份、epoch、revision 与 eventId 由 Sender 补齐。 */
export type PresenterSyncMessageBody =
  | Omit<PresenterSyncStateMessage, keyof PresenterSyncEnvelope>
  | Omit<PresenterSyncNavigateMessage, keyof PresenterSyncEnvelope>
  | Omit<PresenterSyncReadyMessage, keyof PresenterSyncEnvelope>
  | Omit<PresenterSyncCloseMessage, keyof PresenterSyncEnvelope>
  | Omit<PresenterSyncDisplayStatusMessage, keyof PresenterSyncEnvelope>

export type PresenterSyncRejectReason =
  | 'invalid'
  | 'self'
  | 'duplicate'
  | 'duplicate-command'
  | 'channel'
  | 'artifact'
  | 'stale-owner'
  | 'stale-revision'

export interface PresenterSyncIdentity {
  channelId: string
  artifactIdentity: string
  sourceId: string
  ownerEpoch: number
}

export interface ReceivedPresenterSync {
  message: PresenterSyncMessage
  receivedAt: number
  /** 本地时钟下的播放截止时间；仅 state-sync/navigate 携带。 */
  deadline: number | null
}

export interface PresenterSyncReceiveResult {
  accepted: boolean
  reason?: PresenterSyncRejectReason
  received?: ReceivedPresenterSync
}

/** 每次发送递增 revision；eventId 唯一，commandId 供命令跨通道去重。 */
export class PresenterSyncSender {
  private revision = 0
  private sequence = 0

  constructor(private readonly identity: PresenterSyncIdentity) {}

  /**
   * 构造完整信封。
   * @param body 消息体
   * @param commandId 可选命令 ID，同一命令重发时保持不变
   * @returns 可发送协议消息
   */
  create<T extends PresenterSyncMessageBody>(body: T, commandId?: string): T & PresenterSyncEnvelope {
    this.revision += 1
    this.sequence += 1
    const envelope: PresenterSyncEnvelope = {
      protocol: PRESENTER_SYNC_PROTOCOL_VERSION,
      channelId: this.identity.channelId,
      artifactIdentity: this.identity.artifactIdentity,
      sourceId: this.identity.sourceId,
      ownerEpoch: this.identity.ownerEpoch,
      revision: this.revision,
      eventId: `${this.identity.sourceId}:${this.sequence}`,
    }
    if (commandId) envelope.commandId = commandId
    return { ...body, ...envelope }
  }
}

/**
 * 接收并校验跨窗口消息。
 * 身份、协议、owner epoch、revision 与 event/command 去重都在进入业务处理前完成。
 */
export class PresenterSyncReceiver {
  private readonly seenEvents = new Set<string>()
  private readonly seenCommands = new Set<string>()
  private readonly revisions = new Map<string, number>()
  private ownerWatermark = -1
  private latest: ReceivedPresenterSync | null = null
  private readonly now: () => number

  constructor(
    private readonly identity: PresenterSyncIdentity,
    now: () => number = () => Date.now(),
  ) {
    this.now = now
  }

  /**
   * 校验消息并更新去重/顺序状态。
   * @param raw 通道或 storage 中的原始值
   * @returns 是否接受及拒绝原因
   */
  receive(raw: unknown): PresenterSyncReceiveResult {
    const message = parsePresenterSyncMessage(raw)
    if (!message) return { accepted: false, reason: 'invalid' }
    if (message.protocol !== PRESENTER_SYNC_PROTOCOL_VERSION) return { accepted: false, reason: 'invalid' }
    if (message.sourceId === this.identity.sourceId) return { accepted: false, reason: 'self' }
    if (message.channelId !== this.identity.channelId) return { accepted: false, reason: 'channel' }
    if (message.artifactIdentity !== this.identity.artifactIdentity) return { accepted: false, reason: 'artifact' }
    if (this.seenEvents.has(message.eventId)) return { accepted: false, reason: 'duplicate' }
    if (message.commandId && this.seenCommands.has(message.commandId)) {
      return { accepted: false, reason: 'duplicate-command' }
    }
    if (isAuthoritative(message)) {
      if (message.ownerEpoch < this.ownerWatermark) return { accepted: false, reason: 'stale-owner' }
      if (message.ownerEpoch > this.ownerWatermark) {
        this.ownerWatermark = message.ownerEpoch
        this.revisions.clear()
      }
      const lastRevision = this.revisions.get(message.sourceId) ?? -1
      if (message.revision <= lastRevision) return { accepted: false, reason: 'stale-revision' }
      this.revisions.set(message.sourceId, message.revision)
    }

    this.remember(this.seenEvents, message.eventId)
    if (message.commandId) this.remember(this.seenCommands, message.commandId)
    const receivedAt = this.now()
    const deadline = isPlaybackMessage(message)
      ? receivedAt + Math.max(0, Math.round(message.playback.remainingMs))
      : null
    const received: ReceivedPresenterSync = { message, receivedAt, deadline }
    if (isPlaybackMessage(message)) this.latest = received
    return { accepted: true, received }
  }

  /** 最近一次已接受的状态快照；用于新窗口或重连后恢复。 */
  getLatest(): ReceivedPresenterSync | null {
    return this.latest
  }

  private remember(target: Set<string>, value: string): void {
    target.add(value)
    if (target.size > MAX_SEEN_EVENTS) {
      target.delete(target.values().next().value!)
    }
  }
}

/** 校验并解析协议消息；任何字段不合法都返回 null，不猜测版本。 */
export function parsePresenterSyncMessage(value: unknown): PresenterSyncMessage | null {
  if (!isRecord(value)) return null
  if (value.protocol !== PRESENTER_SYNC_PROTOCOL_VERSION) return null
  if (!isNonEmptyString(value.channelId) || typeof value.artifactIdentity !== 'string') return null
  if (!isNonEmptyString(value.sourceId) || !isNonNegativeInteger(value.ownerEpoch)) return null
  if (!isNonNegativeInteger(value.revision) || !isNonEmptyString(value.eventId)) return null
  if (value.commandId !== undefined && !isNonEmptyString(value.commandId)) return null

  switch (value.type) {
    case 'state-sync': {
      const playback = parsePlayback(value.playback)
      if (!isNonEmptyString(value.currentPath) || !isViewMode(value.viewMode) || !playback) return null
      if (!Number.isFinite(value.tileSize)) return null
      return {
        ...baseEnvelope(value),
        type: 'state-sync',
        currentPath: value.currentPath,
        viewMode: value.viewMode,
        tileSize: Number(value.tileSize),
        playback,
      }
    }
    case 'navigate': {
      const playback = parsePlayback(value.playback)
      if (!isNonEmptyString(value.currentPath) || !playback) return null
      return { ...baseEnvelope(value), type: 'navigate', currentPath: value.currentPath, playback }
    }
    case 'ready':
      return { ...baseEnvelope(value), type: 'ready' }
    case 'close':
      return { ...baseEnvelope(value), type: 'close' }
    case 'display-status': {
      const status = value.status
      if (!isRecord(status) || !isDisplayStatusState(status.state) || !Number.isFinite(status.updatedAt)) return null
      return {
        ...baseEnvelope(value),
        type: 'display-status',
        status: {
          state: status.state,
          isFullscreen: Boolean(status.isFullscreen),
          updatedAt: Number(status.updatedAt),
        },
      }
    }
    default:
      return null
  }
}

/** 读取当前 Runtime 产物身份；standalone 没有产物时返回空串。 */
export function resolvePresenterArtifactIdentity(): string {
  const artifactId = getRuntimePreloadedConfig()?.manifest?.artifact_id
  if (typeof artifactId === 'string' && artifactId) return artifactId
  const previewArtifactId = getRuntimePreviewContext()?.artifactId
  return typeof previewArtifactId === 'string' ? previewArtifactId : ''
}

function baseEnvelope(value: Record<string, unknown>): PresenterSyncEnvelope {
  const envelope: PresenterSyncEnvelope = {
    protocol: PRESENTER_SYNC_PROTOCOL_VERSION,
    channelId: value.channelId as string,
    artifactIdentity: value.artifactIdentity as string,
    sourceId: value.sourceId as string,
    ownerEpoch: value.ownerEpoch as number,
    revision: value.revision as number,
    eventId: value.eventId as string,
  }
  if (typeof value.commandId === 'string') envelope.commandId = value.commandId
  return envelope
}

function parsePlayback(value: unknown): PresenterSyncPlaybackSnapshot | null {
  if (!isRecord(value)) return null
  if (!isPlaybackState(value.state) || !isNonEmptyString(value.currentPath)) return null
  if (!Number.isFinite(value.remainingMs) || !Number.isInteger(value.index) || !Number.isInteger(value.total)) return null
  if (value.delayMs !== null && !Number.isFinite(value.delayMs)) return null
  return {
    state: value.state,
    currentPath: value.currentPath,
    remainingMs: Math.max(0, Number(value.remainingMs)),
    delayMs: value.delayMs === null ? null : Number(value.delayMs),
    waitingForMedia: Boolean(value.waitingForMedia),
    index: Number(value.index),
    total: Number(value.total),
  }
}

function isAuthoritative(message: PresenterSyncMessage): boolean {
  return message.type === 'state-sync' || message.type === 'navigate' || message.type === 'close'
}

function isPlaybackMessage(
  message: PresenterSyncMessage,
): message is PresenterSyncStateMessage | PresenterSyncNavigateMessage {
  return message.type === 'state-sync' || message.type === 'navigate'
}

function isViewMode(value: unknown): value is PresenterSyncViewMode {
  return value === 'focus' || value === 'grid'
}

function isPlaybackState(value: unknown): value is PresenterSyncPlaybackState {
  return value === 'stopped'
    || value === 'preparing'
    || value === 'playing'
    || value === 'paused'
    || value === 'ended'
    || value === 'blocked'
    || value === 'error'
}

function isDisplayStatusState(value: unknown): value is PresenterSyncDisplayStatusMessage['status']['state'] {
  return value === 'unknown'
    || value === 'connected'
    || value === 'windowed'
    || value === 'fullscreen'
    || value === 'closed'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 0
}
