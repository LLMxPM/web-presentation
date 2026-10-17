/**
 * 文件功能：项目放映配置在表单草稿与 API 毫秒值之间的转换、范围收敛与默认值。
 */

import type { SlideshowSettings } from '@/types/api'

export type SlideshowEffect = 'none' | 'fade' | 'push'
export type SlideshowAdvanceMode = 'manual' | 'timer' | 'media_end'

export interface SlideshowDraft {
  effect: SlideshowEffect
  durationSeconds: string
  advanceMode: SlideshowAdvanceMode
  delaySeconds: string
  mediaTimeoutSeconds?: string
  loop: boolean
  autoStart: boolean
}

export const DEFAULT_SLIDESHOW_SETTINGS: SlideshowSettings = {
  transition: { effect: 'fade', duration_ms: 400 },
  advance: { mode: 'manual', delay_ms: 5000, media_timeout_ms: 300000 },
  loop: false,
  auto_start: false,
}

const TRANSITION_DURATION_MIN_MS = 100
const TRANSITION_DURATION_MAX_MS = 2000
const ADVANCE_DELAY_MIN_MS = 1000
const ADVANCE_DELAY_MAX_MS = 3_600_000
const MEDIA_TIMEOUT_MIN_MS = 1000
const MEDIA_TIMEOUT_MAX_MS = 3_600_000

/**
 * 把毫秒值转换为无冗余小数的秒字符串。
 * @param value 毫秒值
 */
export function formatMillisecondsAsSeconds(value: number): string {
  return (value / 1000).toFixed(3).replace(/\.?0+$/, '')
}

/**
 * 把秒字符串转换为毫秒；非法输入返回 null，由调用方决定兜底值。
 * @param value 秒字符串
 */
export function parseSecondsToMilliseconds(value: string): number | null {
  const parsed = Number.parseFloat(String(value ?? '').trim())
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null
  }
  return Math.round(parsed * 1000)
}

/**
 * 将项目放映配置转换为表单草稿。
 * @param settings 项目放映配置；缺失时使用平台默认值
 */
export function createSlideshowDraft(settings?: SlideshowSettings | null): SlideshowDraft {
  const resolved = settings ?? DEFAULT_SLIDESHOW_SETTINGS
  return {
    effect: resolved.transition.effect,
    durationSeconds: formatMillisecondsAsSeconds(resolved.transition.duration_ms),
    advanceMode: resolved.advance.mode,
    delaySeconds: formatMillisecondsAsSeconds(resolved.advance.delay_ms),
    mediaTimeoutSeconds: formatMillisecondsAsSeconds(resolved.advance.media_timeout_ms ?? 300000),
    loop: resolved.loop,
    autoStart: resolved.auto_start,
  }
}

/**
 * 把表单草稿收敛为可提交的放映配置，保证范围合法且 none 动画提交 0ms。
 * @param draft 表单草稿
 */
export function normalizeSlideshowDraft(draft: SlideshowDraft): SlideshowSettings {
  const durationMs = draft.effect === 'none'
    ? 0
    : clampMilliseconds(
      parseSecondsToMilliseconds(draft.durationSeconds),
      TRANSITION_DURATION_MIN_MS,
      TRANSITION_DURATION_MAX_MS,
      DEFAULT_SLIDESHOW_SETTINGS.transition.duration_ms,
    )
  const delayMs = clampMilliseconds(
    parseSecondsToMilliseconds(draft.delaySeconds),
    ADVANCE_DELAY_MIN_MS,
    ADVANCE_DELAY_MAX_MS,
    DEFAULT_SLIDESHOW_SETTINGS.advance.delay_ms,
  )
  const mediaTimeoutMs = clampMilliseconds(
    draft.mediaTimeoutSeconds === undefined ? null : parseSecondsToMilliseconds(draft.mediaTimeoutSeconds),
    MEDIA_TIMEOUT_MIN_MS,
    MEDIA_TIMEOUT_MAX_MS,
    DEFAULT_SLIDESHOW_SETTINGS.advance.media_timeout_ms ?? 300000,
  )
  return {
    transition: { effect: draft.effect, duration_ms: durationMs },
    advance: { mode: draft.advanceMode, delay_ms: delayMs, media_timeout_ms: mediaTimeoutMs },
    loop: draft.loop,
    auto_start: draft.autoStart,
  }
}

/**
 * 将毫秒值收敛到指定范围；非法输入使用兜底值。
 */
function clampMilliseconds(value: number | null, min: number, max: number, fallback: number): number {
  if (value === null) {
    return fallback
  }
  return Math.min(max, Math.max(min, value))
}
