/**
 * 文件功能：覆盖 WP04 DOM 适配器的确定性采样、reduced 映射、属性协调与样式恢复。
 */
import { beforeEach, describe, expect, it } from 'vitest'

import type { MotionAdapterContext } from './adapters'
import { compilePageTimeline } from './compile'
import { createDomMotionAdapterFactory, DomMotionCoordinator } from './dom-adapter'
import { MotionError } from './errors'
import { MotionTargetRegistry } from './target-registry'
import type { DomMotionTrackDefinition, MotionVisualMode, PageTimelineDefinition } from './types'

function makeRoot(markup: string): HTMLElement {
  document.body.innerHTML = `<div id="stage">${markup}</div>`
  return document.getElementById('stage') as HTMLElement
}

function makeContext(
  root: HTMLElement,
  tracks: DomMotionTrackDefinition[],
  visualMode: MotionVisualMode = 'full',
): MotionAdapterContext[] {
  const definition: PageTimelineDefinition = { schemaVersion: 1, timelineId: 'dom-test', tracks }
  const plan = compilePageTimeline(definition)
  return plan.tracks.map(track => ({
    plan,
    track,
    root,
    signal: new AbortController().signal,
    visualMode,
    allowMediaPlayback: false,
    muted: false,
    generation: 1,
    ownership: new MotionTargetRegistry(),
  }))
}

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('createDomMotionAdapter', () => {
  it('按逻辑位置应用并支持任意顺序采样', async () => {
    const root = makeRoot('<div class="title"></div>')
    const [context] = makeContext(root, [
      { type: 'dom', id: 'title', target: '.title', preset: 'fade-up', durationMs: 1000 },
    ])
    const factory = createDomMotionAdapterFactory()
    const adapter = factory(context)
    await adapter.prepare()
    const element = root.querySelector<HTMLElement>('.title')!

    await adapter.applyAt({ positionMs: 0, visualMode: 'full' })
    expect(Number(element.style.getPropertyValue('opacity'))).toBe(0)
    expect(element.style.getPropertyValue('translate')).toBe('0px 24px')

    await adapter.applyAt({ positionMs: 500, visualMode: 'full' })
    const middle = {
      opacity: Number(element.style.getPropertyValue('opacity')),
      translate: element.style.getPropertyValue('translate'),
    }
    expect(middle.opacity).toBeGreaterThan(0.5)
    expect(middle.opacity).toBeLessThan(1)

    await adapter.applyAt({ positionMs: 1000, visualMode: 'full' })
    expect(Number(element.style.getPropertyValue('opacity'))).toBe(1)
    expect(element.style.getPropertyValue('translate')).toBe('0px 0px')

    // 直接从中段采样，与先到结尾再回中段的状态一致。
    await adapter.applyAt({ positionMs: 500, visualMode: 'full' })
    expect(element.style.getPropertyValue('translate')).toBe(middle.translate)
    expect(Number(element.style.getPropertyValue('opacity'))).toBeCloseTo(middle.opacity, 6)
    adapter.dispose()
  })

  it('reduced 直接应用可读终态', async () => {
    const root = makeRoot('<div class="title"></div>')
    const [context] = makeContext(root, [
      { type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 1000 },
    ], 'reduced')
    const adapter = createDomMotionAdapterFactory()(context)
    await adapter.prepare()
    const element = root.querySelector<HTMLElement>('.title')!
    expect(Number(element.style.getPropertyValue('opacity'))).toBe(1)

    await adapter.applyAt({ positionMs: 100, visualMode: 'full' })
    const fading = Number(element.style.getPropertyValue('opacity'))
    expect(fading).toBeGreaterThan(0)
    expect(fading).toBeLessThan(1)
    await adapter.applyAt({ positionMs: 100, visualMode: 'reduced' })
    expect(Number(element.style.getPropertyValue('opacity'))).toBe(1)
    adapter.dispose()
  })

  it('同元素不同属性轨道合并，释放后恢复原始内联样式', async () => {
    const root = makeRoot('<div class="title" style="opacity: 0.9; translate: 1px 2px"></div>')
    const [xContext, yContext] = makeContext(root, [
      { type: 'dom', id: 'move-x', target: '.title', from: { x: 10 }, to: { x: 40 }, durationMs: 1000 },
      { type: 'dom', id: 'move-y', target: '.title', from: { y: 0 }, to: { y: 30 }, durationMs: 1000 },
    ])
    const factory = createDomMotionAdapterFactory()
    const xAdapter = factory(xContext)
    const yAdapter = factory(yContext)
    await xAdapter.prepare()
    await yAdapter.prepare()
    const element = root.querySelector<HTMLElement>('.title')!

    await xAdapter.applyAt({ positionMs: 1000, visualMode: 'full' })
    await yAdapter.applyAt({ positionMs: 1000, visualMode: 'full' })
    expect(element.style.getPropertyValue('translate')).toBe('40px 30px')

    xAdapter.dispose()
    expect(element.style.getPropertyValue('translate')).toBe('1px 30px')
    yAdapter.dispose()
    expect(element.style.getPropertyValue('translate')).toBe('1px 2px')
    expect(element.style.getPropertyValue('opacity')).toBe('0.9')
  })

  it('目标缺失时返回带定位的错误', async () => {
    const root = makeRoot('')
    const [context] = makeContext(root, [
      { type: 'dom', id: 'missing', target: '.missing', preset: 'fade', durationMs: 1000 },
    ])
    const adapter = createDomMotionAdapterFactory()(context)
    await expect(adapter.prepare()).rejects.toBeInstanceOf(MotionError)
    adapter.dispose()
  })

  it('协调器释放后无法继续认领属性', () => {
    const coordinator = new DomMotionCoordinator()
    const element = document.createElement('div')
    const ownership = coordinator.acquire(element, ['opacity'])
    expect(() => coordinator.acquire(element, ['opacity'])).toThrow(MotionError)
    coordinator.release(element, ownership)
    coordinator.dispose()
    expect(() => coordinator.acquire(element, ['opacity'])).toThrow(MotionError)
  })
})
