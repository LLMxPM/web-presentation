/**
 * 文件功能：验证工作空间全部页面弹窗的服务端搜索、分页和页面操作入口。
 */
import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import WorkspacePagesDialog from './WorkspacePagesDialog.vue'
import { renderWithEditorProviders } from '@/test/render'
import type { PageItem } from '@/types/api'

const listPagesMock = vi.hoisted(() => vi.fn())
const savePageScreenshotMock = vi.hoisted(() => vi.fn())
const downloadPageScreenshotMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/catalog', () => ({
  copyPageToProject: vi.fn(),
  listPages: (...args: unknown[]) => listPagesMock(...args),
  savePageScreenshot: (...args: unknown[]) => savePageScreenshotMock(...args),
  updatePage: vi.fn(),
}))

vi.mock('@/api/http', () => ({
  getErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

vi.mock('@/utils/message', () => ({
  createConfirm: vi.fn(),
  Message: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

vi.mock('@/utils/page-screenshot-download', () => ({
  downloadPageScreenshot: (...args: unknown[]) => downloadPageScreenshotMock(...args),
}))

const pushMock = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}))

describe('WorkspacePagesDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listPagesMock.mockResolvedValue({
      items: [createPage(31, '季度封面')],
      total: 25,
      page: 1,
      page_size: 24,
    })
    savePageScreenshotMock.mockResolvedValue(createPage(31, '季度封面'))
  })

  it('应按分页参数加载页面，并在搜索输入后回到第一页请求', async () => {
    renderWithEditorProviders(WorkspacePagesDialog, {
      props: { modelValue: true, workspaceId: 7 },
      global: {
        stubs: {
          PageCopyToProjectDialog: true,
        },
      },
    })

    await screen.findByText('季度封面')
    expect(listPagesMock).toHaveBeenCalledWith(expect.objectContaining({
      page: 1,
      page_size: 24,
      workspace_id: 7,
      project_assigned: true,
      status: 'active',
    }))

    await fireEvent.update(screen.getByRole('textbox', { name: '搜索所有页面' }), '封面')
    await new Promise(resolve => window.setTimeout(resolve, 350))

    await waitFor(() => {
      expect(listPagesMock).toHaveBeenCalledWith(expect.objectContaining({
        page: 1,
        keyword: '封面',
      }))
    })
  })

  it('应展示页面所属项目和受限操作按钮', async () => {
    renderWithEditorProviders(WorkspacePagesDialog, {
      props: { modelValue: true, workspaceId: 7 },
      global: {
        stubs: {
          PageCopyToProjectDialog: true,
        },
      },
    })

    await screen.findByText('季度封面')
    expect(screen.getByTestId('workspace-page-card')).toHaveClass('group')
    expect(screen.getByText('季度发布项目')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '查看页面详情', exact: true })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '复制页面' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '复制页面名称', exact: true })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '复制页面编码：PG31' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '更新截图' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '下载截图' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '归档页面' })).toBeInTheDocument()
  })

  it('点击页面名称复制时不应触发详情跳转', async () => {
    renderWithEditorProviders(WorkspacePagesDialog, {
      props: { modelValue: true, workspaceId: 7 },
      global: {
        stubs: {
          PageCopyToProjectDialog: true,
        },
      },
    })

    await screen.findByText('季度封面')
    await fireEvent.click(screen.getByRole('button', { name: '复制页面名称：季度封面' }))

    expect(pushMock).not.toHaveBeenCalled()
  })

  it('下载截图按钮在无截图时应先生成最新截图再下载', async () => {
    const pageWithoutScreenshot = {
      ...createPage(31, '季度封面'),
      screenshot_url: null,
      screenshot_version_no: null,
      screenshot_is_latest: false,
      screenshot_updated_at: null,
    }
    const latestPage = {
      ...pageWithoutScreenshot,
      screenshot_url: 'https://example.test/latest-page.png',
      screenshot_version_no: 2,
      screenshot_is_latest: true,
      screenshot_updated_at: '2026-08-07T08:00:00Z',
    }
    listPagesMock.mockResolvedValueOnce({
      items: [pageWithoutScreenshot],
      total: 1,
      page: 1,
      page_size: 24,
    })
    savePageScreenshotMock.mockResolvedValueOnce(latestPage)

    renderWithEditorProviders(WorkspacePagesDialog, {
      props: { modelValue: true, workspaceId: 7 },
      global: {
        stubs: {
          PageCopyToProjectDialog: true,
        },
      },
    })

    await screen.findByText('季度封面')
    const downloadButton = screen.getByRole('button', { name: '下载截图' })
    expect(downloadButton).not.toBeDisabled()

    await fireEvent.click(downloadButton)

    await waitFor(() => {
      expect(savePageScreenshotMock).toHaveBeenCalledWith(31)
      expect(downloadPageScreenshotMock).toHaveBeenCalledWith(
        latestPage.screenshot_url,
        latestPage.title,
        latestPage.screenshot_version_no,
      )
    })
  })
})

/**
 * 构造工作空间页面弹窗使用的完整页面数据。
 * @param id 页面 ID
 * @param title 页面标题
 */
function createPage(id: number, title: string): PageItem {
  return {
    id,
    code: `PG${id}`,
    page_content: '<template><div /></template>',
    current_version_no: 1,
    file_type: 'vue',
    title,
    summary: null,
    speaker_notes: null,
    status: 'active',
    workspace_id: 7,
    workspace_name: '设计空间',
    project_id: 13,
    project_name: '季度发布项目',
    created_at: '2026-08-01T08:00:00Z',
    updated_at: '2026-08-06T08:00:00Z',
    created_by: 1,
    updated_by: 1,
    screenshot_url: 'https://example.test/page.png',
    screenshot_version_no: 1,
    screenshot_config_hash: 'hash',
    screenshot_is_latest: true,
    screenshot_updated_at: '2026-08-06T08:00:00Z',
    is_in_project_route: true,
    route_bindings: [],
  }
}
