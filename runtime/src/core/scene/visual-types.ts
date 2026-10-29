/** 文件功能：定义受 Scene 托管的 GSAP 正向序列接口，支持 DOM、SVG 和页面数值对象。 */
import type { gsap } from 'gsap'
import type { SceneTask, SceneTaskContext } from './types'

/** 保留 GSAP 的属性、位置、标签和错峰语法，链式结果始终留在受管序列内。 */
export interface SceneVisualTimeline {
  to(targets: gsap.TweenTarget, vars: gsap.TweenVars, position?: gsap.Position): SceneVisualTimeline
  from(targets: gsap.TweenTarget, vars: gsap.TweenVars, position?: gsap.Position): SceneVisualTimeline
  fromTo(targets: gsap.TweenTarget, from: gsap.TweenVars, to: gsap.TweenVars, position?: gsap.Position): SceneVisualTimeline
  set(targets: gsap.TweenTarget, vars: gsap.TweenVars, position?: gsap.Position): SceneVisualTimeline
  addLabel(label: string, position?: gsap.Position): SceneVisualTimeline
  /** 每个 call 在本次会话内至多执行一次；异步工作应登记为独立 Scene 任务。 */
  call(callback: (...params: unknown[]) => void, params?: unknown[], position?: gsap.Position): SceneVisualTimeline
}

export interface SceneVisualOptions extends Pick<SceneTask, 'id' | 'role' | 'startMs' | 'afterTrack' | 'offsetMs'> {
  root: Element
  /** -1 表示无限装饰，只有 ambient 可用；其余为 0–1000 次额外重复。 */
  repeat?: number
  repeatDelay?: number
  yoyo?: boolean
  define(timeline: SceneVisualTimeline, context: SceneTaskContext): void
}
