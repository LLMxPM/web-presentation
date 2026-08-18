/**
 * 文件功能：验证项目列表响应智能体项目及页面变更事件后的刷新行为。
 */
import { defineComponent, h } from 'vue'
import { render, screen, waitFor } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectsView from '@/views/ProjectsView.vue'

const listProjectsMock = vi.fn()
const getWorkspaceMock = vi.fn()
const routeMock = {
  params: {
    workspaceId: '11',
  },
}

vi.mock('vue-router', () => ({
  useRoute: () => routeMock,
  useRouter: () => ({
    push: vi.fn(),
  }),
}))

vi.mock('@/api/catalog', () => ({
  createProject: vi.fn(),
  getWorkspace: (...args: unknown[]) => getWorkspaceMock(...args),
  listProjects: (...args: unknown[]) => listProjectsMock(...args),
  updateProject: vi.fn(),
  updateWorkspace: vi.fn(),
}))

vi.mock('@/api/preview', () => ({
  createProjectPreviewArtifact: vi.fn(),
}))

vi.mock('@/api/templates', () => ({
  createProjectTemplatePackagePreviewArtifact: vi.fn(),
  exportProjectTemplatePackage: vi.fn(),
  importProjectTemplatePackage: vi.fn(),
  validateProjectTemplatePackageExport: vi.fn(),
  validateProjectTemplatePackageImport: vi.fn(),
}))

vi.mock('@/utils/message', () => ({
  createConfirm: vi.fn(),
  Message: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

vi.mock('@/utils/zip-download', () => ({
  downloadBlob: vi.fn(),
}))

const ProjectCardStub = defineComponent({
  name: 'ProjectCard',
  props: {
    project: {
      type: Object,
      required: true,
    },
  },
  setup(props) {
    return () => h('div', { 'data-testid': 'project-card' }, String(props.project.name))
  },
})

const DataStateStub = defineComponent({
  name: 'DataState',
  setup(_, { slots }) {
    return () => h('div', slots.default?.())
  },
})

const project = createProjectItem('初始项目')

describe('ProjectsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getWorkspaceMock.mockResolvedValue({
      id: 11,
      name: '默认工作空间',
      description: null,
    })
    listProjectsMock.mockResolvedValue({
      items: [project],
      total: 1,
      page: 1,
      page_size: 24,
    })
  })

  it.each(['agent:project-updated', 'agent:project-pages-updated'])('收到 %s 后应刷新当前工作空间项目列表', async (eventName) => {
    const updatedProject = createProjectItem('智能体更新后的项目')
    listProjectsMock
      .mockResolvedValueOnce({ items: [project], total: 1, page: 1, page_size: 24 })
      .mockResolvedValueOnce({ items: [updatedProject], total: 1, page: 1, page_size: 24 })

    renderProjectsView()
    expect(await screen.findByText('初始项目')).toBeInTheDocument()

    window.dispatchEvent(new CustomEvent(eventName, {
      detail: {
        workspaceId: 11,
        projectId: 21,
        toolName: 'update_entity',
        result: { success: true },
      },
    }))

    await waitFor(() => {
      expect(listProjectsMock.mock.calls.length).toBeGreaterThanOrEqual(2)
      expect(screen.getByText('智能体更新后的项目')).toBeInTheDocument()
    })
  })

  it('收到其它工作空间的智能体事件时不应刷新项目列表', async () => {
    renderProjectsView()
    expect(await screen.findByText('初始项目')).toBeInTheDocument()
    const callCount = listProjectsMock.mock.calls.length

    window.dispatchEvent(new CustomEvent('agent:project-updated', {
      detail: { workspaceId: 99, projectId: 21 },
    }))

    await new Promise(resolve => window.setTimeout(resolve, 0))
    expect(listProjectsMock).toHaveBeenCalledTimes(callCount)
  })
})

/**
 * 构造项目列表测试数据，保证项目卡片需要的聚合字段完整。
 */
function createProjectItem(name: string) {
  return {
    id: 21,
    workspace_id: 11,
    workspace_name: '默认工作空间',
    code: 'PRJ202608180001',
    name,
    description: null,
    is_system_managed: false,
    status: 'active' as const,
    archived_at: null,
    page_width: 1600,
    page_height: 900,
    base_font_size: '20px',
    icon_default_stroke_width: 2,
    show_pdf_export_button: true,
    menu_mode: 'preview' as const,
    theme_key: 'lightblue',
    theme_config_yaml: 'themes: {}',
    style_spec_markdown: '',
    routed_page_count: 1,
    total_page_count: 1,
    first_page_title: '首页',
    first_page_screenshot_url: null,
    created_at: '2026-08-18T10:00:00+08:00',
    updated_at: '2026-08-18T10:00:00+08:00',
    created_by: 1,
    updated_by: 1,
  }
}

/**
 * 创建带 Vue Query 测试客户端的项目列表视图。
 */
function renderProjectsView() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
  return render(ProjectsView, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      stubs: {
        ArchivedProjectsDialog: true,
        CommandBar: true,
        DataState: DataStateStub,
        PageHeader: true,
        PaginationControl: true,
        ProjectCard: ProjectCardStub,
        ProjectCreateCard: true,
        ProjectMetadataDialog: true,
        RuntimePreviewFrame: true,
        SimpleSearchBar: true,
        UiButton: true,
        UiDialog: true,
        UiIconButton: true,
        WorkspaceMetadataDialog: true,
        WorkspacePagesDialog: true,
      },
    },
  })
}
