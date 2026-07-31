/**
 * 文件功能：验证放大编辑弹窗的内容实时同步、JSON 回退格式化与错误提示展示。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import CodeZoomEditDialog from '@/components/editor/CodeZoomEditDialog.vue'

const monacoStub = defineComponent({
  name: 'MonacoCodeEditor',
  props: {
    modelValue: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () => h('textarea', {
      'aria-label': 'zoom-monaco-editor',
      value: props.modelValue,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLTextAreaElement).value),
    })
  },
})

/** 渲染放大编辑弹窗并返回事件记录。 */
function renderDialog(props: Partial<InstanceType<typeof CodeZoomEditDialog>['$props']> = {}) {
  return render(CodeZoomEditDialog, {
    props: {
      open: true,
      modelValue: '{"a":1}',
      title: '放大编辑：结构化数据',
      language: 'json',
      ...props,
    },
    global: {
      stubs: {
        MonacoCodeEditor: monacoStub,
      },
    },
  })
}

describe('CodeZoomEditDialog', () => {
  it('应展示标题与内容，并把编辑实时同步给父层', async () => {
    const { emitted } = renderDialog()

    expect(screen.getByText('放大编辑：结构化数据')).toBeInTheDocument()
    const editor = screen.getByLabelText('zoom-monaco-editor') as HTMLTextAreaElement
    expect(editor.value).toBe('{"a":1}')

    await fireEvent.update(editor, '{"a":2}')
    const updates = emitted('update:modelValue') as Array<[string]> | undefined
    expect(updates?.at(-1)).toEqual(['{"a":2}'])
  })

  it('Monaco 动作不可用时，格式化按钮应对 JSON 做两空格重序列化', async () => {
    const { emitted } = renderDialog({ modelValue: '{"a":1,"b":[1,2]}' })

    await fireEvent.click(screen.getByRole('button', { name: /格式化/ }))
    const updates = emitted('update:modelValue') as Array<[string]> | undefined
    expect(updates?.at(-1)).toEqual([JSON.stringify({ a: 1, b: [1, 2] }, null, 2)])
  })

  it('非法 JSON 点击格式化不应改写内容，并展示父层错误', async () => {
    const { emitted } = renderDialog({ modelValue: '{bad json', error: 'JSON 格式不合法。' })

    await fireEvent.click(screen.getByRole('button', { name: /格式化/ }))
    expect(emitted('update:modelValue')).toBeUndefined()
    expect(screen.getByText('JSON 格式不合法。')).toBeInTheDocument()
  })
})
