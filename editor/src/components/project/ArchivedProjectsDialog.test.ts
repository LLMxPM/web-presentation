/**
 * 文件功能：验证归档项目弹窗中的恢复与删除操作。
 */
import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ArchivedProjectsDialog from './ArchivedProjectsDialog.vue'
import { renderWithEditorProviders } from '@/test/render'
import type { ProjectItem } from '@/types/api'

const deleteProjectMock = vi.hoisted(() => vi.fn())
const listProjectsMock = vi.hoisted(() => vi.fn())
const createConfirmMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/catalog', () => ({
  deleteProject: (...args: unknown[]) => deleteProjectMock(...args),
  listProjects: (...args: unknown[]) => listProjectsMock(...args),
  updateProject: vi.fn(),
}))

vi.mock('@/api/http', () => ({
  getErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

vi.mock('@/utils/message', () => ({
  createConfirm: (...args: unknown[]) => createConfirmMock(...args),
  Message: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('ArchivedProjectsDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    createConfirmMock.mockResolvedValue(true)
    deleteProjectMock.mockResolvedValue({ message: '项目已删除。' })
    listProjectsMock.mockResolvedValue({
      items: [createArchivedProject()],
      total: 1,
      page: 1,
      page_size: 100,
    })
  })

  it('确认后应删除归档项目并刷新归档列表', async () => {
    renderWithEditorProviders(ArchivedProjectsDialog, {
      props: { modelValue: true, workspaceId: 7 },
    })

    await screen.findByText('季度复盘')
    await fireEvent.click(screen.getByRole('button', { name: '删除' }))

    await waitFor(() => {
      expect(createConfirmMock).toHaveBeenCalledWith(
        '删除后「季度复盘」将不再出现在项目列表中，确定删除吗？',
        '删除归档项目',
      )
      expect(deleteProjectMock).toHaveBeenCalledWith(19)
    })

    await waitFor(() => {
      expect(listProjectsMock).toHaveBeenCalledTimes(2)
    })
  })
})

/**
 * 构造用于归档项目列表的完整项目数据。
 */
function createArchivedProject(): ProjectItem {
  return {
    id: 19,
    workspace_id: 7,
    workspace_name: '设计团队',
    code: 'PRJ-019',
    name: '季度复盘',
    description: '已完成的季度演示材料',
    is_system_managed: false,
    status: 'archived',
    archived_at: '2026-07-01T08:00:00+08:00',
    page_width: 1920,
    page_height: 1080,
    base_font_size: '20px',
    icon_default_stroke_width: 2,
    show_pdf_export_button: true,
    menu_mode: 'preview',
    theme_key: null,
    theme_config_yaml: '',
    style_spec_markdown: '',
    created_at: '2026-06-01T08:00:00+08:00',
    updated_at: '2026-07-01T08:00:00+08:00',
    created_by: 1,
    updated_by: 1,
  }
}
