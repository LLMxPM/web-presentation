/**
 * 文件用途：验证 Runtime 全局 Tailwind safelist 覆盖页面和组件常用设计系统类。
 */

import { describe, expect, it } from 'vitest'

import { runtimeTailwindSafelist } from './runtime-safelist.js'

describe('runtime tailwind safelist', () => {
  it('应覆盖主题、背景、渐变和画布布局常用类', () => {
    expect(runtimeTailwindSafelist).toEqual(
      expect.arrayContaining([
        'relative',
        'size-4',
        'h-full',
        'w-full',
        'overflow-hidden',
        'pt-16',
        'bg-cover',
        'bg-center',
        'bg-no-repeat',
        'text-primary',
        'text-5xl',
        'align-middle',
        'text-secondary',
        'text-invert',
        'bg-background',
        'bg-background-subtle',
        'bg-background-invert',
        'border-border',
        'from-background-invert/80',
        'bg-accent1-100',
        'text-red-300',
        'text-red-900',
        'bg-slate-100',
        'border-blue-600',
        'border-dashed',
        'border-2',
        'from-emerald-400',
        'text-red-300/80',
      ]),
    )
  })

  it('不应把 Editor 或未声明的语义颜色混入 Runtime safelist', () => {
    expect(runtimeTailwindSafelist).not.toContain('bg-surface')
    expect(runtimeTailwindSafelist).not.toContain('text-muted')
    expect(runtimeTailwindSafelist.some(candidate => String(candidate).includes('tertiary'))).toBe(false)
  })
})
