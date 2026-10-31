/** 文件功能：Presenter 非浏览器回归的消息队列与配置夹具，只模拟跨窗口投递。 */
import { createApp, defineComponent, nextTick, type App } from 'vue'
import { vi } from 'vitest'
import { setRuntimePreloadedConfig } from '@/core/utils/path'
import { reloadAllConfigs } from '@/core/utils/config'
import { usePresenterController } from './usePresenterController'
import type { PresenterSyncRole, PresenterSyncIntentAction } from './presenter-sync-protocol'
export const apps: App[] = []
export const messages: Array<() => void> = []
export class FakePresenterChannel {
  static instances = new Set<FakePresenterChannel>()
  onmessage: ((event: { data: unknown }) => void) | null = null
  constructor(readonly name: string) { FakePresenterChannel.instances.add(this) }
  /** 排队复制消息，避免同步递归掩盖实际握手问题。 */
  postMessage(data: unknown): void {
    for (const target of FakePresenterChannel.instances) if (target !== this && target.name === this.name) messages.push(() => { if (FakePresenterChannel.instances.has(target)) target.onmessage?.({ data: structuredClone(data) }) })
  }
  close(): void { FakePresenterChannel.instances.delete(this) }
}
/** 只提供目录 fixture，不启动任何服务、媒体或 Renderer。 */
export async function preparePresenterFixture(): Promise<void> {
  vi.stubGlobal('BroadcastChannel', FakePresenterChannel)
  setRuntimePreloadedConfig({ app: {}, routes: { playback: { schemaVersion: 4 }, routes: [
    { route: 'a', component: '@/views/a.vue', meta: { title: 'A', order: 1, speakerNotes: '备注' } },
    { route: 'b', component: '@/views/b.vue', meta: { title: 'B', order: 2 } },
  ] }, icons: { static_icons: [] } })
  await reloadAllConfigs()
}
/** 在独立 Vue 宿主安装控制器，可注入真实 Deck 动作或观察回调。 */
export function mountPresenter(role: PresenterSyncRole, ownerEpoch: number, onIntent?: (action: PresenterSyncIntentAction) => void) {
  let controller!: ReturnType<typeof usePresenterController>
  const app = createApp(defineComponent({ setup() { controller = usePresenterController({ role, channelId: 'test', artifactIdentity: 'artifact', initialPath: '/a', ownerEpoch, onIntent }); return () => null } }))
  const node = document.createElement('div'); document.body.appendChild(node); app.mount(node); apps.push(app)
  return { controller, app }
}
/** 有界排空握手与状态队列，消息循环将显式导致测试失败。 */
export async function flushPresenterMessages(): Promise<void> {
  let count = 0
  while (messages.length) { if (++count > 100) throw new Error('消息循环'); messages.shift()!(); await nextTick() }
}
/** 逆序卸载，保证关闭状态在频道释放前投递；测试结束不留下全局监听。 */
export function cleanupPresenterFixture(): void {
  for (const app of apps.splice(0).reverse()) app.unmount()
  messages.length = 0; FakePresenterChannel.instances.clear(); localStorage.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals(); setRuntimePreloadedConfig(undefined); document.body.innerHTML = ''
}
