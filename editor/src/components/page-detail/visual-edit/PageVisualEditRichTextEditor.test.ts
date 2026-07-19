/**
 * 文件功能：验证结构化富文本编辑器的片段切分、样式锁定、语义选区和换行行为。
 */

import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import PageVisualEditRichTextEditor from '@/components/page-detail/visual-edit/PageVisualEditRichTextEditor.vue'

describe('PageVisualEditRichTextEditor', () => {
  it('应按嵌套标签展示片段，允许修改文本并移除锁定外壳保留内容', async () => {
    const baseline = '普通<span class="tone">锁定<strong class="weight">重点</strong></span><em>结尾</em>'
    const rendered = render(PageVisualEditRichTextEditor, {
      props: { modelValue: baseline, baselineHtml: baseline },
    })
    const textareas = screen.getAllByRole('textbox')

    expect(textareas.map(textarea => (textarea as HTMLTextAreaElement).value))
      .toEqual(['普通', '锁定', '重点', '结尾'])
    expect(screen.getAllByRole('button', { name: /查看样式锁定详情/ })).toHaveLength(2)
    expect(screen.queryByText('<span class="tone">')).toBeNull()
    await fireEvent.click(screen.getByRole('button', { name: '查看样式锁定详情 span' }))
    expect(screen.getByText('<span class="tone">')).toBeInTheDocument()

    await fireEvent.update(textareas[1]!, '新锁定')
    expect(rendered.emitted()['update:modelValue']?.at(-1)?.[0])
      .toBe('普通<span class="tone">新锁定<strong class="weight">重点</strong></span><em>结尾</em>')

    await fireEvent.click(screen.getByRole('button', { name: '删除锁定样式 span' }))
    expect(rendered.emitted()['update:modelValue']?.at(-1)?.[0])
      .toBe('普通新锁定<strong class="weight">重点</strong><em>结尾</em>')
  })

  it('删除锁定子节点样式后应把内容合并进父节点文本入口', async () => {
    const baseline = '<span class="outer"><strong class="inner">内容</strong></span>'
    const rendered = render(PageVisualEditRichTextEditor, {
      props: { modelValue: baseline, baselineHtml: baseline },
    })

    await fireEvent.click(screen.getByRole('button', { name: '删除锁定样式 strong' }))

    expect(rendered.emitted()['update:modelValue']?.at(-1)?.[0]).toBe('<span class="outer">内容</span>')
    expect(screen.getByRole('textbox')).toHaveValue('内容')
  })

  it('删除锁定样式后应保留内部内容，并与前后普通文本合并', async () => {
    const baseline = '前文<span class="locked">删除内容</span>后文'
    const rendered = render(PageVisualEditRichTextEditor, {
      props: { modelValue: baseline, baselineHtml: baseline },
    })

    await fireEvent.click(screen.getByRole('button', { name: '删除锁定样式 span' }))

    expect(rendered.emitted()['update:modelValue']?.at(-1)?.[0]).toBe('前文删除内容后文')
    expect(screen.getAllByRole('textbox')).toHaveLength(1)
    expect(screen.getByRole('textbox')).toHaveValue('前文删除内容后文')
  })

  it('链接、组件、动态属性和内联样式仅锁定外壳，全部静态文本仍可编辑', async () => {
    const baseline = '普通<a href="/docs" :class="tone">链接<Badge :level="level">组件文本</Badge></a><em style="color:red">强调</em>'
    const rendered = render(PageVisualEditRichTextEditor, {
      props: { modelValue: baseline, baselineHtml: baseline },
    })
    const textareas = screen.getAllByRole('textbox')

    expect(textareas.map(textarea => (textarea as HTMLTextAreaElement).value))
      .toEqual(['普通', '链接', '组件文本', '强调'])
    expect(screen.getAllByText('样式锁定')).toHaveLength(3)
    expect(screen.queryByText('<a href="/docs" :class="tone">')).toBeNull()

    await fireEvent.click(screen.getByRole('button', { name: '查看样式锁定详情 a' }))
    expect(screen.getByText('<a href="/docs" :class="tone">')).toBeInTheDocument()
    await fireEvent.update(textareas[2]!, '新组件文本')

    expect(rendered.emitted()['update:modelValue']?.at(-1)?.[0]).toBe(
      '普通<a href="/docs" :class="tone">链接<Badge :level="level">新组件文本</Badge></a><em style="color:red">强调</em>',
    )
  })

  it('应把文本框换行转成 br，并把粘贴的标签按纯文本转义', async () => {
    const rendered = render(PageVisualEditRichTextEditor, { props: { modelValue: '原文' } })
    const textarea = screen.getByRole('textbox')

    await fireEvent.update(textarea, '<script>bad()</script>\n下一行')

    expect(rendered.emitted()['update:modelValue']?.at(-1)?.[0])
      .toBe('&lt;script&gt;bad()&lt;/script&gt;<br>下一行')
  })

  it('仅允许把单个文本片段的非空选区包装成 strong/em', async () => {
    const rendered = render(PageVisualEditRichTextEditor, { props: { modelValue: '普通重点' } })
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    const boldButton = screen.getByRole('button', { name: '加粗所选文本' })

    expect(boldButton).toBeDisabled()
    textarea.setSelectionRange(2, 4)
    await fireEvent.select(textarea)
    expect(boldButton).toBeEnabled()
    await fireEvent.mouseDown(boldButton)

    expect(rendered.emitted()['update:modelValue']?.at(-1)?.[0]).toBe('普通<strong>重点</strong>')
    expect(screen.getByRole('button', { name: '取消加粗 strong' })).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '取消加粗 strong' }))
    expect(rendered.emitted()['update:modelValue']?.at(-1)?.[0]).toBe('普通重点')
    expect(screen.getAllByRole('textbox')).toHaveLength(1)
    expect(screen.getByRole('textbox')).toHaveValue('普通重点')
  })

  it('classless strong/em 可取消标签，锁定结构异常时恢复基准值', async () => {
    const rendered = render(PageVisualEditRichTextEditor, {
      props: {
        modelValue: '<span class="changed">内容</span><em>强调</em>',
        baselineHtml: '<span class="locked">内容</span><em>强调</em>',
      },
    })

    expect(screen.getByText(/已恢复为基准内容/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查看样式锁定详情 span' })).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '取消强调 em' }))
    expect(rendered.emitted()['update:modelValue']?.at(-1)?.[0])
      .toBe('<span class="locked">内容</span>强调')
  })

  it('超过长度限制时保留本地输入但不发出草稿', async () => {
    const rendered = render(PageVisualEditRichTextEditor, { props: { modelValue: '' } })
    const textarea = screen.getByRole('textbox')

    await fireEvent.update(textarea, 'x'.repeat(20_001))

    expect(screen.getByText(/超过 20000 字符限制/)).toBeInTheDocument()
    expect((textarea as HTMLTextAreaElement).value).toHaveLength(20_001)
    expect(rendered.emitted()['update:modelValue']).toBeUndefined()
  })
})
