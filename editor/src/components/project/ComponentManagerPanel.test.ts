/**
 * 文件功能：验证全局组件库只读侧边栏的列表入口、预览弹窗和 Runtime Kit 分支。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ComponentManagerPanel from '@/components/project/ComponentManagerPanel.vue'
import type { ComponentPreviewWorkbenchSource } from '@/components/component-preview/component-preview-workbench'
import type { RuntimeKitComponentCapabilityItem, WorkspaceComponentItem } from '@/types/api'

const listComponentsMock = vi.fn()
const getComponentMock = vi.fn()
const listRuntimeKitComponentsMock = vi.fn()
const routerPushMock = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: routerPushMock,
  }),
}))

vi.mock('@/api/catalog', () => ({
  getComponent: (...args: unknown[]) => getComponentMock(...args),
  listComponents: (...args: unknown[]) => listComponentsMock(...args),
  deleteComponent: vi.fn(),
}))

vi.mock('@/api/runtime-kit', () => ({
  listRuntimeKitComponents: (...args: unknown[]) => listRuntimeKitComponentsMock(...args),
}))

describe('ComponentManagerPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listComponentsMock.mockResolvedValue({
      items: createWorkspaceComponents(),
      total: 2,
      page: 1,
      page_size: 100,
    })
    getComponentMock.mockResolvedValue(createWorkspaceComponents()[0])
    listRuntimeKitComponentsMock.mockResolvedValue({
      items: createRuntimeKitItems(),
    })
  })

  it('只读模式不展示新建、编辑、删除和发布入口，未发布组件不能复制 import', async () => {
    renderPanel()

    await waitFor(() => {
      expect(screen.getByText('已发布组件')).toBeInTheDocument()
      expect(screen.getByText('未发布组件')).toBeInTheDocument()
    })

    expect(screen.queryByText('新建')).toBeNull()
    expect(screen.queryByTitle('删除组件')).toBeNull()
    expect(screen.queryByText('编辑组件')).toBeNull()
    expect(screen.queryByText('发布')).toBeNull()
    expect(screen.getByTitle('发布后可复制 import 语句')).toHaveProperty('disabled', true)
  })

  it('点击组件管理应关闭侧边栏并跳转完整组件库页面', async () => {
    renderPanel()

    await waitFor(() => {
      expect(screen.getByTitle('打开完整组件库页面')).toBeInTheDocument()
    })
    await fireEvent.click(screen.getByTitle('打开完整组件库页面'))

    expect(routerPushMock).toHaveBeenCalledWith('/workspaces/11/components')
  })

  it('选择工作空间组件后应打开 ComponentPreviewWorkbench 预览弹窗', async () => {
    const { emitted } = renderPanel()

    await waitFor(() => {
      expect(screen.getByText('已发布组件')).toBeInTheDocument()
    })
    await fireEvent.click(screen.getByText('已发布组件'))

    await waitFor(() => {
      expect(screen.getByTestId('preview-workbench')).toHaveTextContent('预览工作台：workspace-draft:已发布组件')
    })
    expect(screen.getByTestId('preview-workbench')).toHaveTextContent('组件类型：内容区块')
    const selectedEvents = emitted()['component-selected'] as Array<[WorkspaceComponentItem | null]>
    expect(selectedEvents[0][0]).toMatchObject({
      id: 1,
      name: '已发布组件',
    })
  })

  it('选择 Runtime Kit 可预览能力后应打开同一个预览工作台', async () => {
    renderPanel()

    await switchToRuntimeKitTab()
    await fireEvent.click(screen.getByText('资源渲染器'))

    await waitFor(() => {
      expect(screen.getByTestId('preview-workbench')).toHaveTextContent('预览工作台：runtime-kit:资源渲染器')
    })
  })

  it('选择 Runtime Kit doc-only 能力应打开说明弹窗，不进入预览工作台', async () => {
    renderPanel()

    await switchToRuntimeKitTab()
    await fireEvent.click(screen.getByText('格式化工具'))

    await waitFor(() => {
      expect(screen.getByTestId('runtime-doc-dialog')).toHaveTextContent('能力说明：格式化工具')
    })
    expect(screen.queryByTestId('preview-workbench')).toBeNull()
  })

  it('收到智能体组件写入事件后应刷新侧边栏列表', async () => {
    renderPanel()

    await waitFor(() => {
      expect(screen.getByText('已发布组件')).toBeInTheDocument()
    })
    const initialCallCount = listComponentsMock.mock.calls.length

    window.dispatchEvent(new CustomEvent('agent:component-updated', {
      detail: {
        workspaceId: 11,
        componentId: 1,
        toolName: 'apply_component_edits',
        result: { success: true, component_id: 1 },
      },
    }))

    await waitFor(() => {
      expect(listComponentsMock.mock.calls.length).toBeGreaterThan(initialCallCount)
    })
  })
})

function renderPanel() {
  return render(ComponentManagerPanel, {
    props: {
      modelValue: true,
      workspaceId: 11,
      readOnly: true,
    },
    global: {
      stubs: {
        teleport: true,
        ComponentPreviewWorkbench: createPreviewWorkbenchStub(),
        RuntimeKitCapabilityDocDialog: createRuntimeKitDocDialogStub(),
      },
    },
  })
}

async function switchToRuntimeKitTab(): Promise<void> {
  await waitFor(() => {
    expect(screen.getByText('内建能力')).toBeInTheDocument()
  })
  await fireEvent.click(screen.getByText('内建能力'))
  await waitFor(() => {
    expect(screen.getByText('资源渲染器')).toBeInTheDocument()
    expect(screen.getByText('格式化工具')).toBeInTheDocument()
  })
}

function createPreviewWorkbenchStub() {
  return defineComponent({
    name: 'ComponentPreviewWorkbench',
    props: {
      source: {
        type: Object,
        default: null,
      },
      title: {
        type: String,
        default: '',
      },
    },
    setup(props, { slots }) {
      return () => {
        const source = props.source as ComponentPreviewWorkbenchSource | null
        return h('section', { 'data-testid': 'preview-workbench' }, [
          `预览工作台：${source?.kind || 'empty'}:${props.title}`,
          `组件类型：${source?.kind === 'workspace-draft' ? source.componentType : ''}`,
          slots.actions?.(),
        ])
      }
    },
  })
}

function createRuntimeKitDocDialogStub() {
  return defineComponent({
    name: 'RuntimeKitCapabilityDocDialog',
    props: {
      modelValue: {
        type: Boolean,
        default: false,
      },
      item: {
        type: Object,
        default: null,
      },
    },
    emits: ['update:modelValue'],
    setup(props) {
      return () => {
        const item = props.item as RuntimeKitComponentCapabilityItem | null
        return props.modelValue
          ? h('section', { 'data-testid': 'runtime-doc-dialog' }, `能力说明：${item?.display_name || ''}`)
          : null
      }
    },
  })
}

function createWorkspaceComponents(): WorkspaceComponentItem[] {
  return [
    {
      id: 1,
      workspace_id: 11,
      workspace_name: '默认工作空间',
      code: 'CMP001',
      name: '已发布组件',
      import_name: 'PublishedComponent',
      component_type: '内容区块',
      summary: null,
      status: 'active',
      content: '<template><div /></template>',
      preview_schema: null,
      current_version_no: 2,
      draft_base_version_no: 2,
      has_unpublished_changes: false,
      published_at: '2026-05-01T10:00:00+08:00',
      file_type: 'vue',
      created_at: '2026-05-01T10:00:00+08:00',
      updated_at: '2026-05-01T10:00:00+08:00',
      created_by: 1,
      updated_by: 1,
    },
    {
      id: 2,
      workspace_id: 11,
      workspace_name: '默认工作空间',
      code: 'CMP002',
      name: '未发布组件',
      import_name: 'DraftComponent',
      component_type: '内容区块',
      summary: null,
      status: 'active',
      content: '<template><div /></template>',
      preview_schema: null,
      current_version_no: 0,
      draft_base_version_no: 0,
      has_unpublished_changes: true,
      published_at: null,
      file_type: 'vue',
      created_at: '2026-05-01T10:00:00+08:00',
      updated_at: '2026-05-01T10:00:00+08:00',
      created_by: 1,
      updated_by: 1,
    },
  ]
}

function createRuntimeKitItems(): RuntimeKitComponentCapabilityItem[] {
  return [
    {
      kind: 'component',
      name: 'AssetRenderer',
      import_path: '@runtime-kit/components/assets/AssetRenderer',
      category: 'assets',
      description: '资源渲染组件',
      display_name: '资源渲染器',
      summary: '渲染资源',
      tags: ['asset'],
      previewable: true,
      preview_schema: null,
      preview_options: null,
      usage: [],
      returns: null,
      return_example: [],
      constraints: [],
      audiences: ['agent'],
      manifest_version: '1.0.0',
    },
    {
      kind: 'util',
      name: 'formatValue',
      import_path: '@runtime-kit/utils/formatValue',
      category: 'format',
      description: '格式化工具',
      display_name: '格式化工具',
      summary: '格式化数据',
      tags: ['format'],
      previewable: false,
      preview_schema: null,
      preview_options: null,
      usage: ['formatValue(value)'],
      returns: 'string',
      return_example: ['"1,000"'],
      constraints: [],
      audiences: ['agent'],
      manifest_version: '1.0.0',
    },
  ]
}
