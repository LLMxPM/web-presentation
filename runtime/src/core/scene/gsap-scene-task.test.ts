/** 文件功能：用真实 GSAP ticker 验证受管正向序列、SVG/数字/回调、冻结和释放，不采样或启动浏览器。 */
import { gsap } from 'gsap'
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createGsapSceneTask } from './gsap-scene-task'
import { deferred, flushScenePromises, scene, task } from './session-test-helpers'
import type { PageSceneSession } from './types'
import type { SceneVisualOptions, SceneVisualTimeline } from './visual-types'

// GSAP 在模块加载时捕获 Date.now；需在导入前安装同一只假时钟，避免真实 ticker 被错误地“推进”。
vi.hoisted(() => { vi.useFakeTimers() })

let root: HTMLElement
const sessions: PageSceneSession[] = []

/** 使用真实执行器与默认有限视觉任务，所有测试会话退出时统一释放。 */
function visual(options: Partial<SceneVisualOptions> = {}) {
  return createGsapSceneTask({ id: 'visual', role: 'blocking', root,
    define: timeline => { timeline.to('.title', { opacity: 1, duration: 0.1, ease: 'none' }) }, ...options })
}

/** 按小步推进假墙钟与真实 ticker，保留 GSAP 自己的正向时钟和完成事件。 */
async function advance(milliseconds: number): Promise<void> {
  for (let elapsed = 0; elapsed < milliseconds; elapsed += 10) {
    await vi.advanceTimersByTimeAsync(Math.min(10, milliseconds - elapsed))
    gsap.ticker.tick()
  }
  await flushScenePromises()
}

/** 登记正式 Scene 会话，避免未结束的 ambient 留到下一个测试。 */
function startScene(tasks = [visual()]) {
  const session = scene(tasks)
  sessions.push(session)
  return session
}

beforeEach(() => {
  gsap.ticker.sleep()
  gsap.ticker.lagSmoothing(0)
  root = document.createElement('section')
  root.innerHTML = '<h1 class="title" style="opacity:0.2;color:red">标题</h1><svg><path class="stroke" style="stroke-dashoffset:100" /></svg>'
  document.body.append(root)
  gsap.ticker.wake()
})

afterEach(() => {
  sessions.splice(0).forEach(session => session.stop())
  gsap.ticker.sleep()
  gsap.ticker.lagSmoothing(500, 33)
  document.body.innerHTML = ''
})

afterAll(() => { vi.useRealTimers() })

