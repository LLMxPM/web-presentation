/**
 * 文件功能：验证 Editor UI class 组合工具的条件处理与 Tailwind 冲突消解行为。
 */

import { describe, expect, it } from 'vitest'

import { cn } from '@/utils/class-names'

describe('cn', () => {
  it('应忽略空值并展开嵌套条件 class', () => {
    expect(cn('flex', false, ['items-center', { hidden: false, 'gap-2': true }], null))
      .toBe('flex items-center gap-2')
  })

  it('应保留调用方传入的同组 Tailwind class 作为最终结果', () => {
    expect(cn('h-control-sm bg-surface text-text-muted', 'h-control-md bg-accent text-text'))
      .toBe('h-control-md bg-accent text-text')
  })

  it('应支持状态变体中的冲突消解', () => {
    expect(cn('hover:bg-surface-hover focus:ring-1', 'hover:bg-accent-hover focus:ring-2'))
      .toBe('hover:bg-accent-hover focus:ring-2')
  })
})
