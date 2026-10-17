/** 文件功能：校验过渡配置并解析项目默认与页面覆盖，不继承分组参数。 */
import type { PageAdvanceConfig, PageTransitionConfig } from '../types/page-transition'

export const DEFAULT_PAGE_TRANSITION: PageTransitionConfig = { effect: 'fade', durationMs: 400 }
export const DEFAULT_PAGE_ADVANCE: PageAdvanceConfig = { mode: 'manual', delayMs: 5000 }
const warned = new Set<string>()

/** 将外部配置归一化；错误有界告警并使用指定默认值。 */
export function resolvePageTransition(value: unknown, fallback = DEFAULT_PAGE_TRANSITION): PageTransitionConfig {
  if (value == null) return { ...fallback }
  if (typeof value === 'object' && !Array.isArray(value)) {
    const input = value as Partial<PageTransitionConfig>
    const duration = input.durationMs ?? 400
    if (input.effect === 'none') return { effect: 'none', durationMs: 0 }
    if ((input.effect === 'fade' || input.effect === 'push') && Number.isInteger(duration) && duration >= 100 && duration <= 2000) {
      return { effect: input.effect, durationMs: duration }
    }
  }
  const key = JSON.stringify(value)
  if (!warned.has(key) && warned.size < 20) {
    warned.add(key)
    console.warn('[runtime-transition] 非法过渡配置，已采用默认效果', value)
  }
  return { ...fallback }
}

/** 校验并归一化翻页推进配置；旧产物缺省时保持手动翻页。 */
export function resolvePageAdvance(value: unknown, fallback: PageAdvanceConfig = DEFAULT_PAGE_ADVANCE): PageAdvanceConfig {
  if (value == null) return { ...fallback }
  if (typeof value === 'object' && !Array.isArray(value)) {
    const input = value as Partial<PageAdvanceConfig>
    const delay = input.delayMs ?? DEFAULT_PAGE_ADVANCE.delayMs
    if ((input.mode === 'manual' || input.mode === 'timer') && Number.isInteger(delay) && delay >= 1000 && delay <= 3600000) {
      return { mode: input.mode, delayMs: delay }
    }
  }
  const key = JSON.stringify(value)
  if (!warned.has(key) && warned.size < 20) {
    warned.add(key)
    console.warn('[runtime-transition] 非法翻页配置，已采用默认值', value)
  }
  return { ...fallback }
}
