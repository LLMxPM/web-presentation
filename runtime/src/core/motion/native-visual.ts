/** 文件功能：托管原生 GSAP 视觉填充、作用域、初态、静默采样、身份与释放。 */
import { gsap } from 'gsap'
import type { MotionTrackAdapter } from './adapters'
import { digestMotionPayload } from './compile'
import { MotionError, MOTION_ERROR_SCHEMA_INVALID, MOTION_ERROR_PROPERTY_CONFLICT } from './errors'
import { digestMotionStateProof } from './sampling'
import { MAX_MOTION_DURATION_MS, type CompiledMotionPlan, type MotionVisualMode } from './types'

/** 使用原生 GSAP fromTo/标签/位置/错峰；函数复用直接向同一暂停时间轴追加段落。 */
export type NativeVisualTimeline = Pick<gsap.core.Timeline, 'fromTo' | 'addLabel'>
export type NativeVisualBuilder = (timeline: NativeVisualTimeline) => void
type Values = Record<string, number>
interface Segment { target: HTMLElement; key: string; startMs: number; endMs: number; from: Values; to: Values; ease: string }
const PROPERTIES = new Set(['opacity', 'x', 'y', 'scale', 'rotation'])
const OPTIONS = new Set(['duration', 'ease', 'stagger', 'immediateRender'])

/** 资源/transport 用毫秒，原生 GSAP 参数保持秒，转换只在此处统一定义。 */
export function seconds(milliseconds: number): number { return milliseconds / 1000 }

/** 抛出有界创作错误；禁止回调、额外时钟与未声明初态。 */
function invalid(message: string): never { throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, message, { fieldPath: 'visual' }) }

/** 元素身份只使用 root 内的结构路径，不能依赖实例编号或临时绑定属性。 */
function targetKey(root: HTMLElement, element: HTMLElement): string {
  const parts: number[] = []
  let current: Element | null = element
  while (current && current !== root) {
    const parent: Element | null = current.parentElement
    if (!parent) invalid('视觉目标必须属于当前页面。')
    parts.unshift(Array.from(parent.children).indexOf(current))
    current = parent
  }
  if (current !== root) invalid('视觉目标必须属于当前页面。')
  return parts.join('/') || 'root'
}

/** 校验有限数值属性，不将 JS 回调或插件参数放进规范身份。 */
function readValues(vars: gsap.TweenVars, end: boolean): Values {
  if (!vars || typeof vars !== 'object') invalid('视觉段落必须使用 GSAP 3 的显式 fromTo 签名。')
  const values: Values = {}
  for (const [key, value] of Object.entries(vars)) {
    if (end && OPTIONS.has(key)) continue
    if (!PROPERTIES.has(key) || typeof value !== 'number' || !Number.isFinite(value)) invalid(`不支持的视觉属性 ${key}。`)
    values[key] = value
  }
  return values
}

