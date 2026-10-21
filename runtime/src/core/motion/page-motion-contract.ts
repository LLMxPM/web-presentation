/**
 * 文件功能：定义页面时间轴向放映宿主暴露的窄句柄与 DOM 注册契约。
 *
 * 页面组件拥有 transport 生命周期；宿主只读取快照、发命令和感知完成，
 * 不取得适配器、Mixer、媒体元素或其它内部对象。
 */
import type { MotionTargetRegistry } from './target-registry'
import type { MotionTransport } from './transport'
import type { CompiledMotionPlan, MotionTransportSnapshot, MotionVisualMode } from './types'
import type { MotionSampleResult } from './sampling'

/** 页面根节点上的句柄属性名；跨 realm 只依赖固定字符串。 */
export const PAGE_MOTION_HANDLE_KEY = '__runtimePageMotionV1'
/** 可查询的 DOM 标记；与属性名一起登记/注销。 */
export const PAGE_MOTION_ATTR = 'data-runtime-page-motion'

export interface PageMotionHandle {
  readonly plan: CompiledMotionPlan
  readonly ownership: MotionTargetRegistry
  /** MediaSession 过滤：已由时间轴独占的媒体不再自动播放或归零。 */
  isElementClaimed(element: Element): boolean
  getSnapshot(): MotionTransportSnapshot
  prepare(): Promise<void>
  play(): Promise<boolean>
  pause(): boolean
  resume(): Promise<boolean>
  seek(positionMs: number): Promise<void>
  restart(): Promise<boolean>
  setMuted(muted: boolean): void
  sampleAt(positionMs: number, visualMode?: MotionVisualMode): Promise<MotionSampleResult>
  subscribe(listener: (snapshot: MotionTransportSnapshot) => void): () => void
  /** 由页面组件调用；注销 DOM 句柄并释放 transport。 */
  dispose(): void
}

/** 从元素读取页面时间轴句柄；形状不合法时返回 null。 */
export function readPageMotionHandle(element: Element | null | undefined): PageMotionHandle | null {
  if (!element) return null
  const candidate = (element as unknown as Record<string, unknown>)[PAGE_MOTION_HANDLE_KEY]
  if (!candidate || typeof candidate !== 'object') return null
  const record = candidate as { getSnapshot?: unknown; play?: unknown; subscribe?: unknown }
  if (typeof record.getSnapshot !== 'function' || typeof record.play !== 'function' || typeof record.subscribe !== 'function') {
    return null
  }
  return candidate as PageMotionHandle
}

/** 在页面根内查找时间轴句柄；页面根自身优先。 */
export function findPageMotionHandle(root: ParentNode): PageMotionHandle | null {
  if (root instanceof Element) {
    const direct = readPageMotionHandle(root)
    if (direct) return direct
  }
  const marked = root.querySelector<HTMLElement>(`[${PAGE_MOTION_ATTR}="v1"]`)
  return readPageMotionHandle(marked)
}

/**
 * 将 transport 包装为页面句柄并登记到根元素。
 * 只由页面 composable 调用；宿主读取后不得 dispose。
 */
export function createPageMotionHandle(root: Element, transport: MotionTransport): PageMotionHandle {
  let disposed = false
  const handle: PageMotionHandle = {
    plan: transport.plan,
    ownership: transport.ownership,
    isElementClaimed: element => transport.ownership.isElementClaimed(element),
    getSnapshot: () => transport.getSnapshot(),
    prepare: () => transport.prepare(),
    play: () => transport.play(),
    pause: () => transport.pause(),
    resume: () => transport.resume(),
    seek: positionMs => transport.seek(positionMs),
    restart: () => transport.restart(),
    setMuted: muted => transport.setMuted(muted),
    sampleAt: (positionMs, visualMode) => transport.sampleAt(positionMs, visualMode),
    subscribe: listener => transport.subscribe(listener),
    dispose: () => {
      if (disposed) return
      disposed = true
      unregisterPageMotionHandle(root, handle)
      transport.dispose()
    },
  }
  ;(root as unknown as Record<string, unknown>)[PAGE_MOTION_HANDLE_KEY] = handle
  root.setAttribute(PAGE_MOTION_ATTR, 'v1')
  return handle
}

/** 只注销同一引用，避免旧页面卸载时移除新页面句柄。 */
export function unregisterPageMotionHandle(root: Element, handle: PageMotionHandle): void {
  const record = root as unknown as Record<string, unknown>
  if (record[PAGE_MOTION_HANDLE_KEY] === handle) {
    delete record[PAGE_MOTION_HANDLE_KEY]
    root.removeAttribute(PAGE_MOTION_ATTR)
  }
}
