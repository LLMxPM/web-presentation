/**
 * 文件功能：公开 page-timeline.v1 创作入口，合并定义、页面绑定与唯一 transport。
 *
 * 定义只描述轨道与目标 key；bindings 把目标 key 解析到页面内元素。
 * 页面最多注册一个时间轴，宿主只通过窄句柄读取状态与发送播放命令。
 */

import { onBeforeUnmount, onMounted, shallowReadonly, shallowRef, toValue, unref, type MaybeRefOrGetter, type Ref } from 'vue'

import { useRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { compilePageTimeline } from '@/core/motion/compile'
import { createDefaultMotionAdapterFactory } from '@/core/motion/default-adapters'
import { createNativeVisual, type NativeVisualBuilder } from '@/core/motion/native-visual'
import { createMotionResourceBuilder, type MotionResourceBuilder } from '@/core/motion/resource-builder'
import { registerMotionReadiness } from '@/core/motion/readiness'
import { MOTION_ERROR_TARGET_INVALID, MotionError, toMotionError } from '@/core/motion/errors'
import {
  createPageMotionHandle,
  type PageMotionHandle,
} from '@/core/motion/page-motion-contract'
import type { MotionSampleResult } from '@/core/motion/sampling'
import { createMotionTransport } from '@/core/motion/transport'
import type {
  CompiledMotionPlan,
  DomMotionTrackDefinition,
  MediaMotionTrackDefinition,
  ModelMotionTrackDefinition,
  MotionTransportSnapshot,
  MotionVisualMode,
  PageTimelineDefinition,
  MotionPosterDefinition,
  MotionTrackDefinition,
} from '@/core/motion/types'

export { seconds } from '@/core/motion/native-visual'
export type { NativeVisualTimeline } from '@/core/motion/native-visual'
export type { MotionResourceBuilder } from '@/core/motion/resource-builder'

/** 组件实例写入的临时绑定属性；卸载时只清理本次写入的值。 */
const MOTION_BINDING_ATTR = 'data-runtime-motion-binding'

export type PageTimelineBinding = string | HTMLElement | Ref<HTMLElement | null | undefined>
export type PageTimelineBindingMap = Record<string, PageTimelineBinding>

export type PublicDomMotionTrackDefinition<K extends string> = Omit<DomMotionTrackDefinition, 'target'> & {
  /** 必须来自 bindings 的页面目标 key，不能直接写 CSS 选择器。 */
  target: K
}

export type PublicMotionTrackDefinition<K extends string> =
  | PublicDomMotionTrackDefinition<K>
  | MediaMotionTrackDefinition
  | ModelMotionTrackDefinition

export interface PageTimelineAuthoringDefinition<K extends string> extends Omit<PageTimelineDefinition, 'tracks'> {
  tracks: PublicMotionTrackDefinition<K>[]
}

export interface PageTimelineAuthoringContext {
  readonly root: HTMLElement
  resources(): MotionResourceBuilder
}

interface PageTimelineCommonOptions<B extends PageTimelineBindingMap> {
  /** 目标 key 到 CSS 选择器、元素或元素 ref 的绑定。 */
  bindings: B
  /** 页面根节点；时间轴句柄注册在这里供放映宿主发现。 */
  root: MaybeRefOrGetter<HTMLElement | null | undefined>
  /** 进入快照的诊断路径；缺省为空串。 */
  pagePath?: string
  /** 显式视觉模式；缺省读取调试参数与系统降动效偏好。 */
  visualMode?: MotionVisualMode
  /** 会话静音初值；放映宿主仍可覆盖。 */
  muted?: boolean
  /** 预览中是否自动应用 poster；放映始终保留动画初态，静态捕获由就绪协议采样。 */
  applyPoster?: boolean
}

/** 默认创作采用资源 builder 与原生视觉；旧 definition 仅兼容内部已有夹具。 */
export type UsePageTimelineOptions<K extends string, B extends PageTimelineBindingMap> = PageTimelineCommonOptions<B> & (
  | { definition: PageTimelineAuthoringDefinition<K>; define?: never; timelineId?: never; poster?: never }
  | { definition?: never; timelineId: string; poster?: MotionPosterDefinition
      define(context: PageTimelineAuthoringContext): { plan: MotionTrackDefinition[]; visual: NativeVisualBuilder } }
)

export interface UsePageTimelineApi {
  plan: Readonly<Ref<CompiledMotionPlan | null>>
  state: Readonly<Ref<MotionTransportSnapshot | null>>
  error: Readonly<Ref<MotionError | null>>
  ready: Promise<void>
  prepare(): Promise<void>
  play(): Promise<boolean>
  pause(): boolean
  resume(): Promise<boolean>
  restart(): Promise<boolean>
  seek(positionMs: number): Promise<void>
  sampleAt(positionMs: number, visualMode?: MotionVisualMode): Promise<MotionSampleResult>
  setMuted(muted: boolean): void
  setVisualMode(mode: MotionVisualMode): void
  dispose(): void
}

/**
 * 声明页面时间轴。DOM 轨道 target 由类型限制为 bindings 的 key；
 * 媒体与模型轨道仍按资源逻辑名由对应 Asset*.v2 组件渲染。
 */
export function usePageTimeline<B extends PageTimelineBindingMap>(
  options: UsePageTimelineOptions<Extract<keyof B, string>, B>,
): UsePageTimelineApi {
  const execution = useRuntimeExecutionPolicy()
  const plan = shallowRef<CompiledMotionPlan | null>(null)
  const state = shallowRef<MotionTransportSnapshot | null>(null)
  const error = shallowRef<MotionError | null>(null)
  const markerElements: Array<{ element: HTMLElement; value: string }> = []
  let handle: PageMotionHandle | null = null
  let disposed = false
  let resolveReady: () => void = () => {}
  let rejectReady: (reason: unknown) => void = () => {}
  const ready = new Promise<void>((resolve, reject) => {
    resolveReady = resolve
    rejectReady = reject
  })
  // 页面不消费 ready 时也不能产生未处理拒绝。
  void ready.catch(() => {})
  const unregisterReadiness = registerMotionReadiness({
    root: () => toValue(options.root),
    ready,
    async prepareStatic() {
      const current = ensureHandle()
      await current.prepare()
      await current.sampleAt(current.plan.posterTimeMs, 'full')
    },
  })

  function ensureHandle(): PageMotionHandle {
    if (!handle || disposed) {
      throw new MotionError(MOTION_ERROR_TARGET_INVALID, '页面时间轴尚未挂载或已释放。')
    }
    return handle
  }

  function clearBindings(): void {
    for (const marker of markerElements) {
      if (marker.element.getAttribute(MOTION_BINDING_ATTR) === marker.value) {
        marker.element.removeAttribute(MOTION_BINDING_ATTR)
      }
    }
    markerElements.length = 0
  }

  /** 把绑定值收敛为当前页面可查询的 CSS 选择器；元素绑定写入实例级临时属性。 */
  function resolveBinding(key: string, raw: PageTimelineBinding): string {
    if (typeof raw === 'string') {
      const selector = raw.trim()
      if (!selector) {
        throw new MotionError(MOTION_ERROR_TARGET_INVALID, `绑定 ${key} 的选择器不能为空。`, {
          fieldPath: `bindings.${key}`,
        })
      }
      return selector
    }
    const element = raw instanceof HTMLElement ? raw : unref(raw)
    if (!(element instanceof HTMLElement)) {
      throw new MotionError(MOTION_ERROR_TARGET_INVALID, `绑定 ${key} 未解析到页面元素。`, {
        fieldPath: `bindings.${key}`,
      })
    }
    // 查询始终限定在本页 root 内，身份使用稳定 key，不掺入挂载次数。
    const value = `binding-${encodeURIComponent(key)}`
    element.setAttribute(MOTION_BINDING_ATTR, value)
    markerElements.push({ element, value })
    return `[${MOTION_BINDING_ATTR}="${value}"]`
  }

  /** 把公开 key 翻译为内部选择器；媒体/模型轨道显式 selector 也允许引用绑定 key。 */
  function toInternalDefinition(
    definition: PageTimelineAuthoringDefinition<Extract<keyof B, string>>,
    selectors: Map<string, string>,
  ): PageTimelineDefinition {
    return {
      ...definition,
      tracks: definition.tracks.map(track => {
        if (track.type === 'dom') {
          const selector = selectors.get(track.target)
          if (!selector) {
            throw new MotionError(MOTION_ERROR_TARGET_INVALID, `轨道 ${track.id} 未绑定目标 ${track.target}。`, {
              fieldPath: `timeline.tracks.${track.id}.target`,
              trackId: track.id,
            })
          }
          return { ...track, target: selector }
        }
        if (track.selector && selectors.has(track.selector)) {
          return { ...track, selector: selectors.get(track.selector) }
        }
        return track
      }),
    }
  }

  /** 读取当前预览的视觉偏好：显式参数优先，其次调试参数与系统降动效设置。 */
  function resolveVisualMode(): MotionVisualMode {
    if (options.visualMode) return options.visualMode
    if (typeof window !== 'undefined') {
      const queryMode = new URLSearchParams(window.location.search).get('runtimeMotionVisualMode')
      if (queryMode === 'reduced' || queryMode === 'full') return queryMode
      if (typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        return 'reduced'
      }
    }
    return 'full'
  }

  /** 安装 transport；放映在切页过渡前准备初态，预览按需固化 poster。 */
  async function mountTimeline(): Promise<void> {
    if (disposed) return
    const root = toValue(options.root)
    if (!(root instanceof HTMLElement)) {
      throw new MotionError(MOTION_ERROR_TARGET_INVALID, '页面时间轴缺少有效根节点。', {
        fieldPath: 'root',
      })
    }
    const selectors = new Map<string, string>()
    Object.entries(options.bindings).forEach(([key, value]) => {
      selectors.set(key, resolveBinding(key, value))
    })
    const story = options.define?.({ root, resources: createMotionResourceBuilder })
    const definition = options.definition ?? {
      schemaVersion: 1 as const, timelineId: options.timelineId!, tracks: story!.plan, poster: options.poster,
    }
    const internalDefinition = toInternalDefinition(definition as PageTimelineAuthoringDefinition<Extract<keyof B, string>>, selectors)
    let nativeVisual: ReturnType<typeof createNativeVisual> | undefined
    let compiled: CompiledMotionPlan
    try {
      if (story) {
        const resources = compilePageTimeline({ ...internalDefinition, poster: undefined }, { allowEmpty: true })
        nativeVisual = createNativeVisual(root, resources.labels, story.visual)
      }
      compiled = compilePageTimeline(internalDefinition, { visual: nativeVisual?.plan })
    } catch (cause) {
      nativeVisual?.adapter.dispose()
      clearBindings()
      throw cause
    }
    const policy = execution.value
    const visualMode = resolveVisualMode()
    const createdTransport = createMotionTransport({
      plan: compiled,
      root,
      pagePath: options.pagePath ?? '',
      generation: 1,
      createAdapter: createDefaultMotionAdapterFactory(),
      visualAdapter: nativeVisual?.adapter,
      visualMode,
      allowMediaPlayback: policy.allowMediaPlayback,
      muted: options.muted === true,
      onState: snapshot => {
        state.value = snapshot
        if (snapshot.phase === 'error' && snapshot.errorCode) {
          error.value = new MotionError(
            snapshot.errorCode as MotionError['code'],
            snapshot.errorMessage || '页面时间轴执行失败。',
          )
        }
      },
    })
    plan.value = compiled
    handle = createPageMotionHandle(root, createdTransport)
    state.value = createdTransport.getSnapshot()
    // 作者声明的可读海报只用于预览；放映不能先展示终态、等过渡结束再回到零点。
    const shouldApplyPoster = policy.kind !== 'presentation'
      && (options.applyPoster ?? policy.kind === 'interactive-preview')
    if (shouldApplyPoster || policy.kind === 'presentation') {
      await createdTransport.prepare()
      if (disposed) return
      if (shouldApplyPoster) await createdTransport.sampleAt(compiled.posterTimeMs, visualMode)
    }
  }

  onMounted(() => {
    mountTimeline()
      .then(() => resolveReady())
      .catch((cause: unknown) => {
        // 快速翻页或切换宿主已卸载本实例时，迟到的准备/采样回执不再报告为当前页失败。
        if (disposed) { resolveReady(); return }
        const motionError = toMotionError(cause)
        error.value = motionError
        console.error('[usePageTimeline] 初始化失败', motionError)
        rejectReady(motionError)
      })
  })

  onBeforeUnmount(() => dispose())

  /** 释放 transport、句柄与临时绑定属性；重复调用无副作用。 */
  function dispose(): void {
    if (disposed) return
    disposed = true
    unregisterReadiness()
    handle?.dispose()
    handle = null
    clearBindings()
    state.value = null
  }

  return {
    plan: shallowReadonly(plan),
    state: shallowReadonly(state),
    error: shallowReadonly(error),
    ready,
    prepare: async () => {
      await ensureHandle().prepare()
    },
    play: async () => ensureHandle().play(),
    pause: () => ensureHandle().pause(),
    resume: async () => ensureHandle().resume(),
    restart: async () => ensureHandle().restart(),
    seek: async positionMs => ensureHandle().seek(positionMs),
    sampleAt: async (positionMs, visualMode) => ensureHandle().sampleAt(positionMs, visualMode),
    setMuted: muted => ensureHandle().setMuted(muted),
    setVisualMode: mode => ensureHandle().setVisualMode(mode),
    dispose,
  }
}
