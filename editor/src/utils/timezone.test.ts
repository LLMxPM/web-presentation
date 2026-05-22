/**
 * 文件功能：验证前端业务时区工具在显式时区下生成稳定的日期片段。
 */

import { describe, expect, it } from 'vitest'

import { APP_TIMEZONE, getAppDateSegment } from '@/utils/timezone'

describe('app timezone utils', () => {
  it('应按业务时区生成稳定的日期片段', () => {
    const sourceValue = '2026-03-31T16:30:00.000Z'
    const parts = new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      timeZone: APP_TIMEZONE,
    }).formatToParts(new Date(sourceValue))

    const year = parts.find(part => part.type === 'year')?.value ?? ''
    const month = parts.find(part => part.type === 'month')?.value ?? ''
    const day = parts.find(part => part.type === 'day')?.value ?? ''
    expect(getAppDateSegment(sourceValue)).toBe(`${year}-${month}-${day}`)
  })
})
