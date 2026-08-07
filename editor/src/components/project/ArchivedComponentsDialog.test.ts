/**
 * 文件功能：验证归档组件弹窗中的恢复操作与列表刷新。
 */
import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ArchivedComponentsDialog from './ArchivedComponentsDialog.vue'
import { renderWithEditorProviders } from '@/test/render'
import type { WorkspaceComponentItem } from '@/types/api'

const listComponentsMock = vi.hoisted(() => vi.fn())
const restoreComponentMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/catalog', () => ({
  listComponents: (...args: unknown[]) => listComponentsMock(...args),
  restoreComponent: (...args: unknown[]) => restoreComponentMock(...args),
}))

vi.mock('@/api/http', () => ({
  getErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

vi.mock('@/utils/message', () => ({
  Message: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('ArchivedComponentsDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    restoreComponentMock.mockResolvedValue({ message: '组件已恢复。' })
    listComponentsMock.mockResolvedValue({
      items: [createArchivedComponent()],
      total: 1,
      page: 1,
      page_size: 100,
    })
  })

  it('应展示归档组件并支持单个恢复，恢复后刷新归档列表', async () => {
    renderWithEditorProviders(ArchivedComponentsDialog, {
      props: { modelValue: true, workspaceId: 7 },
    })

    await screen.findByText('旧版销售卡片')
    expect(listComponentsMock).toHaveBeenCalledWith(
      expect.objectContaining({ workspace_id: 7, status: 'archived' }),
    )

    await fireEvent.click(screen.getByRole('button', { name: '恢复' }))

    await waitFor(() => {
      expect(restoreComponentMock).toHaveBeenCalledWith(19)
    })
    await waitFor(() => {
      expect(listComponentsMock).toHaveBeenCalledTimes(2)
    })
  })

  it('归档列表为空时应展示空态文案', async () => {
    listComponentsMock.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    })
    renderWithEditorProviders(ArchivedComponentsDialog, {
      props: { modelValue: true, workspaceId: 7 },
    })

    expect(await screen.findByText('当前没有已归档组件。')).toBeInTheDocument()
  })
})

/**
 * 构造用于归档组件列表的完整组件数据。
 */
function createArchivedComponent(): WorkspaceComponentItem {
  return {
    id: 19,
    workspace_id: 7,
    workspace_name: '设计团队',
    code: 'CMP019',
    name: '旧版销售卡片',
    import_name: 'LegacySalesCard',
    component_type: '内容组件',
    summary: '已被新版组件替代',
    status: 'archived',
    content: '<template><div /></template>',
    preview_schema: null,
    current_version_no: 1,
    draft_base_version_no: 1,
    has_unpublished_changes: false,
    published_at: '2026-05-01T08:00:00+08:00',
    file_type: 'vue',
    created_at: '2026-05-01T08:00:00+08:00',
    updated_at: '2026-06-01T08:00:00+08:00',
    created_by: 1,
    updated_by: 1,
  }
}
