/**
 * 文件功能：验证顶部项目快速切换组件的项目列表展示与路由跳转行为。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectQuickSwitcher from '@/components/nav/ProjectQuickSwitcher.vue'

const routerPushMock = vi.hoisted(() => vi.fn())
const listProjectsMock = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPushMock }),
}))

vi.mock('@/api/catalog', () => ({
  listProjects: (...args: unknown[]) => listProjectsMock(...args),
}))

describe('ProjectQuickSwitcher', () => {
  beforeEach(() => {
    routerPushMock.mockReset()
    listProjectsMock.mockReset()
    listProjectsMock.mockResolvedValue({
      items: [
        createProject(2, '当前项目'),
        createProject(3, '增长看板'),
      ],
      total: 2,
      page: 1,
      page_size: 100,
    })
  })

  it('应展示当前项目，并可切换到其他项目页面列表', async () => {
    renderSwitcher({ workspaceId: 1, currentProjectId: 2, currentProjectName: '当前项目' })

    expect(screen.getByText('当前项目')).toBeTruthy()
    await fireEvent.click(screen.getByTestId('project-quick-switcher-trigger'))
    await fireEvent.click(await screen.findByText('增长看板'))

    expect(listProjectsMock).toHaveBeenCalledWith({
      page: 1,
      page_size: 100,
      workspace_id: 1,
      status: 'active',
    })
    expect(routerPushMock).toHaveBeenCalledWith('/workspaces/1/projects/3/pages')
  })

  it('应支持返回工作空间项目总览', async () => {
    renderSwitcher({ workspaceId: 1, currentProjectId: 2, currentProjectName: '当前项目' })

    await fireEvent.click(screen.getByTestId('project-quick-switcher-trigger'))
    await fireEvent.click(screen.getByTestId('project-quick-switcher-home'))

    expect(routerPushMock).toHaveBeenCalledWith('/workspaces/1/home')
  })
})

/**
 * 渲染带独立查询客户端的项目快速切换组件。
 */
function renderSwitcher(props: {
  workspaceId: number | null
  currentProjectId: number | null
  currentProjectName?: string | null
}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(ProjectQuickSwitcher, {
    props,
    global: {
      plugins: [
        [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
      ],
    },
  })
}

/**
 * 构造项目列表测试数据。
 * @param id 项目 ID
 * @param name 项目名称
 */
function createProject(id: number, name: string) {
  return {
    id,
    workspace_id: 1,
    workspace_name: '演示空间',
    code: `project-${id}`,
    name,
    description: null,
    is_system_managed: false,
    status: 'active',
    archived_at: null,
    page_width: 1920,
    page_height: 1080,
    base_font_size: '20px',
    icon_default_stroke_width: 2,
    show_pdf_export_button: true,
    menu_mode: 'preview',
    theme_key: null,
    theme_config_yaml: '',
    style_spec_markdown: '',
    created_at: '',
    updated_at: '',
    created_by: null,
    updated_by: null,
  }
}
