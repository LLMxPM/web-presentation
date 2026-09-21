/** 文件功能：验证旧时间补 UTC、跨时区展示与部署业务时区切换。 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { formatDateTime } from '@/utils/format'
import { APP_TIMEZONE, formatDateTimeInAppTimezone, getAppDateSegment, parseApiDate, setAppTimezone } from '@/utils/timezone'

const initialTimezone = APP_TIMEZONE

beforeEach(() => setAppTimezone('Asia/Shanghai'))
afterEach(() => setAppTimezone(initialTimezone))

describe('app timezone utils', () => {
  it.each([
    '2026-09-21T02:00:00',
    '2026-09-21 02:00:00',
    '2026-09-21T02:00',
    '2026-09-21T02:00:00.000000',
    '2026-09-21T02:00:00Z',
    '2026-09-21T02:00:00+00:00',
    '2026-09-21T10:00:00+08:00',
    '2026-09-20T22:00:00-04:00',
  ])('应将 %s 解析为同一时间点', (value) => {
    expect(parseApiDate(value).toISOString()).toBe('2026-09-21T02:00:00.000Z')
    expect(formatDateTimeInAppTimezone(value)).toBe('2026/9/21 10:00')
  })

  it('应保留毫秒、Date 对象和数字时间戳的时间点', () => {
    const date = new Date('2026-09-21T02:00:00.123Z')
    expect(parseApiDate('2026-09-21T02:00:00.123456').getTime()).toBe(date.getTime())
    expect(parseApiDate(date)).toBe(date)
    expect(parseApiDate(date.getTime()).getTime()).toBe(date.getTime())
  })

  it('应按业务时区跨日，并直接补齐旧时间的 UTC', () => {
    expect(getAppDateSegment('2026-03-31T16:30:00')).toBe('2026-04-01')
    expect(getAppDateSegment('2026-03-31T16:30:00Z')).toBe('2026-04-01')
  })

  it('应使用后端启动配置覆盖前端默认时区', () => {
    expect(getAppDateSegment('2026-09-21T15:30:00Z')).toBe('2026-09-21')
    setAppTimezone('Asia/Tokyo')
    expect(APP_TIMEZONE).toBe('Asia/Tokyo')
    expect(getAppDateSegment('2026-09-21T15:30:00Z')).toBe('2026-09-22')
    expect(formatDateTime('2026-09-21T15:30:00')).toBe('2026/9/22 00:30')
  })

  it('非法时区不得覆盖已有配置', () => {
    expect(() => setAppTimezone('Not/A_Timezone')).toThrow()
    expect(APP_TIMEZONE).toBe('Asia/Shanghai')
  })

  it('缺失或非法时间应显示占位符而非抛出渲染错误', () => {
    expect(formatDateTime(null)).toBe('-')
    expect(formatDateTime(undefined)).toBe('-')
    expect(formatDateTime('')).toBe('-')
    expect(formatDateTime('invalid-date')).toBe('-')
  })
})
