/** 文件功能：保留 GSAP 核心属性表达力，拦截可选插件参数并为序列回调接入取消与异常围栏。 */
import type { gsap } from 'gsap'
import { SceneSessionError } from './types'

/** CSS 与 attr 属于 Runtime 自带核心能力；可选插件不在本轮支持范围。 */
const OPTIONAL_PLUGIN_FIELDS = new Set(['scrollTrigger', 'drawSVG', 'morphSVG', 'motionPath', 'physics2D', 'physicsProps',
  'inertia', 'scrambleText', 'splitText', 'text', 'scrollTo', 'pixi', 'easel', 'flip', 'observer'])

export type ProtectVisualCallback = (callback: (...params: unknown[]) => unknown, once: boolean) => (...params: unknown[]) => unknown

/** 包装生命周期与函数值，prepare 不执行回调；onUpdate 和动态取值可在播放帧中重复执行。 */
export function protectSceneVisualVars(vars: gsap.TweenVars, protect: ProtectVisualCallback, infinite: boolean): gsap.TweenVars {
  if (!vars || typeof vars !== 'object') throw new SceneSessionError('SCENE_VISUAL_INVALID', '视觉参数必须是对象。')
  const output: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(vars)) {
    if (OPTIONAL_PLUGIN_FIELDS.has(key)) throw new SceneSessionError('SCENE_PLUGIN_UNSUPPORTED', 'Scene 不支持 GSAP 可选插件参数。')
    if ((key === 'paused' || key === 'reversed') && value) throw new SceneSessionError('SCENE_VISUAL_INVALID', '子动画不能自行暂停或反向播放。')
    if (key === 'repeat' && (!Number.isInteger(value) || value < (infinite ? -1 : 0) || value > 1000)) {
      throw new SceneSessionError('SCENE_VISUAL_INVALID', '有限序列不能包含无限重复，repeat 必须是允许范围内的整数。')
    }
    if (key === 'modifiers') throw new SceneSessionError('SCENE_PLUGIN_UNSUPPORTED', '本轮不提供 GSAP modifiers 插件回调。')
    if (typeof value === 'function') output[key] = protect(value, key.startsWith('on') && key !== 'onUpdate')
    else if (key === 'startAt' || key === 'css' || key === 'attr' || (key === 'stagger' && typeof value === 'object')
      || (key === 'snap' && typeof value === 'object')) output[key] = protectSceneVisualVars(value, protect, infinite)
    else if (key === 'keyframes') {
      output[key] = Array.isArray(value)
        ? value.map(frame => protectSceneVisualVars(frame, protect, infinite))
        : Object.fromEntries(Object.entries(value).map(([at, frame]) => [at,
          frame && typeof frame === 'object' && !Array.isArray(frame) ? protectSceneVisualVars(frame, protect, infinite) : frame]))
    } else output[key] = value
  }
  return output as gsap.TweenVars
}
