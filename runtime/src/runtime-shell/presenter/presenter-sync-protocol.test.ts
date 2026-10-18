// @vitest-environment jsdom
/** 文件功能：验证演讲同步协议的版本/身份校验、去重、owner/revision 顺序与本地时钟基准。 */

import { describe, expect, it } from 'vitest'

import {
  PRESENTER_SYNC_PROTOCOL_VERSION,
  PresenterSyncReceiver,
  PresenterSyncSender,
  isPresenterMessageForOwner,
  parsePresenterSyncMessage,
  type PresenterSyncIdentity,
  type PresenterSyncPlaybackSnapshot,
} from './presenter-sync-protocol'

const IDENTITY: PresenterSyncIdentity = {
  channelId: 'channel-1',
  artifactIdentity: 'artifact-1',
  sourceId: 'display-1',
  role: 'display',
  ownerEpoch: 100,
}

const PLAYBACK: PresenterSyncPlaybackSnapshot = {
  state: 'playing',
  currentPath: '/a',
  remainingMs: 5000,
  delayMs: 8000,
  waitingForMedia: false,
  index: 0,
  total: 2,
}

/** 构造带完整信封的频道消息。 */
function buildMessage(overrides: Record<string, unknown> = {}) {
  return {
    protocol: PRESENTER_SYNC_PROTOCOL_VERSION,
    channelId: 'channel-1',
    artifactIdentity: 'artifact-1',
    sourceId: 'console-1',
    role: 'console',
    ownerEpoch: 10,
    revision: 1,
    eventId: 'console-1:1',
    type: 'state-sync',
    currentPath: '/a',
    viewMode: 'focus',
    tileSize: 300,
    playback: PLAYBACK,
    ...overrides,
  }
}

describe('PresenterSyncSender', () => {
  it('逐条递增 revision 与 eventId，并保留命令 ID', () => {
    const sender = new PresenterSyncSender({ ...IDENTITY, sourceId: 'console-1', ownerEpoch: 10 })
    const first = sender.create({ type: 'ready' })
    const second = sender.create({ type: 'navigate', currentPath: '/b', playback: PLAYBACK }, 'command-1')

    expect(first).toMatchObject({
      protocol: 2,
      channelId: 'channel-1',
      artifactIdentity: 'artifact-1',
      sourceId: 'console-1',
      ownerEpoch: 10,
      revision: 1,
    })
    expect(second.revision).toBe(2)
    expect(second.eventId).not.toBe(first.eventId)
    expect(second.commandId).toBe('command-1')
  })
})

describe('parsePresenterSyncMessage', () => {
  it('拒绝旧协议与缺失身份字段', () => {
    expect(parsePresenterSyncMessage(buildMessage())).not.toBeNull()
    expect(parsePresenterSyncMessage(buildMessage({ protocol: 1 }))).toBeNull()
    expect(parsePresenterSyncMessage(buildMessage({ channelId: '' }))).toBeNull()
    expect(parsePresenterSyncMessage(buildMessage({ artifactIdentity: undefined }))).toBeNull()
    expect(parsePresenterSyncMessage(buildMessage({ role: undefined }))).toBeNull()
    expect(parsePresenterSyncMessage(buildMessage({ role: 'viewer' }))).toBeNull()
    expect(parsePresenterSyncMessage(buildMessage({ playback: { state: 'playing' } }))).toBeNull()
    expect(parsePresenterSyncMessage(buildMessage({ type: 'display-status', status: { state: 'bad' } }))).toBeNull()
    expect(parsePresenterSyncMessage(null)).toBeNull()
  })

  it('解析导航、关闭和观众状态消息', () => {
    expect(parsePresenterSyncMessage(buildMessage({
      type: 'navigate', currentPath: '/b', playback: { ...PLAYBACK, currentPath: '/b', index: 1 },
    }))).toMatchObject({ type: 'navigate', currentPath: '/b' })
    expect(parsePresenterSyncMessage(buildMessage({ type: 'close' }))).toMatchObject({ type: 'close' })
    expect(parsePresenterSyncMessage(buildMessage({
      type: 'display-status',
      status: { state: 'fullscreen', isFullscreen: true, updatedAt: 123 },
    }))).toMatchObject({ type: 'display-status', status: { state: 'fullscreen' } })
  })

  it('解析放映命令、播放快照与目标 owner', () => {
    expect(parsePresenterSyncMessage(buildMessage({
      type: 'playback-command',
      action: 'pause',
      targetOwnerEpoch: 100,
    }))).toMatchObject({
      type: 'playback-command',
      action: 'pause',
      targetOwnerEpoch: 100,
    })
    expect(parsePresenterSyncMessage(buildMessage({
      type: 'playback-state',
      playback: { ...PLAYBACK, state: 'paused', remainingMs: 1200 },
    }))).toMatchObject({
      type: 'playback-state',
      playback: { state: 'paused', remainingMs: 1200 },
    })
    expect(parsePresenterSyncMessage(buildMessage({ type: 'playback-command', action: 'restart' }))).toBeNull()
    expect(parsePresenterSyncMessage(buildMessage({
      type: 'navigate', currentPath: '/b', playback: PLAYBACK, targetOwnerEpoch: -1,
    }))).toBeNull()
  })

  it('目标 owner 缺省时兼容旧消息，存在时必须匹配', () => {
    expect(isPresenterMessageForOwner({}, 100)).toBe(true)
    expect(isPresenterMessageForOwner({ targetOwnerEpoch: 100 }, 100)).toBe(true)
    expect(isPresenterMessageForOwner({ targetOwnerEpoch: 99 }, 100)).toBe(false)
  })
})

