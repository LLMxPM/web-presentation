/**
 * 文件用途：验证 Runtime Tailwind 主题中的动态字号与默认行高比例。
 */

import { describe, expect, it } from 'vitest'

import { createDynamicFontSizeScale, runtimeTailwindTheme } from './runtime-tailwind-theme.js'

describe('runtime tailwind theme font size scale', () => {
  it('应按 Tailwind 默认比例生成字号与行高配置', () => {
    const fontSize = createDynamicFontSizeScale()

    expect(fontSize.base).toEqual([
      'var(--tw-font-size-base)',
      { lineHeight: 'calc(var(--tw-font-size-base) * 1.5)' },
    ])
    expect(fontSize.xl).toEqual([
      'calc(var(--tw-font-size-base) * 1.25)',
      { lineHeight: 'calc(var(--tw-font-size-base) * 1.75)' },
    ])
    expect(fontSize['4xl']).toEqual([
      'calc(var(--tw-font-size-base) * 2.25)',
      { lineHeight: 'calc(var(--tw-font-size-base) * 2.5)' },
    ])
    expect(fontSize['5xl']).toEqual([
      'calc(var(--tw-font-size-base) * 3)',
      { lineHeight: '1' },
    ])
  })

  it('应保持 Runtime 主题语义颜色、色阶和字体类映射', () => {
    const colors = runtimeTailwindTheme.extend?.colors as Record<string, unknown>
    const background = colors.background as Record<string, unknown>
    const border = colors.border as Record<string, unknown>
    const fontFamily = runtimeTailwindTheme.extend?.fontFamily as Record<string, unknown>

    expect(colors.primary).toHaveProperty('600')
    expect(colors.accent1).toHaveProperty('900')
    expect(background).toHaveProperty('DEFAULT')
    expect(background).toHaveProperty('subtle')
    expect(background).toHaveProperty('invert')
    expect(border).toHaveProperty('DEFAULT')
    expect(border).toHaveProperty('subtle')
    expect(fontFamily).toEqual(expect.objectContaining({
      heading: ['var(--tw-font-heading)', 'sans-serif'],
      body: ['var(--tw-font-body)', 'sans-serif'],
      code: ['var(--tw-font-code)', 'monospace'],
    }))
  })
})
