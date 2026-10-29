/** 文件功能：让独立 GSAP 序列正向播放并以实际完成回报 Scene，负责作用域、冻结和离页恢复。 */
import { gsap } from 'gsap'
import { MAX_SCENE_DURATION_MS } from './task-graph'
import { SceneSessionError, type SceneTask, type SceneTaskContext } from './types'
import { resolveSceneVisualTargets } from './visual-targets'
import { protectSceneVisualVars } from './visual-vars'
import type { SceneVisualOptions, SceneVisualTimeline } from './visual-types'

/** 构造任务描述，不创建时间轴；真正的 GSAP 实例只在非静态会话 prepare 创建。 */
export function createGsapSceneTask(options: SceneVisualOptions): SceneTask {
  options = { ...options }
  const infinite = options.repeat === -1
  let timeline: gsap.core.Timeline | null = null, scope: gsap.Context | null = null
  let disposed = false, started = false, settled = false, building = false
  let resolveRun: () => void, rejectRun: (error: unknown) => void
  let running: Promise<void> | null = null
  let context: SceneTaskContext | null = null

  /** 清理先关闭回调，再撤销动画和样式；退出不触发 onComplete/onInterrupt 用户副作用。 */
  function dispose(): void {
    if (disposed) return
    disposed = true
    timeline?.kill()
    scope?.revert()
    resolveRun?.()
  }

  /** 回调异常变为任务失败；不得从 GSAP 的 ticker 传播为未处理浏览器异常。 */
  function fail(error: unknown): void {
    if (disposed || settled) return
    settled = true
    rejectRun?.(error)
    timeline?.pause()
    // 等当前 GSAP render 栈退出再恢复样式，防止 onStart 异常后的剩余渲染覆盖清理结果。
    queueMicrotask(dispose)
  }

  /** 用会话信号与执行标记围住每个回调，避免准备、重播周期或取消造成重复外部工作。 */
  function protect(callback: (...params: unknown[]) => unknown, once: boolean) {
    let invoked = false
    return function guardedCallback(this: unknown, ...params: unknown[]): unknown {
      if (!started || disposed || settled || context?.signal.aborted || (once && invoked)) return
      invoked = true
      try {
        const result = callback.apply(this, params)
        if (result && typeof (result as PromiseLike<unknown>).then === 'function') {
          void Promise.resolve(result).catch(() => {})
          fail(new SceneSessionError('SCENE_VISUAL_ASYNC_CALLBACK', '异步回调必须登记为独立 Scene 任务。', options.id))
          return
        }
        return result
      } catch (error) { fail(error) }
    }
  }

  /** 只开放填充序列的方法，目标和回调全部经过同一围栏；不暴露 seek/restart/注册插件。 */
  function facade(raw: gsap.core.Timeline): SceneVisualTimeline {
    /** 填充结束后封口，防止迟到异步代码修改任务时长、创建新子动画或越过清理域。 */
    const assertBuilding = () => {
      if (!building || disposed || context?.signal.aborted) throw new SceneSessionError('SCENE_REGISTRATION_CLOSED', '视觉序列只能在 prepare 填充函数中修改。', options.id)
    }
    const targets = (value: gsap.TweenTarget) => { assertBuilding(); return resolveSceneVisualTargets(options.root, value) }
    const vars = (value: gsap.TweenVars) => protectSceneVisualVars(value, protect, infinite)
    const api: SceneVisualTimeline = {
      to(value, to, at) { raw.to(targets(value), { ...vars(to), immediateRender: false }, at); return api },
      from(value, from, at) { raw.from(targets(value), { ...vars(from), immediateRender: false }, at); return api },
      fromTo(value, from, to, at) { raw.fromTo(targets(value), vars(from), { ...vars(to), immediateRender: false }, at); return api },
      set(value, to, at) { raw.set(targets(value), { ...vars(to), immediateRender: false }, at); return api },
      addLabel(label, at) { assertBuilding(); raw.addLabel(label, at); return api },
      call(callback, params, at) { assertBuilding(); raw.call(protect(callback, true), params, at); return api },
    }
    return api
  }

  return { id: options.id, role: options.role, finite: !infinite,
    startMs: options.startMs, afterTrack: options.afterTrack, offsetMs: options.offsetMs,
    prepare(value) {
      if (timeline || disposed) throw new SceneSessionError('SCENE_VISUAL_INVALID', '视觉任务实例不能跨会话复用。', options.id)
      if (!(options.root instanceof Element)) throw new SceneSessionError('SCENE_TARGET_INVALID', '视觉任务缺少页面根节点。', options.id)
      if (!Number.isInteger(options.repeat ?? 0) || (options.repeat ?? 0) < -1 || (options.repeat ?? 0) > 1000
        || !Number.isFinite(options.repeatDelay ?? 0) || (options.repeatDelay ?? 0) < 0 || (options.repeatDelay ?? 0) > 3600) {
        throw new SceneSessionError('SCENE_VISUAL_INVALID', '视觉重复次数或间隔非法。', options.id)
      }
      context = value
      value.onCleanup(dispose)
      scope = gsap.context(() => {}, options.root)
      try {
        scope.add(() => {
          timeline = gsap.timeline({ paused: true, repeat: options.repeat ?? 0, repeatDelay: options.repeatDelay ?? 0,
            yoyo: options.yoyo ?? false, onComplete() { if (!disposed && !settled) { settled = true; resolveRun?.() } } })
          let result: unknown
          building = true
          try { result = options.define(facade(timeline), value) }
          finally { building = false }
          if (result && typeof (result as PromiseLike<unknown>).then === 'function') {
            void Promise.resolve(result).catch(() => {})
            throw new SceneSessionError('SCENE_VISUAL_INVALID', '视觉填充必须同步，异步准备请使用独立任务。', options.id)
          }
          const duration = infinite ? timeline.duration() : timeline.totalDuration()
          if (!Number.isFinite(duration) || duration <= 0 || duration * 1000 > MAX_SCENE_DURATION_MS) {
            throw new SceneSessionError('SCENE_VISUAL_INVALID', '视觉序列必须具有非空且不超过一小时的有限单轮时长。', options.id)
          }
        })
      } catch (error) { dispose(); throw error }
    },
    run() {
      if (running) return running
      if (!timeline || disposed) throw new SceneSessionError('SCENE_VISUAL_INVALID', '视觉任务尚未准备或已释放。', options.id)
      running = new Promise<void>((resolve, reject) => { resolveRun = resolve; rejectRun = reject })
      started = true
      timeline.play()
      return running
    },
    setSuspended(value) { if (!disposed && started && !settled) timeline?.paused(value) },
  }
}