describe('PresenterSyncReceiver', () => {
  it('用本地到达时间重建截止时间，不比较跨窗口 performance.now', () => {
    let now = 1_000
    const receiver = new PresenterSyncReceiver(IDENTITY, () => now)
    const first = receiver.receive(buildMessage())
    expect(first.accepted).toBe(true)
    expect(first.received?.receivedAt).toBe(1_000)
    expect(first.received?.deadline).toBe(6_000)

    now = 3_000
    const second = receiver.receive(buildMessage({
      eventId: 'console-1:2', revision: 2, playback: { ...PLAYBACK, remainingMs: 2500 },
    }))
    expect(second.received?.deadline).toBe(5_500)
    expect(receiver.getLatest()?.message).toMatchObject({ revision: 2 })

    now = 4_000
    const playbackState = receiver.receive(buildMessage({
      eventId: 'console-1:3', revision: 3, type: 'playback-state', playback: { ...PLAYBACK, remainingMs: 700 },
    }))
    expect(playbackState.accepted).toBe(true)
    expect(playbackState.received?.deadline).toBe(4_700)
    expect(receiver.getLatest()?.message).toMatchObject({ type: 'playback-state' })
  })

  it('拒绝自身、频道/产物不匹配、重复事件与重复命令', () => {
    const receiver = new PresenterSyncReceiver(IDENTITY, () => 0)
    expect(receiver.receive(buildMessage({ sourceId: 'display-1' }))).toMatchObject({ accepted: false, reason: 'self' })
    expect(receiver.receive(buildMessage({ channelId: 'other' }))).toMatchObject({ accepted: false, reason: 'channel' })
    expect(receiver.receive(buildMessage({ artifactIdentity: 'other' }))).toMatchObject({ accepted: false, reason: 'artifact' })

    const message = buildMessage()
    expect(receiver.receive(message).accepted).toBe(true)
    expect(receiver.receive(message)).toMatchObject({ accepted: false, reason: 'duplicate' })
    expect(receiver.receive(buildMessage({ eventId: 'console-1:2', revision: 2, commandId: 'command-1' })).accepted).toBe(true)
    expect(receiver.receive(buildMessage({
      eventId: 'console-1:3', revision: 3, commandId: 'command-1',
    }))).toMatchObject({ accepted: false, reason: 'duplicate-command' })
  })

  it('owner 水位按角色隔离，观众 owner 不会阻塞后续控制台命令', () => {
    const receiver = new PresenterSyncReceiver(IDENTITY, () => 0)
    expect(receiver.receive(buildMessage({
      role: 'console', ownerEpoch: 10, revision: 1, eventId: 'console-1:1',
    })).accepted).toBe(true)
    expect(receiver.receive(buildMessage({
      role: 'display', sourceId: 'display-new', ownerEpoch: 99, revision: 1, eventId: 'display-new:1',
    })).accepted).toBe(true)
    expect(receiver.receive(buildMessage({
      role: 'console', ownerEpoch: 11, revision: 2, eventId: 'console-1:2',
    })).accepted).toBe(true)
    expect(receiver.receive(buildMessage({
      role: 'console', ownerEpoch: 9, revision: 3, eventId: 'console-1:3',
    }))).toMatchObject({ accepted: false, reason: 'stale-owner' })
  })

  it('拒绝旧 revision 与旧 owner，新 owner 可接管并重置 revision', () => {
    const receiver = new PresenterSyncReceiver(IDENTITY, () => 0)
    expect(receiver.receive(buildMessage()).accepted).toBe(true)
    expect(receiver.receive(buildMessage({ eventId: 'console-1:2', revision: 1 })))
      .toMatchObject({ accepted: false, reason: 'stale-revision' })
    expect(receiver.receive(buildMessage({ eventId: 'console-1:3', revision: 2 })).accepted).toBe(true)

    expect(receiver.receive(buildMessage({
      sourceId: 'console-old', ownerEpoch: 5, revision: 9, eventId: 'console-old:1',
    }))).toMatchObject({ accepted: false, reason: 'stale-owner' })

    expect(receiver.receive(buildMessage({
      sourceId: 'console-2', ownerEpoch: 20, revision: 1, eventId: 'console-2:1',
    })).accepted).toBe(true)
    expect(receiver.receive(buildMessage({
      sourceId: 'console-1', ownerEpoch: 10, revision: 3, eventId: 'console-1:4',
    }))).toMatchObject({ accepted: false, reason: 'stale-owner' })

    expect(receiver.receive(buildMessage({
      sourceId: 'console-2', ownerEpoch: 20, revision: 0, eventId: 'console-2:2',
    }))).toMatchObject({ accepted: false, reason: 'stale-revision' })
  })

  it('观众状态不抢占 owner 水位，旧控制台不能借 ready 覆盖播放快照', () => {
    const receiver = new PresenterSyncReceiver(IDENTITY, () => 0)
    expect(receiver.receive(buildMessage({
      sourceId: 'console-old', ownerEpoch: 1, revision: 1, eventId: 'console-old:1', type: 'close',
    })).accepted).toBe(true)
    expect(receiver.receive(buildMessage({
      sourceId: 'console-new', ownerEpoch: 2, revision: 1, eventId: 'console-new:1',
    })).accepted).toBe(true)
    expect(receiver.receive(buildMessage({
      sourceId: 'display-2', ownerEpoch: 0, revision: 1, eventId: 'display-2:1',
      type: 'display-status', status: { state: 'connected', isFullscreen: false, updatedAt: 1 },
    })).accepted).toBe(true)
    expect(receiver.getLatest()?.message).toMatchObject({ sourceId: 'console-new', type: 'state-sync' })
  })
})
