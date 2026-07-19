/**
 * 文件功能：验证结构化富文本解析、序列化与锁定标签骨架裁剪规则。
 */

import { describe, expect, it } from 'vitest'

import {
  isPageVisualEditRichTextLockedStructurePruning,
  normalizePageVisualEditRichText,
} from '@/utils/page-visual-edit-rich-text'

describe('page visual edit rich text utils', () => {
  it('应保留复杂标签外壳，并规范 classless 语义标签、换行和危险文本', () => {
    expect(normalizePageVisualEditRichText(
      '<a href="/docs" :class="tone"><Badge style="color:red">链接</Badge></a><strong>重点</strong><br>{{值}}',
    )).toBe(
      '<a href="/docs" :class="tone"><Badge style="color:red">链接</Badge></a><strong>重点</strong><br>&#123;&#123;值&#125;&#125;',
    )
  })

  it('候选可移除锁定外壳并提升内容，但不能修改或重挂剩余标签', () => {
    const baseline = '<span class="outer"><strong class="inner">重点</strong></span><em class="tail">结尾</em>'

    expect(isPageVisualEditRichTextLockedStructurePruning(
      baseline,
      '<span class="outer"><strong class="inner"><em>新重点</em></strong></span>',
    )).toBe(true)
    expect(isPageVisualEditRichTextLockedStructurePruning(baseline, '<em class="tail">结尾</em>')).toBe(true)
    expect(isPageVisualEditRichTextLockedStructurePruning(baseline, '普通文本')).toBe(true)
    expect(isPageVisualEditRichTextLockedStructurePruning(
      baseline,
      '<strong class="inner">重点</strong><em class="tail">结尾</em>',
    )).toBe(true)
    expect(isPageVisualEditRichTextLockedStructurePruning(
      baseline,
      '<span class="changed"><strong class="inner">重点</strong></span><em class="tail">结尾</em>',
    )).toBe(false)
    expect(isPageVisualEditRichTextLockedStructurePruning(
      baseline,
      '<strong class="inner"><span class="outer">重点</span></strong><em class="tail">结尾</em>',
    )).toBe(false)
  })
})
