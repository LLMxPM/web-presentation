/**
 * 文件功能：验证组件库左侧列表的选择、新建入口和只读模式行为。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ComponentLibraryPanel from '@/components/project/ComponentLibraryPanel.vue'
import type { WorkspaceComponentItem } from '@/types/api'

const listComponentsMock = vi.fn()
const routerPushMock = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: routerPushMock,
  }),
}))

vi.mock('@/api/catalog', () => ({
  listComponents: (...args: unknown[]) => listComponentsMock(...args),
  deleteComponent: vi.fn(),
}))

const componentItem: WorkspaceComponentItem = {
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

const unpublishedComponentItem: WorkspaceComponentItem = {
  ...componentItem,
  id: 100,
  code: 'CMP100',
  name: '草稿组件',
  import_name: 'DraftCard',
  current_version_no: 0,
  draft_base_version_no: 0,
  has_unpublished_changes: true,
  published_at: null,
}

describe('ComponentLibraryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listComponentsMock.mockResolvedValue({
      items: [componentItem],
      total: 1,
      page: 1,
      page_size: 100,
    })
  })

  it('点击工作空间组件应发出选择事件，点击新建应发出创建事件', async () => {
    const { emitted } = render(ComponentLibraryPanel, {
      props: {
        modelValue: true,
        workspaceId: 11,
        closable: false,
      },
      global: {
        stubs: {
          RuntimeKitCapabilityList: true,
          StatusTag: true,
        },
      },
    })

    await waitFor(() => {
      expect(screen.getByText('销售卡片')).toBeInTheDocument()
      expect(screen.getByText('SalesCard')).toBeInTheDocument()
    })

    await fireEvent.click(screen.getByText('销售卡片'))
    await fireEvent.click(screen.getByTitle('新建组件'))

    expect(emitted('workspace-component-selected')?.[0]).toEqual([componentItem])
    expect(emitted('create-workspace-component')).toHaveLength(1)
  })

  it('只读模式不展示新建和删除入口，并保留完整组件库跳转入口', async () => {
    render(ComponentLibraryPanel, {
      props: {
        modelValue: true,
        workspaceId: 11,
        readOnly: true,
      },
      global: {
        stubs: {
          RuntimeKitCapabilityList: true,
          StatusTag: true,
        },
      },
    })

    await waitFor(() => {
      expect(screen.getByText('销售卡片')).toBeInTheDocument()
    })

    expect(screen.queryByTitle('新建组件')).toBeNull()
    expect(screen.queryByTitle('删除组件')).toBeNull()
    expect(screen.getByTitle('打开完整组件库页面')).toBeInTheDocument()
  })

  it('开启发布过滤时只展示已有正式版本的工作空间组件', async () => {
    listComponentsMock.mockResolvedValueOnce({
      items: [componentItem, unpublishedComponentItem],
      total: 2,
      page: 1,
      page_size: 100,
    })

    render(ComponentLibraryPanel, {
      props: {
        modelValue: true,
        workspaceId: 11,
        publishedOnly: true,
      },
      global: {
        stubs: {
          RuntimeKitCapabilityList: true,
          StatusTag: true,
        },
      },
    })

    await waitFor(() => {
      expect(screen.getByText('销售卡片')).toBeInTheDocument()
    })

    expect(screen.queryByText('草稿组件')).toBeNull()
    expect(listComponentsMock).toHaveBeenCalledWith(expect.objectContaining({
      workspace_id: 11,
      published_only: true,
    }))
  })

  it('未勾选导出组件时展示刷新入口，勾选后切换为导出入口', async () => {
    const { emitted, rerender } = render(ComponentLibraryPanel, {
      props: {
        modelValue: true,
        workspaceId: 11,
        closable: false,
        batchSelectedComponentIds: [],
      },
      global: {
        stubs: {
          RuntimeKitCapabilityList: true,
          StatusTag: true,
        },
      },
    })

    await waitFor(() => {
      expect(screen.getByText('销售卡片')).toBeInTheDocument()
    })

    expect(screen.getByTitle('刷新组件列表')).toBeInTheDocument()
    expect(screen.queryByTitle('导出已勾选组件')).toBeNull()

    await fireEvent.click(screen.getByTitle('刷新组件列表'))
    expect(emitted('refresh-requested')).toHaveLength(1)

    await rerender({
      modelValue: true,
      workspaceId: 11,
      closable: false,
      batchSelectedComponentIds: [componentItem.id],
    })

    expect(screen.queryByTitle('刷新组件列表')).toBeNull()
    expect(screen.getByTitle('导出已勾选组件')).toBeInTheDocument()
  })

  it('隐藏新建导入入口时仍保留刷新和导出入口', async () => {
    const { rerender } = render(ComponentLibraryPanel, {
      props: {
        modelValue: true,
        workspaceId: 11,
        closable: false,
        showCreateImportActions: false,
        batchSelectedComponentIds: [],
      },
      global: {
        stubs: {
          RuntimeKitCapabilityList: true,
          StatusTag: true,
        },
      },
    })

    await waitFor(() => {
      expect(screen.getByText('销售卡片')).toBeInTheDocument()
    })

    expect(screen.queryByTitle('导入组件离线包')).toBeNull()
    expect(screen.queryByTitle('新建组件')).toBeNull()
    expect(screen.getByTitle('刷新组件列表')).toBeInTheDocument()

    await rerender({
      modelValue: true,
      workspaceId: 11,
      closable: false,
      showCreateImportActions: false,
      batchSelectedComponentIds: [componentItem.id],
    })

    expect(screen.queryByTitle('导入组件离线包')).toBeNull()
    expect(screen.queryByTitle('新建组件')).toBeNull()
    expect(screen.getByTitle('导出已勾选组件')).toBeInTheDocument()
  })
})
