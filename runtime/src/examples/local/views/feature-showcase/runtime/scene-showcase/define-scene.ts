/** 文件功能：使用公开 Scene 门面组织数字、打字机、SVG 和并行装饰序列，不直接导入 GSAP。 */
import type { PageSceneAuthoringContext } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { createCanvasParticles } from './canvas-particles'

export const SCENE_SENTENCE = '让每一段内容，按自己的节奏完成。'

/** 默认模板完整可读；只有宿主 prepare 才创建序列，stop 恢复完整内容与原样式。 */
export function defineShowcase(scene: PageSceneAuthoringContext): void {
  const output = scene.root.querySelector<HTMLElement>('[data-counter]')!
  const words = scene.root.querySelector<HTMLElement>('[data-typewriter]')!
  const originalNumber = output.textContent, originalWords = words.textContent
  const counter = { value: 0 }, cursor = { value: 0 }, characters = Array.from(SCENE_SENTENCE)
  scene.onCleanup(() => { output.textContent = originalNumber; words.textContent = originalWords })

  scene.visual({ id: 'intro', role: 'blocking', define(timeline) {
    timeline.fromTo('.scene-card', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.5, stagger: 0.08 })
  } })
  scene.visual({ id: 'counter', role: 'blocking', define(timeline) {
    timeline.to(counter, { value: 100, duration: 1, ease: 'none', onUpdate() {
      output.textContent = String(Math.round(counter.value))
    } })
  } })
  scene.visual({ id: 'words', role: 'blocking', afterTrack: 'counter', offsetMs: 120, define(timeline) {
    timeline.to(cursor, { value: characters.length, duration: 1.1, ease: 'none', onStart() { words.textContent = '' }, onUpdate() {
      words.textContent = characters.slice(0, Math.floor(cursor.value)).join('')
    } })
  } })
  scene.visual({ id: 'stroke', role: 'blocking', define(timeline) {
    timeline.fromTo('[data-stroke]', { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.9, ease: 'none' })
  } })
  scene.visual({ id: 'sparkles', role: 'ambient', repeat: -1, yoyo: true, define(timeline) {
    timeline.to('.scene-spark', { y: -14, scale: 1.4, opacity: 0.35, duration: 0.65, stagger: 0.08 })
  } })
  scene.task(createCanvasParticles(scene.root.querySelector('canvas')!, scene.root.querySelector<SVGElement>('[data-particle-poster]')!))
}
