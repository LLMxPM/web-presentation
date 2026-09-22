/**
 * 文件用途：校验图标颜色解析工具，确保主题色可被稳定转换为可用于 SVG 内联样式的颜色值。
 */
import { describe, expect, it } from 'vitest'
import { resolveColor } from './colorResolver'

describe('runtime color resolver', () => {
  it('返回基础主题色对应的 CSS 变量', () => {
    expect(resolveColor('text-primary')).toBe('var(--tw-color-text-primary)')
    expect(resolveColor(' accent1 ')).toBe('var(--tw-color-accent1)')
  })

  it('返回浅色阶对应的 color-mix 表达式', () => {
    expect(resolveColor('accent1-300')).toBe(
      'color-mix(in srgb, var(--tw-color-accent1) 50%, white)',
    )
  })

  it('返回深色阶对应的 color-mix 表达式', () => {
    expect(resolveColor('text-accent2-700')).toBe(
      'color-mix(in srgb, var(--tw-color-accent2) 70%, black)',
    )
  })

  it('保留原始颜色值', () => {
    expect(resolveColor('#2563eb')).toBe('#2563eb')
    expect(resolveColor('var(--custom-color)')).toBe('var(--custom-color)')
  })
})