describe('GSAP Scene 正向任务', () => {
  it('prepare 不执行回调也不启动时间轴，实际 onComplete 解锁聚合，stop 恢复原样式', async () => {
    const callback = vi.fn(), complete = vi.fn()
    const session = startScene([visual({ define: timeline => {
      timeline.fromTo('.title', { opacity: 0 }, { opacity: 1, duration: 0.1, ease: 'none', onComplete: complete })
        .call(callback, [], 0.02)
    } })])
    await session.prepare()
    await advance(200)
    expect(callback).not.toHaveBeenCalled()
    expect(complete).not.toHaveBeenCalled()
    expect(root.querySelector<HTMLElement>('.title')!.style.opacity).toBe('0.2')
    await session.start()
    await advance(40)
    expect(callback).toHaveBeenCalledOnce()
    expect(session.getSnapshot().phase).toBe('running')
    await advance(100)
    expect((await session.finished).phase).toBe('completed')
    expect(complete).toHaveBeenCalledOnce()
    expect(root.querySelector<HTMLElement>('.title')!.style.opacity).toBe('1')
    session.stop()
    expect(root.querySelector<HTMLElement>('.title')!.style.opacity).toBe('0.2')
  })

  it('支持 SVG 描边、额外 CSS 属性、数值对象和 onUpdate，多个序列独立并行', async () => {
    const counter = { value: 0 }, updates = vi.fn()
    const session = startScene([
      visual({ id: 'svg', define: timeline => { timeline.to('.stroke', { strokeDashoffset: 0, duration: 0.1, ease: 'none' }) } }),
      visual({ id: 'counter', define: timeline => {
        timeline.to(counter, { value: 100, duration: 0.2, ease: 'none', onUpdate() {
          updates(); root.querySelector('.title')!.textContent = String(Math.round(counter.value))
        } }).to('.title', { letterSpacing: '4px', color: 'blue', duration: 0.05 })
      } }),
    ])
    await session.prepare()
    expect(counter.value).toBe(0)
    expect(updates).not.toHaveBeenCalled()
    await session.start()
    await advance(130)
    expect(Number((root.querySelector('.stroke') as SVGElement).style.strokeDashoffset)).toBe(0)
    expect(session.getSnapshot().phase).toBe('running')
    expect(counter.value).toBeGreaterThan(20)
    await advance(200)
    expect((await session.finished).phase).toBe('completed')
    expect(counter.value).toBe(100)
    expect(root.querySelector<HTMLElement>('.title')!.style.letterSpacing).toBe('4px')
    expect(updates.mock.calls.length).toBeGreaterThan(1)
    session.stop()
    expect(counter.value).toBe(0)
    expect((root.querySelector('.stroke') as SVGElement).style.strokeDashoffset).toBe('100')
  })

  it('有限重复和无限 ambient 都可正向播放，循环经过的 call 每会话只执行一次', async () => {
    const callback = vi.fn(), loopCallback = vi.fn()
    const session = startScene([
      visual({ repeat: 1, define: timeline => {
        timeline.to('.title', { opacity: 1, duration: 0.05 }).call(callback, [], 0.02)
      } }),
      visual({ id: 'pulse', role: 'ambient', repeat: -1, yoyo: true, define: timeline => {
        timeline.to('.stroke', { strokeDashoffset: 0, duration: 0.05 }).call(loopCallback, [], 0.02)
      } }),
    ])
    await session.start()
    await advance(300)
    expect((await session.finished).phase).toBe('completed')
    expect(callback).toHaveBeenCalledOnce()
    expect(loopCallback).toHaveBeenCalledOnce()
    session.stop()
    await advance(100)
    expect(loopCallback).toHaveBeenCalledOnce()
  })

  it('内部冻结暂停真实 GSAP，恢复后继续正向，退出不补发未来回调', async () => {
    const callback = vi.fn(), future = vi.fn()
    const session = startScene([visual({ define: timeline => {
      timeline.to('.title', { opacity: 1, duration: 0.4, ease: 'none' }).call(callback, [], 0.1).call(future, [], 0.35)
    } })])
    await session.start()
    await advance(50)
    session.setSuspended(true)
    const before = root.querySelector<HTMLElement>('.title')!.style.opacity
    await advance(250)
    expect(root.querySelector<HTMLElement>('.title')!.style.opacity).toBe(before)
    expect(callback).not.toHaveBeenCalled()
    session.setSuspended(false)
    await advance(100)
    expect(callback).toHaveBeenCalledOnce()
    session.stop()
    await advance(500)
    expect(future).not.toHaveBeenCalled()
  })

  it('onStart 异常安全转为失败，render 栈结束后样式仍恢复', async () => {
    const future = vi.fn()
    const session = startScene([visual({ define: timeline => {
      timeline.to('.title', { opacity: 1, duration: 0.1, onStart() { throw new Error('private://source') } })
        .call(future, [], 0.05)
    } })])
    await session.start()
    await advance(50)
    expect((await session.finished).issue).toMatchObject({ code: 'SCENE_TASK_FAILED', taskId: 'visual' })
    expect(root.querySelector<HTMLElement>('.title')!.style.opacity).toBe('0.2')
    expect(future).not.toHaveBeenCalled()
  })

  it('异步 call 明确拒绝并消费其拒绝，异步工作须通过独立任务表达', async () => {
    const session = startScene([visual({ define: timeline => {
      timeline.to('.title', { opacity: 1, duration: 0.1 }).call(() => Promise.reject(new Error('async')), [], 0.02)
    } })])
    await session.start()
    await advance(50)
    expect((await session.finished).issue?.code).toBe('SCENE_VISUAL_ASYNC_CALLBACK')
  })

  it('视觉任务可以等待任意资源的实际完成后再开始', async () => {
    const resource = deferred(), callback = vi.fn()
    const session = startScene([task('resource', { run: () => resource.promise }), visual({ afterTrack: 'resource', offsetMs: 30,
      define: timeline => { timeline.to('.title', { opacity: 1, duration: 0.05 }).call(callback, [], 0.01) } })])
    await session.start()
    await advance(200)
    expect(callback).not.toHaveBeenCalled()
    resource.resolve(); await flushScenePromises()
    await advance(20)
    expect(callback).not.toHaveBeenCalled()
    await advance(120)
    expect(callback).toHaveBeenCalledOnce()
    expect((await session.finished).phase).toBe('completed')
  })

  it.each([
    { scrollTrigger: {} }, { drawSVG: '100%' }, { css: { motionPath: {} } }, { modifiers: {} },
  ])('可选插件参数在 prepare 明确拒绝 %#', async vars => {
    const session = startScene([visual({ define: timeline => { timeline.to('.title', { duration: 0.1, ...vars }) } })])
    expect((await session.prepare()).issue).toMatchObject({ code: 'SCENE_PLUGIN_UNSUPPORTED', taskId: 'visual' })
  })

  it('拒绝跨画布 DOM 和无限 blocking，并保留所有原始样式', async () => {
    const outside = document.createElement('div'); document.body.append(outside)
    const session = startScene([visual({ define: timeline => { timeline.to(outside, { opacity: 0, duration: 0.1 }) } })])
    expect((await session.prepare()).issue?.code).toBe('SCENE_TARGET_INVALID')
    const infinite = startScene([visual({ repeat: -1 })])
    expect((await infinite.prepare()).issue?.code).toBe('SCENE_TASK_INVALID')
    expect(root.querySelector<HTMLElement>('.title')!.style.opacity).toBe('0.2')
  })

  it('公开序列句柄仅提供填充操作，有限任务不接受无限子动画或空序列', async () => {
    let captured: SceneVisualTimeline
    const session = startScene([visual({ define: timeline => { captured = timeline; timeline.to('.title', { opacity: 1, duration: 0.1 }) } })])
    await session.prepare()
    expect(Object.keys(captured!)).not.toContain('seek')
    expect(Object.keys(captured!)).not.toContain('restart')
    expect(() => captured!.to('.title', { opacity: 0, duration: 1 })).toThrow('只能在 prepare')
    session.stop()
    expect(() => captured!.call(() => {})).toThrow('只能在 prepare')
    const invalid = startScene([visual({ define: timeline => { timeline.to('.title', { duration: 0.1, repeat: -1 }) } })])
    expect((await invalid.prepare()).issue?.code).toBe('SCENE_VISUAL_INVALID')
    const empty = startScene([visual({ define: () => {} })])
    expect((await empty.prepare()).issue?.code).toBe('SCENE_VISUAL_INVALID')
  })
})
