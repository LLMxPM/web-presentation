/** 文件功能：验证连接线挂载后的延迟测量正常执行，卸载后释放任务且不再访问 DOM。 */
import { createApp, nextTick, type App } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Connector from './Connector.v1.vue'

let app: App<Element> | null = null

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  unmountConnector()
  document.body.innerHTML = ''
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

/** 创建可测量的两个锚点，使用真实 Vue 生命周期挂载连接线。 */
async function mountConnector(): Promise<SVGSVGElement> {
  document.body.innerHTML = '<div id="stage"><div id="from"></div><div id="to"></div><div id="host"></div></div>'
  for (const [index, id] of ['from', 'to'].entries()) {
    const element = document.getElementById(id)!
    Object.defineProperties(element, {
      offsetWidth: { value: 80 },
      offsetHeight: { value: 40 },
      offsetLeft: { value: index * 300 },
    })
  }
  app = createApp(Connector, { from: '#from', to: '#to' })
  app.mount(document.getElementById('host')!)
  await nextTick()
  return document.querySelector('svg')!
}

/** 显式销毁实例并清空引用，避免重复卸载干扰任务清理断言。 */
function unmountConnector(): void {
  app?.unmount()
  app = null
}

describe('Connector 异步测量生命周期', () => {
  it('挂载后仍应延迟测量锚点并绘制连线', async () => {
    const svg = await mountConnector()
    expect(svg.querySelector('path')).toBeNull()

    await vi.advanceTimersByTimeAsync(50)
    await nextTick()
    expect(svg.querySelector('path')?.getAttribute('d')).toBe('M 40 20 L 340 20')
  })

  it('首次测量前卸载应取消延迟任务，且后续不再查询 DOM', async () => {
    await mountConnector()
    unmountConnector()
    const querySelector = vi.spyOn(document, 'querySelector')

    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(250)
    expect(querySelector).not.toHaveBeenCalled()
  })

  it('卸载应取消 DOM 变化安排的绘制帧，并忽略迟到的回调', async () => {
    let pendingFrame: FrameRequestCallback | undefined
    const requestFrame = vi.fn((callback: FrameRequestCallback) => {
      pendingFrame = callback
      return 42
    })
    const cancelFrame = vi.fn()
    vi.stubGlobal('requestAnimationFrame', requestFrame)
    vi.stubGlobal('cancelAnimationFrame', cancelFrame)
    await mountConnector()

    document.getElementById('from')!.style.left = '10px'
    await nextTick()
    expect(requestFrame).toHaveBeenCalledTimes(1)
    unmountConnector()
    expect(cancelFrame).toHaveBeenCalledWith(42)

    const querySelector = vi.spyOn(document, 'querySelector')
    pendingFrame!(performance.now())
    expect(querySelector).not.toHaveBeenCalled()
  })
})
