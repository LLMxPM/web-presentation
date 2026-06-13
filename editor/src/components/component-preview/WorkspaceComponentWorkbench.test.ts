/**
 * 文件功能：验证工作空间组件工作台在同 ID 组件状态更新时重新载入草稿并刷新预览。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import WorkspaceComponentWorkbench from '@/components/component-preview/WorkspaceComponentWorkbench.vue'
import type { WorkspaceComponentItem } from '@/types/api'

const CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA = '{"props":{"height":{"type":"number","label":"高度","default":320}}}'

const catalogMocks = vi.hoisted(() => ({
  createComponent: vi.fn(),
  updateComponent: vi.fn(),
  getComponentReferences: vi.fn(),
  getComponentVersionContent: vi.fn(),
  listComponentVersions: vi.fn(),
  publishComponent: vi.fn(),
  restoreComponentVersionToDraft: vi.fn(),
  upgradeComponentReferences: vi.fn(),
}))

vi.mock('@/api/catalog', () => ({
  createComponent: (...args: unknown[]) => catalogMocks.createComponent(...args),
  updateComponent: (...args: unknown[]) => catalogMocks.updateComponent(...args),
  getComponentReferences: (...args: unknown[]) => catalogMocks.getComponentReferences(...args),
  getComponentVersionContent: (...args: unknown[]) => catalogMocks.getComponentVersionContent(...args),
  listComponentVersions: (...args: unknown[]) => catalogMocks.listComponentVersions(...args),
  publishComponent: (...args: unknown[]) => catalogMocks.publishComponent(...args),
  restoreComponentVersionToDraft: (...args: unknown[]) => catalogMocks.restoreComponentVersionToDraft(...args),
  upgradeComponentReferences: (...args: unknown[]) => catalogMocks.upgradeComponentReferences(...args),
}))

const baseComponent: WorkspaceComponentItem = {
  id: 99,
  workspace_id: 11,
  workspace_name: '默认工作空间',
  code: 'CMP099',
  name: '销售卡片',
  import_name: 'SalesCard',
  component_type: '内容组件',
  summary: '销售数据展示组件',
  status: 'active',
  content: '<template><div>old</div></template>',
  preview_schema: CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
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

const BaseDialogStub = defineComponent({
  name: 'BaseDialogStub',
  props: {
    modelValue: { type: Boolean, default: false },
  },
  setup(props, { slots }) {
    return () => (props.modelValue ? h('section', slots.default?.()) : null)
  },
})

describe('WorkspaceComponentWorkbench', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    catalogMocks.createComponent.mockImplementation((payload: Partial<WorkspaceComponentItem>) => Promise.resolve({
      ...baseComponent,
      id: 120,
      workspace_id: Number(payload.workspace_id ?? baseComponent.workspace_id),
      code: 'CMP120',
      name: String(payload.name ?? baseComponent.name),
      import_name: String(payload.import_name ?? baseComponent.import_name),
      component_type: payload.component_type ?? baseComponent.component_type,
      summary: payload.summary ?? null,
      status: payload.status ?? baseComponent.status,
      content: String(payload.content ?? baseComponent.content),
      preview_schema: payload.preview_schema ?? null,
      current_version_no: 0,
      draft_base_version_no: 0,
      has_unpublished_changes: true,
      updated_at: '2026-05-01T10:30:00+08:00',
    }))
    catalogMocks.updateComponent.mockImplementation((componentId: number, payload: Partial<WorkspaceComponentItem>) => Promise.resolve({
      ...baseComponent,
      id: componentId,
      name: String(payload.name ?? baseComponent.name),
      import_name: String(payload.import_name ?? baseComponent.import_name),
      component_type: payload.component_type ?? baseComponent.component_type,
      summary: payload.summary ?? null,
      status: payload.status ?? baseComponent.status,
      content: String(payload.content ?? baseComponent.content),
      preview_schema: payload.preview_schema ?? null,
      has_unpublished_changes: true,
      updated_at: '2026-05-01T10:30:00+08:00',
    }))
  })

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
          BaseDialog: BaseDialogStub,
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
          BaseDialog: BaseDialogStub,
        },
      },
    })

    await fireEvent.click(await screen.findByRole('button', { name: '编辑' }))

    expect(await screen.findByText('编辑弹窗：edit')).toBeInTheDocument()
  })

  it('已有组件保存并预览应先更新草稿，避免切换组件后丢失编辑内容', async () => {
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
            props: {
              source: { type: Object, default: null },
            },
            setup(props, { slots }) {
              return () => h('section', [
                h('div', `预览源码：${props.source?.content || ''}`),
                slots['component-actions']?.(),
              ])
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
                    content: '<template><div>saved preview</div></template>',
                  })
                  emit('preview-draft')
                },
              }, '保存并预览测试')
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
          BaseDialog: BaseDialogStub,
        },
      },
    })

    await fireEvent.click(await screen.findByRole('button', { name: '编辑' }))
    await fireEvent.click(await screen.findByText('保存并预览测试'))

    await waitFor(() => {
      expect(catalogMocks.updateComponent).toHaveBeenCalledWith(99, expect.objectContaining({
        content: '<template><div>saved preview</div></template>',
      }))
      expect(screen.getByText('预览源码：<template><div>saved preview</div></template>')).toBeInTheDocument()
    })
  })

  it('已有组件保存草稿应更新草稿但保留编辑弹窗', async () => {
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
              ])
            },
          }),
          ComponentEditorPane: defineComponent({
            name: 'ComponentEditorPane',
            props: {
              form: { type: Object, required: true },
            },
            emits: ['update:form', 'save-draft'],
            setup(props, { emit }) {
              return () => h('section', [
                h('div', '编辑弹窗仍打开'),
                h('button', {
                  type: 'button',
                  onClick: () => {
                    emit('update:form', {
                      ...props.form,
                      content: '<template><div>saved only</div></template>',
                    })
                    emit('save-draft')
                  },
                }, '保存草稿测试'),
              ])
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
          BaseDialog: BaseDialogStub,
        },
      },
    })

    await fireEvent.click(await screen.findByRole('button', { name: '编辑' }))
    await fireEvent.click(await screen.findByText('保存草稿测试'))

    await waitFor(() => {
      expect(catalogMocks.updateComponent).toHaveBeenCalledWith(99, expect.objectContaining({
        content: '<template><div>saved only</div></template>',
      }))
      expect(screen.getByText('编辑弹窗仍打开')).toBeInTheDocument()
    })
  })

  it('新建保存并预览应先创建草稿并使用保存后的组件类型', async () => {
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
                    component_type: '页面组件',
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
          BaseDialog: BaseDialogStub,
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
      expect(catalogMocks.createComponent).toHaveBeenCalledWith(expect.objectContaining({
        name: '整页预览组件',
        import_name: 'FullPreview',
        component_type: '页面组件',
        content: '<template><div /></template>',
      }))
      expect(screen.getByText('组件类型：页面组件')).toBeInTheDocument()
    })
  })

  it('新建内容组件缺少尺寸参数时不应提交草稿', async () => {
    const { rerender } = render(WorkspaceComponentWorkbench, {
      props: {
        workspaceId: 11,
        component: null,
        createToken: 0,
      },
      global: {
        stubs: {
          ComponentPreviewWorkbench: true,
          ComponentEditorPane: defineComponent({
            name: 'ComponentEditorPane',
            props: {
              errors: { type: Object, required: true },
              form: { type: Object, required: true },
            },
            emits: ['update:form', 'preview-draft'],
            setup(props, { emit }) {
              return () => h('section', [
                h('div', String(props.errors.preview_schema || '')),
                h('button', {
                  type: 'button',
                  onClick: () => {
                    emit('update:form', {
                      ...props.form,
                      name: '内容卡片',
                      import_name: 'ContentCard',
                      component_type: '内容组件',
                      content: '<template><div /></template>',
                      preview_schema: '',
                    })
                    emit('preview-draft')
                  },
                }, '提交缺少尺寸的内容组件'),
              ])
            },
          }),
          ComponentVersionHistoryDialog: true,
          ComponentReferenceDialog: true,
          ComponentReleaseDialog: true,
          StatusTag: true,
          BaseButton: true,
          BaseDialog: BaseDialogStub,
        },
      },
    })

    await rerender({
      workspaceId: 11,
      component: null,
      createToken: 1,
    })

    await fireEvent.click(await screen.findByText('提交缺少尺寸的内容组件'))

    await waitFor(() => {
      expect(catalogMocks.createComponent).not.toHaveBeenCalled()
      expect(screen.getByText(/内容组件必须在 previewSchema props 中声明/)).toBeInTheDocument()
    })
  })
})
