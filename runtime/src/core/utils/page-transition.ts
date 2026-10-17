/** 文件功能：校验过渡配置并解析项目默认与页面覆盖，不继承分组参数。 */
import type { PageAdvanceConfig, PageTransitionConfig } from '../types/page-transition'

export const DEFAULT_PAGE_TRANSITION: PageTransitionConfig = { effect: 'fade', durationMs: 400 }
export const DEFAULT_MEDIA_TIMEOUT_MS = 300000
export const DEFAULT_PAGE_ADVANCE: PageAdvanceConfig = {
  mode: 'manual',
  delayMs: 5000,
  mediaTimeoutMs: DEFAULT_MEDIA_TIMEOUT_MS,
}
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
  if (value == null) return { ...fallback, mediaTimeoutMs: fallback.mediaTimeoutMs ?? DEFAULT_MEDIA_TIMEOUT_MS }
  if (typeof value === 'object' && !Array.isArray(value)) {
    const input = value as Partial<PageAdvanceConfig>
    const delay = input.delayMs ?? DEFAULT_PAGE_ADVANCE.delayMs
    if (
      (input.mode === 'manual' || input.mode === 'timer' || input.mode === 'media_end')
      && Number.isInteger(delay) && delay >= 1000 && delay <= 3600000
    ) {
      return {
        mode: input.mode,
        delayMs: delay,
        mediaTimeoutMs: resolveMediaTimeout(input.mediaTimeoutMs),
      }
    }
  }
  const key = JSON.stringify(value)
  if (!warned.has(key) && warned.size < 20) {
    warned.add(key)
    console.warn('[runtime-transition] 非法翻页配置，已采用默认值', value)
  }
  return { ...fallback, mediaTimeoutMs: fallback.mediaTimeoutMs ?? DEFAULT_MEDIA_TIMEOUT_MS }
}

/** 媒体等待上限与 Backend 保持同一范围，非法值回退默认时长。 */
function resolveMediaTimeout(value: number | undefined): number {
  return Number.isInteger(value) && (value as number) >= 1000 && (value as number) <= 3600000
    ? value as number
    : DEFAULT_MEDIA_TIMEOUT_MS
}
