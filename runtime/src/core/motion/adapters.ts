/**
 * 文件功能：定义与执行引擎无关的页内编排适配器接口。
 *
 * WP04–WP06 只需实现 prepare/applyAt/play/pause/freeze/dispose；
 * 计划编译、时钟、状态机与目标所有权由 transport 统一维护。
 */
import type { MotionTargetRegistry } from './target-registry'
import type {
  CompiledMotionPlan,
  CompiledMotionTrack,
  MotionStateProof,
  MotionVisualMode,
} from './types'

/** 适配器准备上下文；signal 在取消、换页与 dispose 时触发。 */
export interface MotionAdapterContext {
  plan: CompiledMotionPlan
  track: CompiledMotionTrack
  /** 当前活动页面根节点；适配器不得跨根查询。 */
  root: ParentNode
  signal: AbortSignal
  visualMode: MotionVisualMode
  allowMediaPlayback: boolean
  /** 会话级静音；不写回页面配置。 */
  muted: boolean
  generation: number
  ownership: MotionTargetRegistry
}

export interface MotionAdapterApplyOptions {
  /** 逻辑时间（毫秒），可位于轨道区间外；适配器按区间钳制。 */
  positionMs: number
  visualMode: MotionVisualMode
  /** 定位/捕获必须精确 seek，不能复用实时漂移容差。 */
  forceSeek?: boolean
}

/** 适配器提供的真实媒体时钟；transport 只在主媒体轨道上消费。 */
export interface MotionAdapterClockState {
  /** 真实媒体当前位置（毫秒，已扣除裁切起点前）。 */
  positionMs: number
  ended: boolean
  blocked: boolean
  buffering: boolean
}

/**
 * 单轨道适配器。所有方法必须幂等或在 dispose 后安全返回；
 * applyAt 不得补发跨过的声音、网络请求或业务回调。
 */
export interface MotionTrackAdapter {
  readonly type: CompiledMotionTrack['type']
  prepare(): Promise<void>
  applyAt(options: MotionAdapterApplyOptions): Promise<void>
  /** 开始实时播放；浏览器拒绝时抛 MotionError(TIMELINE_MEDIA_BLOCKED)。 */
  play?(): Promise<void>
  pause?(): void
  setMuted?(muted: boolean): void
  getClock?(): MotionAdapterClockState | null
  freeze?(positionMs: number): Promise<MotionStateProof>
  dispose(): void
}

export type MotionAdapterFactory = (context: MotionAdapterContext) => MotionTrackAdapter

/** 可注入的帧调度器；测试使用虚拟调度器避免依赖浏览器 rAF。 */
export interface MotionScheduler {
  request(callback: () => void): number
  cancel(handle: number): void
}

/** 默认真实浏览器调度器；没有 rAF 时回退到 timeout。 */
export function createMotionScheduler(): MotionScheduler {
  return {
    request: (callback) => {
      if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
        return window.requestAnimationFrame(callback)
      }
      return window.setTimeout(callback, 16)
    },
    cancel: (handle) => {
      if (typeof window !== 'undefined' && typeof window.cancelAnimationFrame === 'function') {
        window.cancelAnimationFrame(handle)
        return
      }
      window.clearTimeout(handle)
    },
  }
}
