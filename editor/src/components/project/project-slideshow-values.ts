/** 文件功能：以生成 DTO 为准转换 schema 4 放映草稿、范围与摘要，项目/单页/批量表单共用。 */
import type { SlideshowCapabilities, SlideshowSettings } from '@/types/api'

export type SlideshowEffect = SlideshowSettings['transition']['effect']
export type SlideshowAdvanceMode = SlideshowSettings['advance']['mode']
export const ADVANCE_MODE_LABELS: Record<SlideshowAdvanceMode, string> = { manual: '手动翻页', timer: '定时翻页', scene_end: '本页完成后翻页' }
export const TRANSITION_EFFECT_LABELS: Record<SlideshowEffect, string> = { none: '无动画', fade: '淡入淡出', push: '推入' }
export const TRANSITION_EFFECT_OPTIONS = (['fade', 'push', 'none'] as const).map(value => ({ value, label: TRANSITION_EFFECT_LABELS[value] }))
export const DEFAULT_SLIDESHOW_SETTINGS: SlideshowSettings = { transition: { effect: 'fade', duration_ms: 400 }, advance: { mode: 'manual', delay_ms: 5000, completion_delay_ms: 300 }, loop: false }
export const TRANSITION_DURATION_MIN_MS = 100, TRANSITION_DURATION_MAX_MS = 2000
export const ADVANCE_DELAY_MIN_MS = 1000, ADVANCE_DELAY_MAX_MS = 3_600_000
export const COMPLETION_DELAY_MIN_MS = 0, COMPLETION_DELAY_MAX_MS = 3_600_000

export interface SlideshowDraft {
  effect: SlideshowEffect
  durationSeconds: string
  advanceMode: SlideshowAdvanceMode
  delaySeconds: string
  completionDelaySeconds: string
  loop: boolean
}

/** 实时能力目录必须声明 schema 4 的实际完成模式，未知旧服务不显示该选项。 */
export function isSceneEndAdvanceAvailable(capabilities?: SlideshowCapabilities | null): boolean {
  return Boolean(capabilities && capabilities.schema_version === 4 && capabilities.advance_modes.includes('scene_end'))
}
/** 项目与路由表单使用相同模式集合，不再提供旧媒体/时间轴选项。 */
export function buildAdvanceModeOptions(capabilities?: SlideshowCapabilities | null): Array<{ label: string; value: SlideshowAdvanceMode }> {
  const modes: SlideshowAdvanceMode[] = ['manual', 'timer']
  if (isSceneEndAdvanceAvailable(capabilities)) modes.push('scene_end')
  return modes.map(value => ({ value, label: ADVANCE_MODE_LABELS[value] }))
}
/** 毫秒转换为无冗余小数的秒字符串。 */
export function formatMillisecondsAsSeconds(value: number): string { return (value / 1000).toFixed(3).replace(/\.?0+$/, '') }
/** 只接受完整有限的非负秒值，空值和夹带文字不能部分解析。 */
export function parseSecondsToMilliseconds(value: string): number | null {
  const text = String(value ?? '').trim(), number = Number(text)
  return text && Number.isFinite(number) && number >= 0 ? Math.round(number * 1000) : null
}
/** API 值转为表单草稿，未配置时使用当前版本默认值。 */
export function createSlideshowDraft(settings: SlideshowSettings | null | undefined = DEFAULT_SLIDESHOW_SETTINGS): SlideshowDraft {
  const value = settings ?? DEFAULT_SLIDESHOW_SETTINGS
  return { effect: value.transition.effect, durationSeconds: formatMillisecondsAsSeconds(value.transition.duration_ms), advanceMode: value.advance.mode,
    delaySeconds: formatMillisecondsAsSeconds(value.advance.delay_ms), completionDelaySeconds: formatMillisecondsAsSeconds(value.advance.completion_delay_ms ?? 300), loop: value.loop }
}
/** 表单提交时收敛范围；完成后停留允许零，定时停留至少一秒。 */
export function normalizeSlideshowDraft(draft: SlideshowDraft): SlideshowSettings {
  return { transition: { effect: draft.effect, duration_ms: draft.effect === 'none' ? 0 : clamp(parseSecondsToMilliseconds(draft.durationSeconds), 100, 2000, 400) },
    advance: { mode: draft.advanceMode, delay_ms: clamp(parseSecondsToMilliseconds(draft.delaySeconds), 1000, 3_600_000, 5000),
      completion_delay_ms: clamp(parseSecondsToMilliseconds(draft.completionDelaySeconds), 0, 3_600_000, 300) }, loop: draft.loop }
}
/** 共享摘要描述真实完成后的停留，不预估 Scene 的结束时刻。 */
export function formatSlideshowAdvance(advance: SlideshowSettings['advance']): string {
  const label = ADVANCE_MODE_LABELS[advance.mode]
  return advance.mode === 'manual' ? label : advance.mode === 'scene_end' ? `${label}，完成后停留 ${formatMillisecondsAsSeconds(advance.completion_delay_ms ?? 300)} 秒` : `${label} ${formatMillisecondsAsSeconds(advance.delay_ms)} 秒`
}
/** 非法输入使用契约默认，有限输入限制在当前字段范围内。 */
function clamp(value: number | null, min: number, max: number, fallback: number): number { return value === null ? fallback : Math.min(max, Math.max(min, value)) }
