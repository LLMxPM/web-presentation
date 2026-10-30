// @vitest-environment jsdom
/** 文件功能：验证 Presenter 面板只呈现观众原子状态，保持不表示页内暂停，媒体许可不远程重试。 */
import { createApp, nextTick } from 'vue'
import { afterEach, expect, it } from 'vitest'
import PresenterPlaybackPanel from './PresenterPlaybackPanel.vue'
import { PresenterSyncSender, type PresenterPhase } from './presenter-sync-protocol'
const cleanups: Array<() => void> = []
afterEach(() => { cleanups.splice(0).forEach(clean => clean()); document.body.innerHTML = '' })
/** 用完整原子消息挂载面板，记录用户意图。 */
function mount(phase: PresenterPhase, held = false) {
  const actions: string[] = [], node = document.createElement('div'); document.body.appendChild(node)
  const message = new PresenterSyncSender({ channelId: 'c', artifactIdentity: 'a', sourceId: 'd', role: 'display', ownerEpoch: 1 }).create({ type: 'state', ownerId: 'd', page: '/a', phase, held, fullscreen: true, issue: null })
  const app = createApp(PresenterPlaybackPanel, { playback: message, displayAvailable: true, canGoPrevious: true, canGoNext: true, pageLabel: '1 / 2', onCommand: (action: string) => actions.push(action) }); app.mount(node); cleanups.push(() => app.unmount())
  return { node, actions }
}
it('保持/释放只发有限意图，不显示自动切换或时间位置', async () => {
  const { node, actions } = mount('playing', true)
  expect(node.textContent).toContain('页内播放继续')
  node.querySelector<HTMLButtonElement>('[data-testid="presenter-playback-hold"]')?.click(); await nextTick()
  expect(actions).toEqual(['release'])
  expect(node.querySelector('input[type=range]')).toBeNull()
  expect(node.querySelector('[data-testid="presenter-playback-auto"]')).toBeNull()
})
it('受阻提示本窗口许可，只有失败才提供任务重试', () => {
  const { node } = mount('blocked')
  expect(node.textContent).toContain('请在观众窗口点击允许播放')
  expect(node.textContent).not.toContain('重试失败页')
  expect(mount('failed').node.textContent).toContain('重试失败页')
})
