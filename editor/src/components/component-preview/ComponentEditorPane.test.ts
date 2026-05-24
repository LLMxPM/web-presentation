/**
 * 文件功能：验证组件编辑面板的表单回写、主题切换和操作事件。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import ComponentEditorPane from '@/components/component-preview/ComponentEditorPane.vue'
import type { WorkspaceComponentDraftErrors, WorkspaceComponentDraftForm } from '@/composables/useWorkspaceComponentDraft'

const form: WorkspaceComponentDraftForm = {
  name: '销售卡片',
  import_name: 'SalesCard',
  component_type: '内容区块',
  summary: '销售数据展示组件',
  status: 'active',
  content: '<template><div /></template>',
  preview_schema: '',
}

const errors: WorkspaceComponentDraftErrors = {
  name: '',
  import_name: '',
  component_type: '',
  content: '',
  preview_schema: '',
}

describe('ComponentEditorPane', () => {
  it('应回写表单字段并触发预览、保存、发布和主题切换事件', async () => {
    const { emitted } = render(ComponentEditorPane, {
      props: {
        form,
        errors,
        mode: 'edit',
        editorTheme: 'light',
        saving: false,
        previewLoading: false,
        canPublish: true,
        canViewHistory: true,
      },
      global: {
        stubs: {
          MonacoCodeEditor: defineComponent({
            name: 'MonacoCodeEditor',
            props: {
              modelValue: { type: String, default: '' },
            },
            emits: ['update:modelValue'],
            setup(props, { emit }) {
              return () => h('textarea', {
                'aria-label': 'monaco-editor',
                value: props.modelValue,
                onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLTextAreaElement).value),
              })
            },
          }),
          SearchableSelect: true,
        },
      },
    })

    await fireEvent.update(screen.getByPlaceholderText('如：数据统计卡片'), '销售趋势卡片')
    await fireEvent.update(screen.getByPlaceholderText('如：SalesMetricCard'), 'SalesTrendCard')
    await fireEvent.click(screen.getByRole('button', { name: '暗黑' }))
    await fireEvent.click(screen.getByRole('button', { name: '发布历史' }))
    await fireEvent.click(screen.getByRole('button', { name: '预览当前草稿' }))
    await fireEvent.click(screen.getByRole('button', { name: '保存草稿' }))
    await fireEvent.click(screen.getByRole('button', { name: '发布版本' }))

    const formEvents = emitted('update:form') as Array<[WorkspaceComponentDraftForm]> | undefined
    const themeEvents = emitted('update:editorTheme') as Array<['dark']> | undefined
    expect(formEvents?.[0]?.[0]).toMatchObject({ name: '销售趋势卡片' })
    expect(formEvents?.[1]?.[0]).toMatchObject({ import_name: 'SalesTrendCard' })
    expect(themeEvents?.[0]).toEqual(['dark'])
    expect(emitted('open-version-history')).toHaveLength(1)
    expect(emitted('preview-draft')).toHaveLength(1)
    expect(emitted('save-draft')).toHaveLength(1)
    expect(emitted('publish')).toHaveLength(1)
  })

  it('新建模式不应展示发布按钮', () => {
    render(ComponentEditorPane, {
      props: {
        form,
        errors,
        mode: 'create',
        editorTheme: 'light',
        saving: false,
        previewLoading: false,
        canPublish: false,
      },
      global: {
        stubs: {
          MonacoCodeEditor: true,
          SearchableSelect: true,
        },
      },
    })

    expect(screen.getByRole('button', { name: '创建草稿' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '发布版本' })).toBeNull()
    expect(screen.queryByRole('button', { name: '发布历史' })).toBeNull()
  })
})
