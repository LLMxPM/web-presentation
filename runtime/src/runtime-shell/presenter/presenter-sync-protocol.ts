/** 文件功能：Presenter v5 只传有限意图与观众原子状态；版本、产物、owner 和修订共同拒绝迟到消息。 */
import { getRuntimePreloadedConfig, getRuntimePreviewContext } from '@/core/utils/path'

export const PRESENTER_SYNC_PROTOCOL_VERSION = 5
export type PresenterSyncViewMode = 'focus' | 'grid'
export type PresenterSyncRole = 'console' | 'display'
export type PresenterSyncPlaybackCommandAction = 'start' | 'next' | 'stop' | 'hold' | 'release' | 'retry' | 'navigate' | 'close'
export type PresenterPhase = 'stopped' | 'preparing' | 'playing' | 'blocked' | 'failed' | 'ended' | 'closed'
export interface PresenterIssue { code: string; message: string }
export interface PresenterPlaybackState {
  page: string
  phase: PresenterPhase
  held: boolean
  fullscreen: boolean
  issue: PresenterIssue | null
}
export interface PresenterSyncIdentity {
  channelId: string
  artifactIdentity: string
  sourceId: string
  role: PresenterSyncRole
  /** 仅用于窗口所有权排序，绝不作为播放时钟。 */
  ownerEpoch: number
}
export interface PresenterSyncEnvelope extends PresenterSyncIdentity { protocol: number; revision: number }
export type PresenterSyncMessageBody =
  | { type: 'request-state' }
  | ({ type: 'state'; ownerId: string } & PresenterPlaybackState)
  | { type: 'intent'; ownerId: string; action: PresenterSyncPlaybackCommandAction; page?: string }
export type PresenterSyncMessage = PresenterSyncEnvelope & PresenterSyncMessageBody
export type PresenterStateMessage = Extract<PresenterSyncMessage, { type: 'state' }>

/** 发送序号同时作为原子状态 revision；同一窗口永不回退。 */
export class PresenterSyncSender {
  private revision = 0
  constructor(private readonly identity: PresenterSyncIdentity) {}
  /** 由当前身份构造完整消息，不复用旧命令或持久化播放状态。 */
  create<T extends PresenterSyncMessageBody>(body: T): PresenterSyncEnvelope & T {
    return { ...body, ...this.identity, protocol: PRESENTER_SYNC_PROTOCOL_VERSION, revision: ++this.revision }
  }
}

/** 只接受完整且有界的 v5 消息；旧位置、倒计时、暂停字段不参与兼容。 */
export function parsePresenterSyncMessage(value: unknown): PresenterSyncMessage | null {
  if (!record(value) || value.protocol !== 5 || !text(value.channelId, 256) || !text(value.sourceId, 256)
    || typeof value.artifactIdentity !== 'string' || value.artifactIdentity.length > 512
    || !['console', 'display'].includes(String(value.role)) || !integer(value.ownerEpoch) || !integer(value.revision) || value.revision === 0) return null
  const envelope = ['protocol', 'channelId', 'artifactIdentity', 'sourceId', 'role', 'ownerEpoch', 'revision']
  let fields: string[]
  if (value.type === 'request-state') fields = ['type']
  else if (value.type === 'intent') {
    fields = ['type', 'ownerId', 'action', 'page']
    if (value.role !== 'console' || !text(value.ownerId, 256)
      || !['start', 'next', 'stop', 'hold', 'release', 'retry', 'navigate', 'close'].includes(String(value.action))
      || (value.action === 'navigate' ? !path(value.page) : value.page !== undefined)) return null
  } else if (value.type === 'state') {
    fields = ['type', 'ownerId', 'page', 'phase', 'held', 'fullscreen', 'issue']
    if (value.role !== 'display' || value.ownerId !== value.sourceId || !path(value.page)
      || !['stopped', 'preparing', 'playing', 'blocked', 'failed', 'ended', 'closed'].includes(String(value.phase))
      || typeof value.held !== 'boolean' || typeof value.fullscreen !== 'boolean'
      || (value.issue !== null && (!record(value.issue) || !text(value.issue.code, 128) || !text(value.issue.message, 500)
        || Object.keys(value.issue).some(key => !['code', 'message'].includes(key))))) return null
  } else return null
  if (Object.keys(value).some(key => !envelope.includes(key) && !fields.includes(key))) return null
  return value as unknown as PresenterSyncMessage
}

/** 一台观众调度者、每个来源单调修订；较新窗口接管后旧 owner 永不复活。 */
export class PresenterSyncReceiver {
  private readonly revisions = new Map<string, number>()
  private owner: { id: string; epoch: number } | null
  constructor(private readonly identity: PresenterSyncIdentity) {
    this.owner = identity.role === 'display' ? { id: identity.sourceId, epoch: identity.ownerEpoch } : null
  }
  get ownerId(): string | null { return this.owner?.id ?? null }
  /** 返回拒绝原因，便于协议测试；不会在接收端建立播放时钟或自动补发意图。 */
  receive(input: unknown): { accepted: boolean; reason?: string; message?: PresenterSyncMessage } {
    const message = parsePresenterSyncMessage(input)
    if (!message) return { accepted: false, reason: 'invalid' }
    if (message.sourceId === this.identity.sourceId) return { accepted: false, reason: 'self' }
    if (message.channelId !== this.identity.channelId || message.artifactIdentity !== this.identity.artifactIdentity) return { accepted: false, reason: 'identity' }
    if (message.revision <= (this.revisions.get(message.sourceId) ?? 0)) return { accepted: false, reason: 'stale-revision' }
    if (!this.revisions.has(message.sourceId) && this.revisions.size >= 64) return { accepted: false, reason: 'capacity' }
    if (message.type === 'state') {
      if (this.owner && message.ownerId !== this.owner.id
        && (message.ownerEpoch < this.owner.epoch || (message.ownerEpoch === this.owner.epoch && message.ownerId < this.owner.id))) return { accepted: false, reason: 'stale-owner' }
      this.owner = { id: message.ownerId, epoch: message.ownerEpoch }
    }
    if (message.type === 'intent' && (this.identity.role !== 'display' || this.owner?.id !== this.identity.sourceId || message.ownerId !== this.identity.sourceId)) return { accepted: false, reason: 'owner' }
    this.revisions.set(message.sourceId, message.revision)
    return { accepted: true, message }
  }
}

/** 产物身份来自预加载 manifest/预览上下文；跨产物频道不能互相控制。 */
export function resolvePresenterArtifactIdentity(): string {
  return getRuntimePreloadedConfig()?.manifest?.artifact_id ?? getRuntimePreviewContext()?.artifactId ?? ''
}
/** 消息记录只接受普通对象。 */
function record(value: unknown): value is Record<string, unknown> { return Boolean(value) && typeof value === 'object' && !Array.isArray(value) }
/** 字符串边界防止错误摘要或频道无限增长。 */
function text(value: unknown, max: number): value is string { return typeof value === 'string' && value.length > 0 && value.length <= max }
/** 路径必须是本地路由，不接受 URL、查询串或协议相对路径。 */
function path(value: unknown): value is string { return text(value, 2048) && value.startsWith('/') && !value.startsWith('//') && !/[?#\\]/.test(value) }
/** 序号与 owner 代际是安全整数，不接受浮点、布尔和负数。 */
function integer(value: unknown): value is number { return Number.isSafeInteger(value) && (value as number) >= 0 }
