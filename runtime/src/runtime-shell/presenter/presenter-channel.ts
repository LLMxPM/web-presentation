/** 文件功能：Presenter 的即时双通道传输；只接收实时 storage 事件，不读取或重放磁盘快照。 */
import type { PresenterSyncMessage } from './presenter-sync-protocol'

/** BroadcastChannel 与 storage 可重复投递，统一接收器负责修订去重；返回关闭句柄。 */
export function openPresenterChannel(channelId: string, receive: (value: unknown) => void) {
  const key = `web-presentation.presenter.v5.event.${channelId}`
  let channel: BroadcastChannel | null = null
  try { if (typeof BroadcastChannel !== 'undefined') channel = new BroadcastChannel(`web-presentation:presenter:v5:${channelId}`) } catch { /* storage 可作为实时后备通道。 */ }
  if (channel) channel.onmessage = event => receive(event.data)
  /** storage 只应用此刻收到的事件，不恢复历史命令。 */
  function onStorage(event: StorageEvent): void {
    if (event.key !== key || !event.newValue) return
    try { receive(JSON.parse(event.newValue)) } catch { /* 忽略无效的同源消息。 */ }
  }
  window.addEventListener('storage', onStorage)
  return {
    supported: Boolean(channel) || storageSupported(),
    /** 不排队或重试命令；新窗口用 request-state 主动获取观众当前事实。 */
    send(message: PresenterSyncMessage): void {
      try { channel?.postMessage(message) } catch { /* 后备通道仍可使用。 */ }
      try { localStorage.setItem(key, JSON.stringify(message)); localStorage.removeItem(key) } catch { /* 隔离存储禁用。 */ }
    },
    /** 所有监听和频道必须随宿主一起释放。 */
    close(): void { channel?.close(); window.removeEventListener('storage', onStorage) },
  }
}
/** 只探测存储可用性，不读取旧协议内容。 */
function storageSupported(): boolean {
  try { const key = 'web-presentation.presenter.v5.probe'; localStorage.setItem(key, '1'); localStorage.removeItem(key); return true } catch { return false }
}

/** 排序只决定窗口所有权；不比较各窗口的播放时钟。 */
export function createPresenterOwnerEpoch(channelId: string): number {
  const key = `web-presentation.presenter.v5.epoch.${channelId}`
  let previous = 0
  try { previous = Number(localStorage.getItem(key)) || 0 } catch { /* 无存储时用当前时间与随机 ownerId 解同代并发。 */ }
  const epoch = Math.max(Date.now(), previous + 1)
  try { localStorage.setItem(key, String(epoch)) } catch { /* 协议仍按 epoch/id 排序。 */ }
  return epoch
}
