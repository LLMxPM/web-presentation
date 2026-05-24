/**
 * 文件功能：验证工作空间组件工作台在同 ID 组件状态更新时重新载入草稿并刷新预览。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import WorkspaceComponentWorkbench from '@/components/component-preview/WorkspaceComponentWorkbench.vue'
import type { WorkspaceComponentItem } from '@/types/api'

const baseComponent: WorkspaceComponentItem = {
  id: 99,
  workspace_id: 11,
  workspace_name: '默认工作空间',
  code: 'CMP099',
  name: '销售卡片',
  import_name: 'SalesCard',
  component_type: '内容区块',
  summary: '销售数据展示组件',
  status: 'active',
  content: '<template><div>old</div></template>',
  preview_schema: null,
  current_version_no: 1,
  draft_base_version_no: 1,
  has_unpublished_changes: false,
  published_at: '2026-05-01T10:00:00+08:00',
  file_type: 'vue',
  created_at: '2026-05-01T10:00:00+08:00',
  updated_at: '2026-05-01T10:00:00+08:00',
  created_by: 1,
  updated_by: 1,
}

describe('WorkspaceComponentWorkbench', () => {
  it('同 ID 组件状态变化后应重新载入草稿并刷新预览', async () => {
    const { rerender } = render(WorkspaceComponentWorkbench, {
      props: {
        workspaceId: 11,
        component: baseComponent,
        createToken: 0,
      },
      global: {
        stubs: {
          ComponentPreviewWorkbench: defineComponent({
            name: 'ComponentPreviewWorkbench',
            props: {
              title: { type: String, default: '' },
              refreshKey: { type: Number, default: 0 },
            },
            setup(props) {
              return () => h('section', `预览工作台：${props.title}#${props.refreshKey}`)
            },
          }),
          ComponentEditorPane: true,
          ComponentVersionHistoryDialog: true,
          ComponentReferenceDialog: true,
          ComponentReleaseDialog: true,
          StatusTag: true,
          BaseButton: true,
          BaseDialog: true,
        },
      },
    })

    expect(await screen.findByText('预览工作台：销售卡片#1')).toBeInTheDocument()

    await rerender({
      workspaceId: 11,
      component: {
        ...baseComponent,
        name: '智能体更新卡片',
        content: '<template><div>agent updated</div></template>',
        current_version_no: 2,
        has_unpublished_changes: true,
        updated_at: '2026-05-01T10:20:00+08:00',
      },
      createToken: 0,
    })

    await waitFor(() => {
      expect(screen.getByText('预览工作台：智能体更新卡片#2')).toBeInTheDocument()
    })
  })

  it('点击编辑组件应通过弹窗展示编辑表单', async () => {
    render(WorkspaceComponentWorkbench, {
      props: {
        workspaceId: 11,
        component: baseComponent,
        createToken: 0,
      },
      global: {
        stubs: {
          ComponentPreviewWorkbench: defineComponent({
            name: 'ComponentPreviewWorkbench',
            setup(_, { slots }) {
              return () => h('section', [
                h('div', '预览工作台'),
                slots['component-actions']?.(),
                slots.actions?.(),
              ])
            },
          }),
          ComponentEditorPane: defineComponent({
            name: 'ComponentEditorPane',
            props: {
              mode: { type: String, required: true },
            },
            setup(props) {
              return () => h('section', `编辑弹窗：${props.mode}`)
            },
          }),
          ComponentVersionHistoryDialog: true,
          ComponentReferenceDialog: true,
          ComponentReleaseDialog: true,
          StatusTag: true,
          BaseButton: defineComponent({
            name: 'BaseButton',
            emits: ['click'],
            setup(_, { emit, slots }) {
              return () => h('button', { type: 'button', onClick: () => emit('click') }, slots.default?.())
            },
          }),
          BaseDialog: true,
        },
      },
    })

    await fireEvent.click(await screen.findByText('编辑组件'))

    expect(await screen.findByText('编辑弹窗：edit')).toBeInTheDocument()
  })

  it('新建草稿预览应使用表单里的当前组件类型', async () => {
    const { rerender } = render(WorkspaceComponentWorkbench, {
      props: {
        workspaceId: 11,
        component: null,
        createToken: 0,
      },
      global: {
        stubs: {
          ComponentPreviewWorkbench: defineComponent({
            name: 'ComponentPreviewWorkbench',
            props: {
              source: { type: Object, default: null },
            },
            setup(props, { expose }) {
              expose({
                refreshCurrentPreview: async () => {},
              })
              return () => h('section', `组件类型：${props.source?.componentType || ''}`)
            },
          }),
          ComponentEditorPane: defineComponent({
            name: 'ComponentEditorPane',
            props: {
              form: { type: Object, required: true },
            },
            emits: ['update:form', 'preview-draft'],
            setup(props, { emit }) {
              return () => h('button', {
                type: 'button',
                onClick: () => {
                  emit('update:form', {
                    ...props.form,
                    name: '整页预览组件',
                    import_name: 'FullPreview',
                    component_type: '布局容器',
                    content: '<template><div /></template>',
                  })
                  emit('preview-draft')
                },
              }, '预览草稿')
            },
          }),
          ComponentVersionHistoryDialog: true,
          ComponentReferenceDialog: true,
          ComponentReleaseDialog: true,
          StatusTag: true,
          BaseButton: true,
          BaseDialog: true,
        },
      },
    })

    await rerender({
      workspaceId: 11,
      component: null,
      createToken: 1,
    })

    await fireEvent.click(await screen.findByText('预览草稿'))

    await waitFor(() => {
      expect(screen.getByText('组件类型：布局容器')).toBeInTheDocument()
    })
  })
})
