/**
 * 文件功能：验证独立组件库页面的右侧工作台切换和组件智能体上下文同步。
 */
import { defineComponent, h, ref } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { componentAgentContextKey } from '@/composables/component-agent-context'
import type { RuntimeKitComponentCapabilityItem, WorkspaceComponentItem } from '@/types/api'
import ComponentsView from '@/views/ComponentsView.vue'

const getWorkspaceMock = vi.fn()
const getComponentMock = vi.fn()
const exportComponentPackageMock = vi.fn()
const importComponentPackageMock = vi.fn()
const validateComponentPackageExportMock = vi.fn()
const validateComponentPackageImportMock = vi.fn()
const listWorkspaceAssetsMock = vi.fn()
const routerPushMock = vi.fn()
const routerReplaceMock = vi.fn()
const routeMock = {
  params: {
    workspaceId: '11',
  },
  path: '/workspaces/11/components',
  query: {} as Record<string, string>,
}

vi.mock('vue-router', () => ({
  useRoute: () => routeMock,
  useRouter: () => ({
    push: routerPushMock,
    replace: routerReplaceMock,
  }),
}))

vi.mock('@/api/catalog', () => ({
  getWorkspace: (...args: unknown[]) => getWorkspaceMock(...args),
  getComponent: (...args: unknown[]) => getComponentMock(...args),
  exportComponentPackage: (...args: unknown[]) => exportComponentPackageMock(...args),
  importComponentPackage: (...args: unknown[]) => importComponentPackageMock(...args),
  validateComponentPackageExport: (...args: unknown[]) => validateComponentPackageExportMock(...args),
  validateComponentPackageImport: (...args: unknown[]) => validateComponentPackageImportMock(...args),
}))

vi.mock('@/api/assets', () => ({
  listWorkspaceAssets: (...args: unknown[]) => listWorkspaceAssetsMock(...args),
}))

const selectedComponent: WorkspaceComponentItem = {
  id: 99,
  workspace_id: 11,
  workspace_name: '默认工作空间',
  code: 'CMP099',
  name: '销售卡片',
  import_name: 'SalesCard',
  component_type: '内容组件',
  summary: '销售数据展示组件',
  status: 'active',
  content: '<template><div /></template>',
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

const runtimeKitItem: RuntimeKitComponentCapabilityItem = {
  kind: 'component',
  base_name: 'AssetImage',
  version_no: 1,
  name: 'AssetImage.v1',
  import_path: '@runtime-kit/public/components/assets/AssetImage.v1.vue',
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
}

describe('ComponentsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeMock.query = {}
    routeMock.path = '/workspaces/11/components'
    getComponentMock.mockResolvedValue(selectedComponent)
    validateComponentPackageExportMock.mockResolvedValue({
      can_export: true,
      components: [],
      automatic_assets: [],
      manual_assets: [],
      fonts: [],
      warnings: [],
      missing_static_asset_names: [],
      missing_manual_asset_names: [],
      dynamic_resource_components: [],
    })
    exportComponentPackageMock.mockResolvedValue({
      blob: new Blob(['zip']),
      filename: 'workspace-components.zip',
    })
    validateComponentPackageImportMock.mockResolvedValue({
      valid: true,
      schema_version: 2,
      runtime_kit_manifest_version: null,
      components: [],
      assets: [],
      fonts: [],
      errors: [],
      warnings: [],
    })
    importComponentPackageMock.mockResolvedValue({
      imported_components: [],
      components: [],
      assets: [],
      fonts: [],
      warnings: [],
    })
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    })
  })

  it('选择工作空间组件后应同步上下文并在右侧显示组件工作台', async () => {
    const { setSelectedComponentMock } = renderComponentsView()

    await waitFor(() => {
      expect(setSelectedComponentMock).toHaveBeenCalledWith(null)
    })

    await fireEvent.click(screen.getByRole('button', { name: '选择销售卡片' }))

    await waitFor(() => {
      expect(setSelectedComponentMock).toHaveBeenCalledWith(selectedComponent)
      expect(screen.getByText('工作空间工作台：销售卡片')).toBeInTheDocument()
    })
    expect(routerReplaceMock).toHaveBeenCalledWith({
      path: '/workspaces/11/components',
      query: { componentId: '99' },
    })
    expect(screen.queryByText('当前组件')).toBeNull()
    expect(screen.queryByText('当前上下文')).toBeNull()
  })

  it('访问 componentId query 时应自动恢复选中组件', async () => {
    routeMock.query = { componentId: '99' }
    const { setSelectedComponentMock } = renderComponentsView()

    await waitFor(() => {
      expect(getComponentMock).toHaveBeenCalledWith(99)
      expect(setSelectedComponentMock).toHaveBeenLastCalledWith(selectedComponent)
      expect(screen.getByText('工作空间工作台：销售卡片')).toBeInTheDocument()
    })
    expect(routerReplaceMock).not.toHaveBeenCalled()
  })

  it('选择 Runtime Kit 预览能力后应清空组件上下文并显示右侧预览', async () => {
    routeMock.query = { componentId: '99' }
    const { setSelectedComponentMock } = renderComponentsView()

    await waitFor(() => {
      expect(setSelectedComponentMock).toHaveBeenLastCalledWith(selectedComponent)
    })
    await fireEvent.click(screen.getByRole('button', { name: '选择 Runtime Kit' }))

    await waitFor(() => {
      expect(setSelectedComponentMock).toHaveBeenLastCalledWith(null)
      expect(screen.getByText('Runtime Kit 预览：AssetImage.v1')).toBeInTheDocument()
    })
    expect(routerReplaceMock).toHaveBeenCalledWith({
      path: '/workspaces/11/components',
      query: {},
    })
  })

  it('点击新增组件后应清空上下文并打开右侧创建工作台', async () => {
    const { setSelectedComponentMock } = renderComponentsView()

    await fireEvent.click(screen.getByRole('button', { name: '新增组件' }))

    await waitFor(() => {
      expect(setSelectedComponentMock).toHaveBeenLastCalledWith(null)
      expect(screen.getByText(/工作空间工作台：新建/)).toBeInTheDocument()
    })
  })

  it('收到智能体组件修改事件后应刷新并选中最新组件', async () => {
    const updatedComponent: WorkspaceComponentItem = {
      ...selectedComponent,
      name: '智能体更新卡片',
      content: '<template><div>agent updated</div></template>',
      has_unpublished_changes: true,
      updated_at: '2026-05-01T10:20:00+08:00',
    }
    getComponentMock.mockResolvedValue(updatedComponent)
    const { setSelectedComponentMock } = renderComponentsView()

    await fireEvent.click(screen.getByRole('button', { name: '选择销售卡片' }))
    window.dispatchEvent(new CustomEvent('agent:component-updated', {
      detail: {
        workspaceId: 11,
        componentId: 99,
        toolName: 'apply_component_edits',
        result: { success: true, component_id: 99 },
      },
    }))

    await waitFor(() => {
      expect(getComponentMock).toHaveBeenCalledWith(99)
      expect(setSelectedComponentMock).toHaveBeenLastCalledWith(updatedComponent)
      expect(screen.getByText('工作空间工作台：智能体更新卡片')).toBeInTheDocument()
    })
  })

  it('收到智能体删除当前组件事件后应清空选择', async () => {
    const { setSelectedComponentMock } = renderComponentsView()

    await fireEvent.click(screen.getByRole('button', { name: '选择销售卡片' }))
    window.dispatchEvent(new CustomEvent('agent:component-updated', {
      detail: {
        workspaceId: 11,
        componentId: 99,
        toolName: 'delete_component',
        result: { success: true, component_id: 99 },
      },
    }))

    await waitFor(() => {
      expect(setSelectedComponentMock).toHaveBeenLastCalledWith(null)
      expect(screen.queryByText('工作空间工作台：销售卡片')).toBeNull()
      expect(screen.getByText('请选择左侧组件')).toBeInTheDocument()
    })
  })
})

