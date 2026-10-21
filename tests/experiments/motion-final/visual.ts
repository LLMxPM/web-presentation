// 文件功能：统一拥有 GSAP 作用域、初始化、静默采样及固化释放；只用于 G0 研究。
import { gsap } from 'gsap'
import type { Plan, Visual } from '../motion-story/types'
import type { StoryDefinition } from './api-types'
const diagnostics = new WeakMap<HTMLElement, { timeline: gsap.core.Timeline; frozen: boolean; disposed: boolean }>()

/** 将平台毫秒换成 GSAP 原生秒；资源插入点通过同名标签自动登记。 */
export function seconds(milliseconds: number): number { return milliseconds / 1000 }

/** 先完整建立未来轨道起态，再交给 transport；页面只填充原生视觉定义。 */
export function createVisual(root: HTMLElement, plan: Plan, build: StoryDefinition['visual']): Visual {
  let timeline!: gsap.core.Timeline
  const context = gsap.context(() => {}, root)
  try { context.add(() => {
    timeline = gsap.timeline({ paused: true, defaults: { ease: 'none' } })
    for (const track of plan.tracks) timeline.addLabel(track.id, seconds(track.startMs))
    const fromTo = timeline.fromTo.bind(timeline)
    // 初态是适配层职责：先写入 from，再创建原生补间；不接受作者关闭初态渲染。
    timeline.fromTo = (targets, fromVars, toVars, position) => {
      if (typeof fromVars === 'number' || typeof position === 'object') throw new Error('GSAP_LEGACY_SIGNATURE_UNSUPPORTED')
      gsap.set(targets, fromVars)
      return fromTo(targets, fromVars, { ...toVars, immediateRender: true }, position)
    }
    build(timeline)
    // immediateRender=false 的未来轨道也必须在首次 0ms 采样前建立初态；两次定位均静默。
    timeline.totalTime(timeline.duration(), true).totalTime(0, true)
  }) } catch (error) { context.revert(); throw error }
  const record = { timeline, frozen: false, disposed: false }; diagnostics.set(root, record)
  return {
    sample(ms) { if (record.frozen || record.disposed) throw new Error('VISUAL_CLOSED'); timeline.totalTime(seconds(Math.max(0, ms)), true) },
    freeze() { if (record.disposed) return; record.frozen = true; timeline.kill() },
    dispose() { if (record.disposed) return; record.disposed = true; timeline.kill(); context.revert() },
  }
}

/** 仅供夹具检查实际时间轴与清理状态，不从创作 SDK 导出。 */
export function inspectVisual(root: HTMLElement) { return diagnostics.get(root) }
