/**
 * 文件功能：验证页面跨项目复制弹窗的目标项目筛选与提交 payload。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import PageCopyToProjectDialog from './PageCopyToProjectDialog.vue'
import type { PageItem, ProjectItem, RecordStatus } from '@/types/api'

const listProjectsMock = vi.fn()
const getProjectRoutesMock = vi.fn()
const messageErrorMock = vi.fn()
const messageWarningMock = vi.fn()

vi.mock('@/api/catalog', () => ({
  listProjects: (...args: unknown[]) => listProjectsMock(...args),
  getProjectRoutes: (...args: unknown[]) => getProjectRoutesMock(...args),
}))

vi.mock('@/api/http', () => ({
  getErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

vi.mock('@/utils/message', () => ({
  Message: {
    error: (...args: unknown[]) => messageErrorMock(...args),
    warning: (...args: unknown[]) => messageWarningMock(...args),
  },
}))

function createPage(): PageItem {
  return {
    id: 31,
    code: 'PG20260521001',
    page_content: '<template><div>demo</div></template>',
    current_version_no: 1,
    file_type: 'vue',
    title: '源页面',
    summary: '源摘要',
    status: 'active',
    workspace_id: 11,
    workspace_name: '工作空间 A',
    project_id: 21,
    project_name: '源项目',
    created_at: '2026-05-21T00:00:00Z',
    updated_at: '2026-05-21T00:00:00Z',
    created_by: 1,
    updated_by: 1,
    screenshot_url: null,
    screenshot_version_no: null,
    screenshot_config_hash: null,
    screenshot_is_latest: false,
    screenshot_updated_at: null,
    is_in_project_route: false,
    route_bindings: [],
  }
}

function createProject(id: number, name: string, workspaceId = 11, status: RecordStatus = 'active'): ProjectItem {
  return {
    id,
    workspace_id: workspaceId,
    workspace_name: '工作空间 A',
    code: `PRJ${id}`,
    name,
    description: null,
    is_system_managed: false,
    status,
    archived_at: null,
    page_width: 1920,
    page_height: 1080,
    base_font_size: '20px',
    icon_default_stroke_width: 2,
    show_pdf_export_button: true,
    menu_mode: 'preview',
    theme_key: null,
    theme_config_yaml: 'themes: {}',
    style_spec_markdown: '',
    created_at: '2026-05-21T00:00:00Z',
    updated_at: '2026-05-21T00:00:00Z',
    created_by: 1,
    updated_by: 1,
  }
}

function renderDialog() {
  return render(PageCopyToProjectDialog, {
    props: {
      modelValue: true,
      page: createPage(),
      workspaceId: 11,
      currentProjectId: 21,
      loading: false,
    },
    global: {
      stubs: {
        teleport: true,
      },
    },
  })
}

function getSubmitPayload(view: ReturnType<typeof render>) {
  const emitted = view.emitted() as Record<string, Array<unknown[]>>
  return emitted.submit?.[0]?.[0]
}

describe('PageCopyToProjectDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listProjectsMock.mockResolvedValue({
      items: [
        createProject(21, '源项目'),
        createProject(22, '目标项目'),
        createProject(23, '归档项目', 11, 'archived'),
        createProject(24, '其他空间项目', 12),
      ],
      total: 4,
      page: 1,
      page_size: 100,
    })
    getProjectRoutesMock.mockResolvedValue({
      routes: [],
    })
  })

  it('只列出当前工作空间其他 active 项目，并默认提交未加入路由', async () => {
    const view = renderDialog()

    await screen.findByText('目标项目')
    expect(screen.queryByText('源项目')).not.toBeInTheDocument()
    expect(listProjectsMock).toHaveBeenCalledWith(expect.objectContaining({
      workspace_id: 11,
      status: 'active',
    }))

    await fireEvent.click(screen.getByText('复制页面'))

    expect(getSubmitPayload(view)).toEqual({
      target_project_id: 22,
      title: '源页面',
      summary: '源摘要',
      route_placement: 'none',
      parent_route_id: null,
      route: null,
    })
  })

  it('选择分组路由时提交目标分组和自定义路由片段', async () => {
    getProjectRoutesMock.mockResolvedValue({
      routes: [
        {
          id: 301,
          route_type: 'group',
          route: 'chapter',
          order: 10,
          icon: null,
          hidden: false,
          group_title: '章节',
          page_id: null,
          page_code: null,
          page_title: null,
          display_title: '章节',
          children: [],
        },
      ],
    })
    const view = renderDialog()

    await screen.findByText('目标项目')
    await waitFor(() => expect(getProjectRoutesMock).toHaveBeenCalledWith(22))

    await fireEvent.update(screen.getByPlaceholderText('留空时使用新页面编码'), 'overview')
    await fireEvent.click(screen.getByLabelText('复制后加入目标项目路由'))
    await fireEvent.click(screen.getByText('目标分组'))
    await fireEvent.click(screen.getByText('选择目标分组'))
    await fireEvent.click(screen.getByText('章节'))
    await fireEvent.click(screen.getByText('复制页面'))

    expect(getSubmitPayload(view)).toEqual({
      target_project_id: 22,
      title: '源页面',
      summary: '源摘要',
      route_placement: 'group',
      parent_route_id: 301,
      route: 'overview',
    })
  })
})
