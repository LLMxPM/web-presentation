/**
 * 文件用途：验证 Tailwind visual catalog 的版本、互斥组和 Runtime safelist 子集约束。
 */

import { describe, expect, it } from 'vitest'

import { runtimeTailwindSafelist } from '../../tailwind/runtime-safelist.js'
import { findVisualTailwindGroup, runtimeVisualTailwindCatalog } from './catalog'

describe('runtime visual Tailwind catalog', () => {
  it('所有可选类都应来自 Runtime safelist，且组和类不重复', () => {
    const safelist = new Set(runtimeTailwindSafelist.filter(candidate => typeof candidate === 'string'))
    const groupKeys = runtimeVisualTailwindCatalog.groups.map(group => group.key)
    const catalogClasses = runtimeVisualTailwindCatalog.groups.flatMap(group => (
      group.options.map(option => option.className)
    ))

    expect(runtimeVisualTailwindCatalog.version).toBe(1)
    expect(new Set(groupKeys).size).toBe(groupKeys.length)
    expect(new Set(catalogClasses).size).toBe(catalogClasses.length)
    expect(catalogClasses.every(className => safelist.has(className))).toBe(true)
  })

  it('所有可见选项必须使用中文语义标签，不直接展示 Tailwind className', () => {
    const options = runtimeVisualTailwindCatalog.groups.flatMap(group => group.options)

    expect(options.every(option => option.label !== option.className)).toBe(true)
    expect(options.every(option => /[\u3400-\u9fff]/.test(option.label))).toBe(true)
  })

  it('应提供常用互斥组，但不接受 variant、任意值或未知类', () => {
    expect(findVisualTailwindGroup('display')?.options.map(option => option.className)).toContain('flex')
    expect(findVisualTailwindGroup('padding-x')?.options.map(option => option.className)).toContain('px-4')
    expect(findVisualTailwindGroup('text-color')?.options.map(option => option.className)).toContain('text-primary')

    const catalogClasses = new Set(
      runtimeVisualTailwindCatalog.groups.flatMap(group => group.options.map(option => option.className)),
    )
    expect(catalogClasses.has('hover:bg-blue-500')).toBe(false)
    expect(catalogClasses.has('w-[123px]')).toBe(false)
    expect(catalogClasses.has('unknown-class')).toBe(false)
    expect(findVisualTailwindGroup('display')?.options.find(option => option.className === 'flex')?.label).toBe('弹性布局')
    expect(findVisualTailwindGroup('width')?.options.find(option => option.className === 'w-full')?.label).toBe('占满宽度')
    expect(findVisualTailwindGroup('text-color')?.options.find(option => option.className === 'text-primary')?.label)
      .toBe('主题主色')
  })
})
