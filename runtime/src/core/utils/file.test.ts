/**
 * 文件用途：验证文件下载工具中的默认文件名、时间格式与非法字符清理规则。
 */

import { describe, expect, it } from 'vitest'
import {
  formatLocalFilenameTimestamp,
  generateFilename,
  sanitizeFilenameBase,
} from './file'

describe('file utils', () => {
  it('应使用用户本地时区字段格式化文件名时间', () => {
    const localDate = new Date(2026, 3, 26, 9, 8, 7)

    expect(formatLocalFilenameTimestamp(localDate)).toBe('2026-04-26_09-08-07')
  })

  it('应生成标题加本地时间的安全默认文件名', () => {
    const localDate = new Date(2026, 3, 26, 9, 8, 7)

    expect(generateFilename(undefined, '项目:标题/页面*-{timestamp}', true, '.pdf', localDate))
      .toBe('项目-标题-页面-2026-04-26_09-08-07.pdf')
  })

  it('应保留自定义文件名并补齐扩展名', () => {
    expect(generateFilename('自定义文件')).toBe('自定义文件.pdf')
    expect(generateFilename('自定义文件.pdf')).toBe('自定义文件.pdf')
  })

  it('应清理默认文件名主体中的系统非法字符', () => {
    expect(sanitizeFilenameBase('  项目<>:"/\\|?* 标题  '))
      .toBe('项目- 标题')
  })

  it('默认模板清理为空时应回退到 export', () => {
    expect(generateFilename(undefined, '<>:"/\\|?*', true, '.pdf', new Date(2026, 3, 26, 9, 8, 7)))
      .toBe('export.pdf')
  })
})