function renderComponentsView() {
  getWorkspaceMock.mockResolvedValue({ id: 11, name: '默认工作空间' })
  const selectedComponentRef = ref<WorkspaceComponentItem | null>(null)
  const setSelectedComponentMock = vi.fn((component: WorkspaceComponentItem | null) => {
    selectedComponentRef.value = component
  })
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  render(ComponentsView, {
    global: {
      plugins: [
        [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
      ],
      provide: {
        [componentAgentContextKey as symbol]: {
          selectedComponent: selectedComponentRef,
          setSelectedComponent: setSelectedComponentMock,
        },
      },
      stubs: {
        PageTitleBar: defineComponent({
          name: 'PageTitleBar',
          setup(_, { slots }) {
            return () => h('header', [slots.default?.(), slots.actions?.()])
          },
        }),
        ComponentLibraryPanel: defineComponent({
          name: 'ComponentLibraryPanel',
          props: {
            showCreateImportActions: { type: Boolean, default: true },
          },
          emits: [
            'workspace-component-selected',
            'create-workspace-component',
            'runtime-kit-preview-selected',
          ],
          setup(props, { emit }) {
            return () => {
              const buttons = [
                h('button', {
                  type: 'button',
                  onClick: () => emit('workspace-component-selected', selectedComponent),
                }, '选择销售卡片'),
                h('button', {
                  type: 'button',
                  onClick: () => emit('runtime-kit-preview-selected', runtimeKitItem),
                }, '选择 Runtime Kit'),
              ]
              if (props.showCreateImportActions) {
                buttons.push(h('button', {
                  type: 'button',
                  onClick: () => emit('create-workspace-component'),
                }, '新增组件'))
              }
              return h('div', buttons)
            }
          },
        }),
        WorkspaceComponentWorkbench: defineComponent({
          name: 'WorkspaceComponentWorkbench',
          props: {
            component: { type: Object, default: null },
            createToken: { type: Number, default: 0 },
          },
          setup(props) {
            return () => h('section', `工作空间工作台：${(props.component as WorkspaceComponentItem | null)?.name || (props.createToken ? '新建' : '空')}`)
          },
        }),
        ComponentPreviewWorkbench: defineComponent({
          name: 'ComponentPreviewWorkbench',
          props: {
            source: { type: Object, default: null },
          },
          setup(props) {
            const source = props.source as { item?: RuntimeKitComponentCapabilityItem } | null
            return () => h('section', `Runtime Kit 预览：${source?.item?.name || '空'}`)
          },
        }),
        RuntimeKitCapabilityDocDialog: true,
        BaseButton: defineComponent({
          name: 'BaseButton',
          props: {
            disabled: { type: Boolean, default: false },
            loading: { type: Boolean, default: false },
            variant: { type: String, default: 'primary' },
          },
          setup(props, { attrs, slots }) {
            return () => h('button', {
              ...attrs,
              disabled: props.disabled || props.loading,
            }, slots.default?.())
          },
        }),
      },
    },
  })

  return { setSelectedComponentMock }
}
