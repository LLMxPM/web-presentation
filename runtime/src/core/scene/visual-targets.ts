/** 文件功能：将视觉目标限制在当前页面 DOM/SVG 或页面自有数值对象，避免选择器穿越画布。 */
import type { gsap } from 'gsap'
import { SceneSessionError } from './types'

/** 选择器始终在 root 中解析；显式 Element 也必须属于同一画布。 */
export function resolveSceneVisualTargets(root: Element, targets: gsap.TweenTarget): object[] {
  const resolved: object[] = []
  /** 递归展平元素/对象集合；不接受 Window、Document 或其它平台对象。 */
  function append(value: unknown): void {
    if (typeof value === 'string') {
      const matches = root.querySelectorAll(value)
      if (!matches.length) throw new SceneSessionError('SCENE_TARGET_INVALID', '视觉选择器未匹配当前页元素。')
      for (const element of matches) append(element)
      return
    }
    if (value instanceof Element) {
      if (value !== root && !root.contains(value)) throw new SceneSessionError('SCENE_TARGET_INVALID', '视觉目标必须属于当前页面。')
      resolved.push(value)
      return
    }
    if (Array.isArray(value) || value instanceof NodeList || value instanceof HTMLCollection) {
      for (const item of Array.from(value)) append(item)
      return
    }
    if (value && typeof value === 'object' && [Object.prototype, null].includes(Object.getPrototypeOf(value))) {
      resolved.push(value)
      return
    }
    throw new SceneSessionError('SCENE_TARGET_INVALID', '视觉目标必须是页面 DOM/SVG 或页面自有数值对象。')
  }
  append(targets)
  if (!resolved.length) throw new SceneSessionError('SCENE_TARGET_INVALID', '视觉目标集合不能为空。')
  return resolved
}
