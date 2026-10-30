// @vitest-environment jsdom
/** 文件功能：验证没有 BroadcastChannel 时的即时 storage 握手、命令去重及不读取遗留快照。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanupPresenterFixture, flushPresenterMessages, messages, mountPresenter, preparePresenterFixture } from './presenter-test-helpers'
beforeEach(async () => {
  await preparePresenterFixture(); vi.stubGlobal('BroadcastChannel', undefined)
  const original = Storage.prototype.setItem
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function(this: Storage, key, value) {
    original.call(this, key, value)
    if (key.includes('.v5.event.')) { const event = () => window.dispatchEvent(new StorageEvent('storage', { key, newValue: value })); messages.push(event, event) }
  })
})
afterEach(cleanupPresenterFixture)
it('两个实时通道的重复消息只执行一次，重开请求状态，不读存储的命令', async () => {
  const actions = vi.fn(), audience = mountPresenter('display', 10, actions), consoleView = mountPresenter('console', 1)
  await flushPresenterMessages()
  expect(consoleView.controller.remotePlayback.value?.phase).toBe('stopped')
  consoleView.controller.sendPlaybackCommand('next'); await flushPresenterMessages()
  expect(actions).toHaveBeenCalledTimes(1)
  audience.controller.updatePlayback({ page: '/b', phase: 'failed', held: false, issue: { code: 'PREPARE_FAILED', message: '资源准备失败' } }); await flushPresenterMessages()
  consoleView.app.unmount()
  const reopened = mountPresenter('console', 2); await flushPresenterMessages()
  expect(reopened.controller.remotePlayback.value).toMatchObject({ page: '/b', phase: 'failed' })
  expect(actions).toHaveBeenCalledTimes(1)
})
