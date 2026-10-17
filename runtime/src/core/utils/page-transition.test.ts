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
  it('缺省保持手动翻页，合法 timer 覆盖生效', () => {
    expect(resolvePageAdvance(undefined)).toEqual({ mode: 'manual', delayMs: 5000 })
    expect(resolvePageAdvance(null, { mode: 'manual', delayMs: 9000 })).toEqual({ mode: 'manual', delayMs: 9000 })
    expect(resolvePageAdvance({ mode: 'timer', delayMs: 8000 })).toEqual({ mode: 'timer', delayMs: 8000 })
  })
  it.each([
    { mode: 'media_end', delayMs: 5000 },
    { mode: 'timer', delayMs: 999 },
    { mode: 'timer', delayMs: 3600001 },
    { mode: 'timer', delayMs: '5000' },
  ])('非法配置回退并告警：%j', value => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(resolvePageAdvance(value)).toEqual({ mode: 'manual', delayMs: 5000 })
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})
