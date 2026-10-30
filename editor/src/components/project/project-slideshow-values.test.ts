/** 文件功能：验证 schema 4 草稿往返、秒值边界、能力选项与旧字段清除。 */
import { expect, it } from 'vitest'
import { createSlideshowDraft, normalizeSlideshowDraft, DEFAULT_SLIDESHOW_SETTINGS, buildAdvanceModeOptions, parseSecondsToMilliseconds, formatSlideshowAdvance } from './project-slideshow-values'
import { sceneCapabilities } from '@/test/slideshow-helpers'

it('默认完整往返且无 auto_start 或旧预算', () => {
  expect(normalizeSlideshowDraft(createSlideshowDraft())).toEqual(DEFAULT_SLIDESHOW_SETTINGS)
  expect(normalizeSlideshowDraft(createSlideshowDraft())).not.toHaveProperty('auto_start')
  const draft = createSlideshowDraft({ transition: { effect: 'push', duration_ms: 650 }, advance: { mode: 'scene_end', delay_ms: 5000, completion_delay_ms: 450 }, loop: true })
  expect(draft).toMatchObject({ durationSeconds: '0.65', completionDelaySeconds: '0.45' })
  expect(normalizeSlideshowDraft(draft).advance).toEqual({ mode: 'scene_end', delay_ms: 5000, completion_delay_ms: 450 })
})

it.each([['0', 0], ['0.1235', 124], ['99999', 3600000], ['oops', 300], ['-1', 300]])('完成后停留 %s 收敛为 %s 毫秒', (input, output) => {
  const value = normalizeSlideshowDraft({ ...createSlideshowDraft(), advanceMode: 'scene_end', completionDelaySeconds: String(input) })
  expect(value.advance.completion_delay_ms).toBe(output)
})

it('定时停留和动画范围独立，未使用字段也保持完整结构', () => {
  const draft = { ...createSlideshowDraft(), advanceMode: 'timer' as const, delaySeconds: '0', durationSeconds: '99' }
  expect(normalizeSlideshowDraft(draft)).toMatchObject({ transition: { duration_ms: 2000 }, advance: { delay_ms: 1000, completion_delay_ms: 300 } })
  expect(normalizeSlideshowDraft({ ...draft, effect: 'none' }).transition.duration_ms).toBe(0)
  expect(parseSecondsToMilliseconds('3abc')).toBeNull(); expect(parseSecondsToMilliseconds('')).toBeNull()
})

it('Scene 选项要求当前版本声明，摘要不会预估任务完成时间', () => {
  expect(buildAdvanceModeOptions(sceneCapabilities).map(item => item.value)).toEqual(['manual', 'timer', 'scene_end'])
  expect(buildAdvanceModeOptions({ ...sceneCapabilities, schema_version: 3 }).map(item => item.value)).toEqual(['manual', 'timer'])
  expect(formatSlideshowAdvance({ mode: 'scene_end', delay_ms: 5000, completion_delay_ms: 0 })).toContain('完成后停留 0 秒')
})
