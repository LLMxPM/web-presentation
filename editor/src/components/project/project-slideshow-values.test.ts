/** 文件功能：验证放映表单草稿与毫秒配置的转换、范围收敛和无动画 0ms 语义。 */
import { describe, expect, it } from 'vitest'

import type { SlideshowCapabilities } from '@/types/api'
import {
  buildAdvanceModeOptions,
  createSlideshowDraft,
  formatMillisecondsAsSeconds,
  isMediaEndAdvanceAvailable,
  normalizeSlideshowDraft,
  parseSecondsToMilliseconds,
} from './project-slideshow-values'

const capabilities: SlideshowCapabilities = {
  schema_version: 2,
  transition_effects: ['none', 'fade', 'push'],
  advance_modes: ['manual', 'timer', 'media_end'],
  single_window_auto_play: true,
  presenter_auto_play: false,
  capture_auto_play: false,
  transition_duration_ms: { min: 100, max: 2000, none: 0 },
  delay_ms: { min: 1000, max: 3600000 },
  media_timeout_ms: { min: 1000, max: 3600000 },
}

describe('project slideshow values', () => {
  it('应把毫秒配置转换为秒草稿并保留合法值', () => {
    const draft = createSlideshowDraft({
      transition: { effect: 'push', duration_ms: 650 },
      advance: { mode: 'timer', delay_ms: 8000 },
      loop: true,
      auto_start: false,
    })

    expect(draft).toEqual({
      effect: 'push',
      durationSeconds: '0.65',
      advanceMode: 'timer',
      delaySeconds: '8',
      mediaTimeoutSeconds: '300',
      loop: true,
      autoStart: false,
    })
  })

  it('应把小数秒四舍五入为整数毫秒', () => {
    expect(parseSecondsToMilliseconds('0.3004')).toBe(300)
    expect(parseSecondsToMilliseconds(' 12.5 ')).toBe(12500)
    expect(parseSecondsToMilliseconds('abc')).toBeNull()
    expect(parseSecondsToMilliseconds('-1')).toBeNull()
    expect(formatMillisecondsAsSeconds(650)).toBe('0.65')
    expect(formatMillisecondsAsSeconds(1000)).toBe('1')
  })

  it('无动画时必须提交 0ms，其它效果收敛到 100–2000ms', () => {
    expect(normalizeSlideshowDraft({
      effect: 'none',
      durationSeconds: '0.8',
      advanceMode: 'manual',
      delaySeconds: '5',
      loop: false,
      autoStart: false,
    }).transition).toEqual({ effect: 'none', duration_ms: 0 })

    expect(normalizeSlideshowDraft({
      effect: 'fade',
      durationSeconds: '0.01',
      advanceMode: 'manual',
      delaySeconds: '5',
      loop: false,
      autoStart: false,
    }).transition.duration_ms).toBe(100)

    expect(normalizeSlideshowDraft({
      effect: 'push',
      durationSeconds: '9',
      advanceMode: 'manual',
      delaySeconds: '5',
      loop: false,
      autoStart: false,
    }).transition.duration_ms).toBe(2000)
  })

  it('停留时长应收敛到 1000–3600000ms 并对非法输入使用兜底值', () => {
    const base = {
      effect: 'fade' as const,
      durationSeconds: '0.4',
      advanceMode: 'timer' as const,
      loop: false,
      autoStart: false,
    }

    expect(normalizeSlideshowDraft({ ...base, delaySeconds: '0.2' }).advance.delay_ms).toBe(1000)
    expect(normalizeSlideshowDraft({ ...base, delaySeconds: '9999' }).advance.delay_ms).toBe(3600000)
    expect(normalizeSlideshowDraft({ ...base, delaySeconds: 'oops' }).advance.delay_ms).toBe(5000)
    expect(normalizeSlideshowDraft({ ...base, delaySeconds: '' }).advance.delay_ms).toBe(5000)
  })

  it('媒体结束超时应保留合法值并收敛到 1000–3600000ms', () => {
    const base = {
      effect: 'fade' as const,
      durationSeconds: '0.4',
      advanceMode: 'timer' as const,
      delaySeconds: '5',
      loop: false,
      autoStart: false,
    }

    expect(normalizeSlideshowDraft({ ...base, mediaTimeoutSeconds: '120' }).advance.media_timeout_ms).toBe(120000)
    expect(normalizeSlideshowDraft({ ...base, mediaTimeoutSeconds: '0.2' }).advance.media_timeout_ms).toBe(1000)
    expect(normalizeSlideshowDraft({ ...base, mediaTimeoutSeconds: '9999' }).advance.media_timeout_ms).toBe(3600000)
    expect(normalizeSlideshowDraft({ ...base, mediaTimeoutSeconds: 'oops' }).advance.media_timeout_ms).toBe(300000)
  })

  it('媒体结束模式应提交完整 advance 对象并保留等待上限', () => {
    const settings = normalizeSlideshowDraft({
      effect: 'fade',
      durationSeconds: '0.4',
      advanceMode: 'media_end',
      delaySeconds: '6',
      mediaTimeoutSeconds: '120',
      loop: false,
      autoStart: false,
    })

    expect(settings.advance).toEqual({ mode: 'media_end', delay_ms: 6000, media_timeout_ms: 120000 })
  })

  it('翻页模式选项应只包含服务端已声明的模式', () => {
    expect(buildAdvanceModeOptions(null).map(option => option.value)).toEqual(['manual', 'timer'])
    expect(isMediaEndAdvanceAvailable(null)).toBe(false)
    expect(buildAdvanceModeOptions(capabilities).map(option => option.value)).toEqual(['manual', 'timer', 'media_end'])
    expect(isMediaEndAdvanceAvailable(capabilities)).toBe(true)
    expect(isMediaEndAdvanceAvailable({ ...capabilities, advance_modes: ['manual', 'timer'] })).toBe(false)
  })
})
