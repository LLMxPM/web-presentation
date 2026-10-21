/**
 * 文件功能：实现 DOM 动效适配器与同目标多轨道视觉状态协调。
 *
 * GSAP 只负责有限段落的缓动插值；实际样式写入独立的 translate/scale/rotate
 * CSS 属性，保留页面自身的 transform 布局。相同元素上的不同属性轨道通过
 * 协调器合并，释放后恢复原始内联样式。
 */
import { gsap } from 'gsap'

import type { MotionAdapterContext, MotionAdapterFactory, MotionTrackAdapter } from './adapters'
import { MOTION_ERROR_TARGET_INVALID, MotionError } from './errors'
import { digestMotionStateProof } from './sampling'
import type { CompiledDomTrack, DomMotionProperty, DomMotionState, MotionStateProof, MotionVisualMode } from './types'

const WRAPPER_STYLE_PROPERTIES = ['translate', 'scale', 'rotate'] as const
const WRAPPER_PROPERTIES: DomMotionProperty[] = ['x', 'y', 'scale', 'rotation']

interface ElementOwnership {
  token: symbol
  properties: Set<DomMotionProperty>
  values: DomMotionState
}

export interface ElementState {
  element: HTMLElement
  owners: Map<DomMotionProperty, ElementOwnership>
  original: {
    opacity: string
    translate: string
    scale: string
    rotate: string
    willChange: string
  }
  /** 释放部分属性时用于组合的原始值；不覆盖仍被其它轨道拥有的属性。 */
  base: {
    x: number
    y: number
    scale: number
    rotation: number
  }
  anyOwned: boolean
}

/**
 * 同元素多轨道协调器；每个 transport 使用独立实例，避免预览与捕获互相写样式。
 */
export class DomMotionCoordinator {
  private readonly states = new WeakMap<HTMLElement, ElementState>()
  private disposed = false

  /** 为轨道登记属性所有权，返回用于写入与释放的句柄。 */
  acquire(element: HTMLElement, properties: DomMotionProperty[]): ElementOwnership {
    if (this.disposed) {
      throw new MotionError(MOTION_ERROR_TARGET_INVALID, 'DOM 动效协调器已释放。')
    }
    let state = this.states.get(element)
    if (!state) {
      const original = {
        opacity: element.style.getPropertyValue('opacity'),
        translate: element.style.getPropertyValue('translate'),
        scale: element.style.getPropertyValue('scale'),
        rotate: element.style.getPropertyValue('rotate'),
        willChange: element.style.getPropertyValue('will-change'),
      }
      const translate = parseTranslate(original.translate)
      state = {
        element,
        owners: new Map(),
        original,
        base: {
          x: translate.x,
          y: translate.y,
          scale: parseFinite(original.scale, 1),
          rotation: parseFinite(original.rotate, 0),
        },
        anyOwned: false,
      }
      this.states.set(element, state)
    }
    const ownership: ElementOwnership = {
      token: Symbol('dom-motion-owner'),
      properties: new Set(properties),
      values: {},
    }
    for (const property of properties) {
      const existing = state.owners.get(property)
      if (existing) {
        throw new MotionError(
          MOTION_ERROR_TARGET_INVALID,
          `DOM 目标的 ${property} 属性已被其它轨道占用。`,
        )
      }
      state.owners.set(property, ownership)
    }
    if (!state.anyOwned) {
      element.style.setProperty('will-change', 'opacity, translate, scale, rotate')
      state.anyOwned = true
    }
    return ownership
  }

  /** 写入本轨道拥有的属性，并重新组合元素样式。 */
  write(state: ElementState | null, ownership: ElementOwnership, values: DomMotionState): void {
    if (!state || this.disposed) return
    ownership.values = { ...values }
    this.applyState(state)
  }

  /** 读取元素状态；未登记时返回 null。 */
  getState(element: HTMLElement): ElementState | null {
    return this.states.get(element) ?? null
  }

  /** 释放轨道属性；元素无人拥有时恢复原始内联样式。 */
  release(element: HTMLElement, ownership: ElementOwnership): void {
    const state = this.states.get(element)
    if (!state) return
    for (const property of ownership.properties) {
      if (state.owners.get(property) === ownership) state.owners.delete(property)
    }
    if (state.owners.size === 0) {
      this.restore(state)
      this.states.delete(element)
      return
    }
    this.applyState(state)
  }

  dispose(): void {
    this.disposed = true
  }

  private applyState(state: ElementState): void {
    const opacityOwner = state.owners.get('opacity')
    if (opacityOwner?.values.opacity !== undefined) {
      state.element.style.setProperty('opacity', String(opacityOwner.values.opacity))
    } else {
      restoreProperty(state.element, 'opacity', state.original.opacity)
    }
    const hasTranslate = state.owners.has('x') || state.owners.has('y')
    if (hasTranslate) {
      const x = state.owners.has('x') ? ownerValue(state, 'x', state.base.x) : state.base.x
      const y = state.owners.has('y') ? ownerValue(state, 'y', state.base.y) : state.base.y
      state.element.style.setProperty('translate', `${x}px ${y}px`)
    } else {
      restoreProperty(state.element, 'translate', state.original.translate)
    }
    if (state.owners.has('scale')) {
      state.element.style.setProperty('scale', String(ownerValue(state, 'scale', state.base.scale)))
    } else {
      restoreProperty(state.element, 'scale', state.original.scale)
    }
    if (state.owners.has('rotation')) {
      state.element.style.setProperty('rotate', `${ownerValue(state, 'rotation', state.base.rotation)}deg`)
    } else {
      restoreProperty(state.element, 'rotate', state.original.rotate)
    }
  }

