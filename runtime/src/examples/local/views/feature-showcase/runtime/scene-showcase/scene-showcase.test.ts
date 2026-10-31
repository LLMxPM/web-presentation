/** 文件功能：挂载真实公开样例，以真实 GSAP ticker/假墙钟验证完成、清理和静态零执行；不声明像素验收。 */
import { createApp } from 'vue'
import { gsap } from 'gsap'
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { initializeRuntimeExecution, resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { findPageSceneDefinition } from '@/core/scene/page-scene-definition'
import { createPageSceneSlot } from '@/core/scene/page-scene-slot'
import { settleStaticPresentation } from '@/core/static-presentation/registry'
import { flushScenePromises } from '@/core/scene/session-test-helpers'
import type { ExecutionContextKind } from '@/core/execution/execution-policy'
import SceneShowcase from '../SceneShowcase.vue'
import { SCENE_SENTENCE } from './define-scene'

vi.hoisted(() => { vi.useFakeTimers() })
const cleanups: Array<() => void> = []
let painter: { clearRect: ReturnType<typeof vi.fn>; beginPath: ReturnType<typeof vi.fn>; arc: ReturnType<typeof vi.fn>; fill: ReturnType<typeof vi.fn>; fillStyle: string }
let getContext: ReturnType<typeof vi.spyOn>

/** 推进真实 ticker 与 RAF 的同一假墙钟，不手动定位或调用完成回调。 */
async function advance(milliseconds: number): Promise<void> {
  for (let elapsed = 0; elapsed < milliseconds; elapsed += 10) {
    await vi.advanceTimersByTimeAsync(Math.min(10, milliseconds - elapsed))
    gsap.ticker.tick()
  }
  await flushScenePromises()
}

/** 使用生产 Vue 组件和宿主 slot；返回静态根便于卸载后核对清理结果。 */
function mount(execution: ExecutionContextKind = 'presentation') {
  initializeRuntimeExecution(`?runtimeExecution=${execution}`)
  const host = document.createElement('div'); document.body.append(host)
  const app = createApp(SceneShowcase); app.mount(host)
  const slot = createPageSceneSlot(), root = host.querySelector<HTMLElement>('#scene-showcase')!
  let mounted = true
  const unmount = () => { if (mounted) { mounted = false; app.unmount() } }
  cleanups.push(unmount, slot.stop)
  const entry = findPageSceneDefinition(root)!
  return { root, slot, unmount, prepare: () => slot.prepare({ execution, advanceMode: 'scene_end', define: entry.define }) }
}

beforeEach(() => {
  gsap.ticker.sleep(); gsap.ticker.lagSmoothing(0)
  painter = { clearRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(), fillStyle: '' }
  getContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(painter as unknown as CanvasRenderingContext2D)
})

afterEach(() => {
  cleanups.splice(0).reverse().forEach(cleanup => cleanup())
  gsap.ticker.sleep(); gsap.ticker.lagSmoothing(500, 33)
  vi.restoreAllMocks(); resetRuntimeExecutionForTests(); document.body.innerHTML = ''
})
afterAll(() => { vi.useRealTimers() })

describe('Scene 正式公开入口样例', () => {
  it('多条序列并行、文字等待数字实际完成；Canvas 实际完成后无限装饰仍不阻塞聚合', async () => {
    const timeline = vi.spyOn(gsap, 'timeline'), page = mount()
    expect(timeline).not.toHaveBeenCalled()
    const session = (await page.prepare())!
    expect(session.getSnapshot().phase).toBe('ready')
    expect(getContext).not.toHaveBeenCalled()
    expect(page.root.querySelector('[data-counter]')!.textContent).toBe('100')
    await session.start()
    await advance(500)
    const number = Number(page.root.querySelector('[data-counter]')!.textContent)
    expect(number).toBeGreaterThan(0); expect(number).toBeLessThan(100)
    expect(page.root.querySelector('[data-typewriter]')!.textContent).toBe(SCENE_SENTENCE)
    expect(Number(page.root.querySelector<SVGElement>('[data-stroke]')!.style.strokeDashoffset)).toBeGreaterThan(0)
    await advance(800)
    expect(page.root.querySelector('[data-counter]')!.textContent).toBe('100')
    expect(page.root.querySelector('[data-typewriter]')!.textContent).not.toBe(SCENE_SENTENCE)
    expect(getContext).toHaveBeenCalledOnce()
    await advance(1800)
    expect(session.getSnapshot()).toMatchObject({ phase: 'completed', issue: null })
    expect(page.root.querySelector('[data-typewriter]')!.textContent).toBe(SCENE_SENTENCE)
    expect(painter.arc).toHaveBeenCalled()
    const ambient = [...page.root.querySelectorAll<HTMLElement>('.scene-spark')].map(element => element.style.transform)
    await advance(150)
    expect([...page.root.querySelectorAll<HTMLElement>('.scene-spark')].map(element => element.style.transform)).not.toEqual(ambient)
    session.stop()
    expect(page.root.querySelector<SVGElement>('[data-stroke]')!.style.strokeDashoffset).toBe('0')
    expect(page.root.querySelector<SVGElement>('[data-particle-poster]')!.style.visibility).toBe('')
    expect(page.root.querySelector<HTMLElement>('.scene-spark')!.style.transform).toBe('')
    gsap.ticker.sleep()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('冻结期间 Canvas 和文字不推进，恢复不补跑；卸载立即释放所有自建 RAF', async () => {
    const page = mount(), session = (await page.prepare())!
    await session.start(); await advance(1400)
    const count = painter.arc.mock.calls.length, text = page.root.querySelector('[data-typewriter]')!.textContent
    session.setSuspended(true); await advance(5000)
    expect(painter.arc).toHaveBeenCalledTimes(count)
    expect(page.root.querySelector('[data-typewriter]')!.textContent).toBe(text)
    session.setSuspended(false); await advance(100)
    expect(session.getSnapshot().phase).toBe('running')
    expect(painter.arc.mock.calls.length).toBeGreaterThan(count)
    page.unmount()
    expect(session.getSnapshot().phase).toBe('stopped')
    expect(page.root.querySelector('[data-typewriter]')!.textContent).toBe(SCENE_SENTENCE)
    const stopped = painter.arc.mock.calls.length
    await advance(3000)
    expect(painter.arc).toHaveBeenCalledTimes(stopped)
    gsap.ticker.sleep(); expect(vi.getTimerCount()).toBe(0)
  })

  it.each(['capture', 'export', 'thumbnail'] as const)('%s 默认完整可读且零 Scene/Canvas/RAF 执行', async execution => {
    const timeline = vi.spyOn(gsap, 'timeline'), raf = vi.spyOn(window, 'requestAnimationFrame')
    const page = mount(execution)
    expect((await settleStaticPresentation(page.root)).status).toBe('ready')
    expect(await page.prepare()).toBeNull()
    expect(timeline).not.toHaveBeenCalled(); expect(getContext).not.toHaveBeenCalled(); expect(raf).not.toHaveBeenCalled()
    expect(page.root.querySelector('[data-counter]')!.textContent).toBe('100')
    expect(page.root.querySelector('[data-typewriter]')!.textContent).toBe(SCENE_SENTENCE)
    expect(page.root.querySelectorAll('[data-particle-poster] circle')).toHaveLength(18)
  })
})
