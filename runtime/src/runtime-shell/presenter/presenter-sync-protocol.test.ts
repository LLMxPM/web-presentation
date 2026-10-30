/** 文件功能：验证 Presenter v5 的原子状态、有限意图、严格版本/身份与 owner/修订单调性。 */
import { describe, expect, it } from 'vitest'
import { PresenterSyncReceiver, PresenterSyncSender, parsePresenterSyncMessage, type PresenterSyncIdentity } from './presenter-sync-protocol'
const consoleIdentity: PresenterSyncIdentity = { channelId: 'c', artifactIdentity: 'a', sourceId: 'console', role: 'console', ownerEpoch: 1 }
const displayIdentity: PresenterSyncIdentity = { ...consoleIdentity, sourceId: 'display', role: 'display', ownerEpoch: 10 }
/** 同一快照包括完整页面、阶段、保持与摘要，不能逐字段接收。 */
function state(sender = new PresenterSyncSender(displayIdentity)) {
  return sender.create({ type: 'state', ownerId: 'display', page: '/a', phase: 'playing', held: false, fullscreen: true, issue: null })
}
describe('Presenter v5', () => {
  it('原子状态只接受完整字段，旧 v4 与额外定位字段明确拒绝', () => {
    const message = state()
    expect(parsePresenterSyncMessage(message)).toEqual(message)
    expect(parsePresenterSyncMessage({ ...message, protocol: 4 })).toBeNull()
    expect(parsePresenterSyncMessage({ ...message, positionMs: 5 })).toBeNull()
    const { held: _held, ...incomplete } = message
    expect(parsePresenterSyncMessage(incomplete)).toBeNull()
  })
  it.each(['pause', 'resume', 'seek', 'set-auto-advance'])('不提供旧动作 %s', action => {
    expect(parsePresenterSyncMessage({ ...new PresenterSyncSender(consoleIdentity).create({ type: 'request-state' }), type: 'intent', ownerId: 'display', action })).toBeNull()
  })
  it.each(['start', 'next', 'stop', 'hold', 'release', 'retry', 'close'] as const)('有限动作 %s 只针对当前 owner', action => {
    const sender = new PresenterSyncSender(consoleIdentity), receiver = new PresenterSyncReceiver(displayIdentity)
    expect(receiver.receive(sender.create({ type: 'intent', ownerId: 'old', action })).reason).toBe('owner')
    expect(receiver.receive(sender.create({ type: 'intent', ownerId: 'display', action })).accepted).toBe(true)
  })
  it('不重放重复意图或旧修订，乱序 state 不能回退页面与阶段', () => {
    const sender = new PresenterSyncSender(displayIdentity), receiver = new PresenterSyncReceiver(consoleIdentity)
    const older = state(sender), newer = { ...state(sender), page: '/b', phase: 'blocked' as const, issue: { code: 'MEDIA_PERMISSION', message: '请在观众窗口允许播放' } }
    expect(receiver.receive(newer).message).toEqual(newer)
    expect(receiver.receive(older).reason).toBe('stale-revision')
    expect(receiver.receive(newer).reason).toBe('stale-revision')
    const display = new PresenterSyncReceiver(displayIdentity), intent = new PresenterSyncSender(consoleIdentity).create({ type: 'intent', ownerId: 'display', action: 'next' })
    expect(display.receive(intent).accepted).toBe(true)
    expect(display.receive(intent).reason).toBe('stale-revision')
  })
  it('新 owner 接管后旧 owner 的更高 revision 也不能复活', () => {
    const receiver = new PresenterSyncReceiver(consoleIdentity), old = new PresenterSyncSender(displayIdentity)
    expect(receiver.receive(state(old)).accepted).toBe(true)
    const next = new PresenterSyncSender({ ...displayIdentity, sourceId: 'new', ownerEpoch: 11 })
    expect(receiver.receive({ ...state(next), ownerId: 'new' }).accepted).toBe(true)
    expect(receiver.receive({ ...state(old), revision: 100 }).reason).toBe('stale-owner')
    expect(receiver.ownerId).toBe('new')
  })
  it('同代 owner 按 id 稳定排序；新观众也拒绝针对旧窗口的意图', () => {
    const receiver = new PresenterSyncReceiver({ ...displayIdentity, sourceId: 'z' })
    expect(receiver.receive(state()).reason).toBe('stale-owner')
    expect(receiver.receive(new PresenterSyncSender(consoleIdentity).create({ type: 'intent', ownerId: 'display', action: 'next' })).reason).toBe('owner')
  })
  it('跨频道、跨产物、伪造 owner、无限摘要和非法导航都拒绝', () => {
    const receiver = new PresenterSyncReceiver(consoleIdentity), message = state()
    expect(receiver.receive({ ...message, channelId: 'other' }).reason).toBe('identity')
    expect(receiver.receive({ ...message, artifactIdentity: 'other' }).reason).toBe('identity')
    expect(parsePresenterSyncMessage({ ...message, ownerId: 'forged' })).toBeNull()
    expect(parsePresenterSyncMessage({ ...message, issue: { code: 'x', message: 'x'.repeat(501) } })).toBeNull()
    const sender = new PresenterSyncSender(consoleIdentity)
    for (const page of ['//evil', 'https://evil', '/x?y=1', '/x#z']) expect(parsePresenterSyncMessage(sender.create({ type: 'intent', ownerId: 'display', action: 'navigate', page }))).toBeNull()
  })
})