  private restore(state: ElementState): void {
    const style = state.element.style
    style.setProperty('opacity', state.original.opacity)
    style.setProperty('translate', state.original.translate)
    style.setProperty('scale', state.original.scale)
    style.setProperty('rotate', state.original.rotate)
    style.setProperty('will-change', state.original.willChange)
    // 空值会残留在 cssText 中，移除后恢复样式表来源。
    for (const property of ['opacity', 'translate', 'scale', 'rotate', 'will-change']) {
      if (!style.getPropertyValue(property)) style.removeProperty(property)
    }
  }
}

function ownerValue(state: ElementState, property: DomMotionProperty, fallback: number): number {
  return state.owners.get(property)?.values[property] ?? fallback
}

/** 恢复内联属性；原值为空时移除属性，避免空字符串残留。 */
function restoreProperty(element: HTMLElement, property: string, value: string): void {
  if (value) element.style.setProperty(property, value)
  else element.style.removeProperty(property)
}

/** 解析原始 translate 的像素分量；百分比等无法与轨道像素相加的值按 0 处理。 */
function parseTranslate(value: string): { x: number; y: number } {
  const parts = String(value || '').trim().split(/\s+/)
  const parse = (part: string | undefined): number => {
    const match = /^(-?\d+(?:\.\d+)?)px$/.exec(part ?? '')
    return match ? Number(match[1]) : 0
  }
  return { x: parse(parts[0]), y: parse(parts[1] ?? parts[0]) }
}

function parseFinite(value: string, fallback: number): number {
  const numeric = Number.parseFloat(String(value || '').replace(/deg$/, ''))
  return Number.isFinite(numeric) ? numeric : fallback
}

/** 每个 transport 创建一套 DOM 适配器工厂，共享同元素属性协调。 */
export function createDomMotionAdapterFactory(): MotionAdapterFactory {
  const coordinator = new DomMotionCoordinator()
  return (context: MotionAdapterContext) => createDomMotionAdapter(context, coordinator)
}

/** 创建单轨道 DOM 适配器。 */
export function createDomMotionAdapter(
  context: MotionAdapterContext,
  coordinator: DomMotionCoordinator = new DomMotionCoordinator(),
): MotionTrackAdapter {
  const track = context.track as CompiledDomTrack
  if (track.type !== 'dom') {
    throw new MotionError(MOTION_ERROR_TARGET_INVALID, 'DOM 适配器只接受 DOM 轨道。', { trackId: track.id })
  }
  let element: HTMLElement | null = null
  let ownership: ElementOwnership | null = null
  let state: ElementState | null = null
  let timeline: gsap.core.Timeline | null = null
  let progressProxy: { value: number } | null = null
  let disposed = false
  let visualMode: MotionVisualMode = context.visualMode

  function resolveElement(): HTMLElement {
    if (element?.isConnected) return element
    const found = context.root.querySelector<HTMLElement>(track.target)
    if (!found) {
      throw new MotionError(
        MOTION_ERROR_TARGET_INVALID,
        `DOM 目标 ${track.target} 不存在于当前页面。`,
        { fieldPath: `timeline.tracks.${track.id}.target`, trackId: track.id },
      )
    }
    return found
  }

  function buildTimeline(): gsap.core.Timeline {
    progressProxy = { value: 0 }
    const instance = gsap.timeline({ paused: true })
    // 统一使用可复现的缓动；proxy 只承载 0→1 进度，不使用 CSSPlugin 改写 transform。
    instance.to(progressProxy, {
      value: 1,
      duration: Math.max(track.durationMs, 1) / 1000,
      ease: 'power2.out',
      immediateRender: true,
    })
    instance.pause(0)
    return instance
  }

  function localProgress(positionMs: number, mode: MotionVisualMode): number {
    if (mode === 'reduced') return 1
    const local = positionMs - track.startMs
    if (local <= 0) return 0
    if (local >= track.durationMs) return 1
    return local / track.durationMs
  }

  function valuesAt(progress: number): DomMotionState {
    const eased = progressProxy?.value ?? progress
    const values: DomMotionState = {}
    for (const property of track.properties) {
      const from = track.from[property] ?? defaultPropertyValue(property)
      const to = track.to[property] ?? defaultPropertyValue(property)
      values[property] = from + (to - from) * eased
    }
    return values
  }

  function apply(positionMs: number, mode: MotionVisualMode): void {
    if (disposed || !element || !ownership || !state) return
    visualMode = mode
    const progress = localProgress(positionMs, mode)
    if (timeline && progressProxy) {
      timeline.progress(progress)
    }
    coordinator.write(state, ownership, valuesAt(progress))
  }

  return {
    type: 'dom',
    async prepare() {
      element = resolveElement()
      ownership = coordinator.acquire(element, track.properties)
      state = coordinator.getState(element)
      timeline = buildTimeline()
      apply(track.startMs, context.visualMode)
    },
    async applyAt(options) {
      apply(options.positionMs, options.visualMode)
    },
    async freeze(positionMs): Promise<MotionStateProof> {
      apply(positionMs, visualMode)
      const values = valuesAt(localProgress(positionMs, visualMode))
      return {
        trackId: track.id,
        type: 'dom',
        positionMs,
        digest: digestMotionStateProof(track.id, 'dom', positionMs, {
          target: track.target,
          values,
          visualMode,
        }),
        details: { target: track.target, values, visualMode },
      }
    },
    dispose() {
      if (disposed) return
      disposed = true
      timeline?.kill()
      timeline = null
      progressProxy = null
      if (element && ownership) coordinator.release(element, ownership)
      ownership = null
      state = null
      element = null
    },
  }
}

function defaultPropertyValue(property: DomMotionProperty): number {
  if (property === 'opacity' || property === 'scale') return 1
  return 0
}

export type { CompiledDomTrack }
