// 文件功能：让受控资源 builder 与 JSON 研究路线复用同一套原生 DOM 编排，避免改变效果偏置比较。
import { gsap } from 'gsap'
import { createScope, createTimeline, stagger } from 'animejs'
import type { Engine, Plan, Track, Visual } from './types'

/** 受控路线保留库的错峰和段落组合；资源关系只提供插入点。 */
export function nativeVisual(engine: Engine, root: HTMLElement, detailMs: number, demoMs: number): Visual {
  if (engine === 'gsap') {
    let timeline: gsap.core.Timeline
    const context = gsap.context(() => {
      const intro = gsap.timeline()
        .fromTo('.title', { opacity: 0, y: 32 }, { opacity: 1, y: 0, duration: 0.4, ease: 'none' })
        .fromTo('.card', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.3, stagger: 0.1, ease: 'none' }, 0.6)
      timeline = gsap.timeline({ paused: true }).add(intro, 0)
        .fromTo('.clip-caption', { opacity: 0 }, { opacity: 1, duration: 0.4, ease: 'none' }, detailMs / 1000)
        .fromTo('.demo-caption', { opacity: 0, y: 32 }, { opacity: 1, y: 0, duration: 0.4, ease: 'none' }, demoMs / 1000)
    }, root)
    return { sample: ms => timeline!.totalTime(ms / 1000, true), freeze: () => timeline!.kill(), dispose: () => context.revert() }
  }
  let timeline: ReturnType<typeof createTimeline>, intro: ReturnType<typeof createTimeline>
  const scope = createScope({ root }).add(() => {
    intro = createTimeline({ autoplay: false })
      .add('.title', { opacity: [0, 1], y: [32, 0], duration: 400, ease: 'linear' })
      .add('.card', { opacity: [0, 1], y: [24, 0], duration: 300, delay: stagger(100), ease: 'linear' }, 600)
    intro.init()
    timeline = createTimeline({ autoplay: false }).sync(intro, 0)
      .add('.clip-caption', { opacity: [0, 1], duration: 400, ease: 'linear' }, detailMs)
      .add('.demo-caption', { opacity: [0, 1], y: [32, 0], duration: 400, ease: 'linear' }, demoMs).init()
  })
  return { sample: ms => timeline!.seek(ms, true), freeze: () => { timeline!.cancel(); intro!.cancel() }, dispose: () => scope.revert() }
}

/** JSON 示例只实现原草案的有限 enter；它不代表候选库的完整能力边界。 */
export function jsonVisual(engine: Engine, root: HTMLElement, plan: Plan): Visual {
  const selector = (track: Track) => track.target.startsWith('card') ? `.card:nth-child(${track.target.slice(4)})` : `.${track.target}`
  if (engine === 'gsap') {
    const timeline = gsap.timeline({ paused: true })
    const context = gsap.context(() => {
      for (const t of plan.tracks.filter(track => track.type === 'enter')) timeline.fromTo(selector(t), { opacity: 0, y: t.fromY ?? 0 }, { opacity: 1, y: 0, duration: t.durationMs / 1000, ease: 'none' }, t.startMs / 1000)
    }, root)
    return { sample: ms => timeline.totalTime(ms / 1000, true), freeze: () => timeline.kill(), dispose: () => { timeline.kill(); context.revert() } }
  }
  const timeline = createTimeline({ autoplay: false })
  const scope = createScope({ root }).add(() => {
    for (const t of plan.tracks.filter(track => track.type === 'enter')) timeline.add(selector(t), { opacity: [0, 1], y: [t.fromY ?? 0, 0], duration: t.durationMs, ease: 'linear' }, t.startMs)
    timeline.init()
  })
  return { sample: ms => timeline.seek(ms, true), freeze: () => timeline.cancel(), dispose: () => { timeline.revert(); scope.revert() } }
}
