/** 文件功能：验证过渡配置默认值、覆盖、关闭与非法配置降级。 */
import { describe, expect, it, vi } from 'vitest'
import { resolvePageAdvance, resolvePageTransition } from './page-transition'

describe('过渡配置', () => {
  it('缺省采用淡化400ms，空覆盖继承项目配置', () => {
    expect(resolvePageTransition(undefined)).toEqual({ effect: 'fade', durationMs: 400 })
    expect(resolvePageTransition(null, { effect: 'push', durationMs: 600 })).toEqual({ effect: 'push', durationMs: 600 })
  })
  it('覆盖对象不逐字段继承，关闭忽略时长', () => {
    expect(resolvePageTransition({ effect: 'fade' }, { effect: 'push', durationMs: 600 })).toEqual({ effect: 'fade', durationMs: 400 })
    expect(resolvePageTransition({ effect: 'none', durationMs: -1 })).toEqual({ effect: 'none', durationMs: 0 })
  })
  it.each([{ effect: 'spin' }, { effect: 'push', durationMs: 99 }, { effect: 'fade', durationMs: 2001 }, { effect: 'fade', durationMs: '400' }])('非法配置回退且产生诊断：%j', value => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(resolvePageTransition(value, { effect: 'push', durationMs: 500 })).toEqual({ effect: 'push', durationMs: 500 })
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})

describe('翻页推进配置', () => {
  it('缺省手动、覆盖不逐字段继承，完成停留允许零', () => {
    expect(resolvePageAdvance(undefined)).toEqual({ mode: 'manual', delayMs: 5000, completionDelayMs: 300 })
    expect(resolvePageAdvance(null, { mode: 'timer', delayMs: 9000 })).toEqual({ mode: 'timer', delayMs: 9000, completionDelayMs: 300 })
    expect(resolvePageAdvance({ mode: 'scene_end', completionDelayMs: 0 })).toEqual({ mode: 'scene_end', delayMs: 5000, completionDelayMs: 0 })
  })
  it.each([
    { mode: 'media_end' }, { mode: 'timeline_end' }, { mode: 'timer', mediaTimeoutMs: 5000 },
    { mode: 'timer', timelineTimeoutMs: 5000 }, { mode: 'unknown' }, { mode: 'timer', delayMs: 999 },
    { mode: 'timer', delayMs: '5000' }, { mode: 'scene_end', completionDelayMs: -1 },
    { mode: 'scene_end', completionDelayMs: true }, { mode: 'timer', delayMs: 3600001 },
  ])('非法或旧配置明确拒绝：%j', value => {
    expect(() => resolvePageAdvance(value)).toThrow('schema 4')
  })
})