/** 创建暂停时间轴；填充函数只运行一次，播放/定位全部由 transport 驱动。 */
export function createNativeVisual(root: HTMLElement, resourceLabels: Record<string, number>, build: NativeVisualBuilder): {
  plan: NonNullable<CompiledMotionPlan['visual']>; adapter: MotionTrackAdapter
} {
  const context = gsap.context(() => {}, root)
  let timeline!: gsap.core.Timeline
  const segments: Segment[] = []
  let disposed = false
  let mode: MotionVisualMode = 'full'
  try {
    context.add(() => {
      timeline = gsap.timeline({ paused: true, defaults: { ease: 'none' } })
      for (const [label, ms] of Object.entries(resourceLabels)) timeline.addLabel(label, seconds(ms))
      const facade = new Proxy(timeline, {
        get(_target, key) {
          if (key === 'addLabel') return (label: string, position?: gsap.Position) => {
            if (Object.prototype.hasOwnProperty.call(resourceLabels, label)) invalid(`不能覆盖资源标签 ${label}。`)
            timeline.addLabel(label, position)
            return facade
          }
          if (key !== 'fromTo') return () => invalid(`视觉填充不允许调用 ${String(key)}；请使用显式 fromTo 和段落函数。`)
          return (targets: gsap.TweenTarget, fromVars: gsap.TweenVars, toVars: gsap.TweenVars, position?: gsap.Position) => {
            const from = readValues(fromVars, false)
            const to = readValues(toVars, true)
            if (!Object.keys(to).length || Object.keys(to).some(property => from[property] === undefined)
              || Object.keys(from).some(property => to[property] === undefined)) invalid('from/to 必须显式声明相同属性。')
            const duration = toVars.duration
            const stagger = toVars.stagger ?? 0
            const ease = toVars.ease ?? 'none'
            if (typeof duration !== 'number' || !Number.isFinite(duration) || duration <= 0
              || typeof stagger !== 'number' || !Number.isFinite(stagger) || stagger < 0
              || typeof ease !== 'string') invalid('duration 必须为有限正数，stagger 为非负秒数，ease 为名称。')
            const elements = gsap.utils.toArray<HTMLElement>(targets, root)
            if (!elements.length) invalid('视觉选择器未匹配当前页元素。')
            for (const element of elements) {
              if (!(element instanceof HTMLElement)) invalid('视觉目标必须为页面元素。')
              targetKey(root, element)
            }
            timeline.fromTo(elements, from, { ...to, duration, stagger, ease, immediateRender: false }, position)
            const recent = timeline.recent()
            if (typeof recent === 'function') invalid('视觉段落不能是回调。')
            const startMs = recent.startTime() * 1000
            elements.forEach((target, index) => segments.push({ target, key: targetKey(root, target),
              startMs: startMs + index * stagger * 1000, endMs: startMs + (index * stagger + duration) * 1000, from, to, ease }))
            return facade
          }
        },
      })
      build(facade)
      if (!segments.length || timeline.duration() * 1000 > MAX_MOTION_DURATION_MS) invalid('原生视觉必须具有有限、非空的时长。')
      segments.sort((a, b) => a.startMs - b.startMs || a.key.localeCompare(b.key))
      const initial = new Map<HTMLElement, Values>()
      for (const [index, segment] of segments.entries()) {
        if (segment.startMs < 0) invalid('视觉段落不能在逻辑 0 之前开始。')
        for (const previous of segments.slice(0, index)) {
          if (previous.target === segment.target && previous.endMs > segment.startMs
            && Object.keys(segment.to).some(key => Object.prototype.hasOwnProperty.call(previous.to, key))) {
            throw new MotionError(MOTION_ERROR_PROPERTY_CONFLICT, `视觉目标 ${segment.key} 存在重叠属性轨道。`)
          }
        }
        const values = initial.get(segment.target) ?? {}
        for (const [key, value] of Object.entries(segment.from)) if (!(key in values)) values[key] = value
        initial.set(segment.target, values)
      }
      for (const [target, values] of initial) gsap.set(target, values)
      timeline.invalidate().totalTime(0, true)
    })
  } catch (error) { context.revert(); throw error }
  const labels = Object.fromEntries(Object.entries(timeline.labels).map(([key, value]) => [key, value * 1000]))
  const durationMs = timeline.duration() * 1000
  const digest = digestMotionPayload({ labels, segments: segments.map(({ key, startMs, endMs, from, to, ease }) => (
    { key, startMs, endMs, from, to, ease }
  )) })

  /** reduced 映射为可读终态；静默定位绝不触发跨越的回调。 */
  function sample(positionMs: number, visualMode: MotionVisualMode): void {
    if (disposed) return
    mode = visualMode
    timeline.totalTime(seconds(mode === 'reduced' ? durationMs : Math.max(0, positionMs)), true)
  }
  return { plan: { durationMs, digest, labels }, adapter: {
    type: 'dom',
    async prepare() {},
    async applyAt({ positionMs, visualMode }) { sample(positionMs, visualMode) },
    async freeze(positionMs) {
      sample(positionMs, mode)
      const details = { visualMode: mode, states: segments.map(segment => ({ target: segment.key,
        values: Object.fromEntries(Object.keys(segment.to).map(key => [key, gsap.getProperty(segment.target, key)])) })) }
      return { trackId: 'motion-visual', type: 'dom', positionMs, details,
        digest: digestMotionStateProof('motion-visual', 'dom', positionMs, details) }
    },
    dispose() { if (disposed) return; disposed = true; timeline.kill(); context.revert() },
  } }
}
