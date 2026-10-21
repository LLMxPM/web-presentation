// 文件功能：WP01 GSAP 候选后端；私有暂停时间轴不接管媒体与 Three.js 时钟。
import { gsap } from 'gsap'

/** 使用和 WAAPI 完全相同的两个属性轨道、起止值与线性曲线。 */
export function createDom(targets) {
  targets.forEach(target => { target.style.willChange = 'transform, opacity' })
  const timeline = gsap.timeline({ paused: true })
  targets.forEach((target, i) => {
    timeline.fromTo(target, { opacity: 0 }, { opacity: 1, duration: 0.8, ease: 'none', immediateRender: true }, i * 0.015)
    timeline.fromTo(target, { y: 60 }, { y: 0, duration: 0.8, ease: 'none', immediateRender: true }, i * 0.015)
  })
  // 实验只使用绝对采样；GSAP 默认 ticker 不能成为第二个全局时钟。
  gsap.ticker.sleep()
  return {
    sample(ms) { timeline.totalTime(ms / 1000, true) },
    freeze() { timeline.kill(); gsap.ticker.sleep() },
    dispose() { timeline.kill(); gsap.ticker.sleep(); targets.forEach(target => { target.style.willChange = '' }) },
    count() { return gsap.globalTimeline.getChildren(true, true, true).length },
  }
}
