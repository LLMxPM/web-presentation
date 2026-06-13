/**
 * 文件功能：验证后台布局中的左侧 AI 助手、右侧工作空间 Dock、辅助面板与路由高亮逻辑。
 */
import { nextTick } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AdminLayout from '@/layouts/AdminLayout.vue'

interface MutableRoute {
  name: string
  params: Record<string, string>
  meta: Record<string, unknown>
}

const routerMock = vi.hoisted(() => ({
  route: null as MutableRoute | null,
  push: vi.fn(),
}))
const catalogApiMocks = vi.hoisted(() => ({
  getWorkspace: vi.fn(),
  getProject: vi.fn(),
  getPage: vi.fn(),
}))

vi.mock('vue-router', async () => {
  const { defineComponent, h, reactive } = await vi.importActual<typeof import('vue')>('vue')
  const RouteStub = defineComponent({
    name: 'RouteStub',
    setup() {
      return () => h('div', { 'data-testid': 'route-view' })
    },
  })

  routerMock.route = reactive({
    name: 'workspaceHome',
    params: { workspaceId: '1' },
    meta: { workspaceNav: 'projects' },
  })

  return {
    RouterLink: defineComponent({
      name: 'RouterLink',
      props: {
        to: {
          type: [String, Object],
          default: '',
        },
      },
      setup(_, { slots }) {
        return () => h('a', slots.default?.())
      },
    }),
    RouterView: defineComponent({
      name: 'RouterView',
      setup(_, { slots }) {
        return () => h('div', { 'data-testid': 'router-view' }, slots.default?.({ Component: RouteStub }))
      },
    }),
    useRoute: () => routerMock.route,
    useRouter: () => ({ push: routerMock.push }),
  }
})

vi.mock('@/api/catalog', () => ({
  getWorkspace: (...args: unknown[]) => catalogApiMocks.getWorkspace(...args),
  getProject: (...args: unknown[]) => catalogApiMocks.getProject(...args),
  getPage: (...args: unknown[]) => catalogApiMocks.getPage(...args),
}))

vi.mock('@/components/nav/UserMenu.vue', () => ({
  default: { name: 'UserMenu', template: '<button type="button">用户</button>' },
}))

vi.mock('@/components/nav/WorkspaceSwitcher.vue', () => ({
  default: {
    name: 'WorkspaceSwitcher',
    props: ['prominent'],
    template: '<div data-testid="workspace-switcher" :data-prominent="prominent ? \'true\' : \'false\'">空间切换</div>',
  },
}))

vi.mock('@/components/nav/ProjectQuickSwitcher.vue', () => ({
  default: {
    name: 'ProjectQuickSwitcher',
    props: ['workspaceId', 'currentProjectId', 'currentProjectName'],
    template: '<div data-testid="project-quick-switcher" :data-workspace-id="workspaceId" :data-project-id="currentProjectId" :data-project-name="currentProjectName || \'\'">项目切换</div>',
  },
}))

vi.mock('@/components/agent/AgentGlobalSidebar.vue', () => ({
  default: {
    name: 'AgentGlobalSidebar',
    props: ['agentId', 'source'],
    emits: ['update:expanded'],
    template: `
      <aside data-testid="agent-sidebar" :data-agent-id="agentId" :data-source="source">
        <button type="button" data-testid="agent-expand-state" @click="$emit('update:expanded', true)">展开智能体</button>
      </aside>
    `,
  },
}))

describe('AdminLayout', () => {
  beforeEach(() => {
    routerMock.push.mockReset()
    catalogApiMocks.getWorkspace.mockReset()
    catalogApiMocks.getProject.mockReset()
    catalogApiMocks.getPage.mockReset()
    catalogApiMocks.getWorkspace.mockResolvedValue({ id: 1, name: '演示空间' })
    catalogApiMocks.getProject.mockResolvedValue({ id: 2, name: '演示项目' })
    catalogApiMocks.getPage.mockResolvedValue({ id: 3, title: '演示页面' })
    setRoute({
      name: 'workspaceHome',
      params: { workspaceId: '1' },
      meta: { workspaceNav: 'projects' },
    })
  })

  it('工作空间页面应展示右侧 Dock，并在项目路由上高亮项目入口', () => {
    renderLayout()

    expect(screen.getByTestId('agent-sidebar')).toBeTruthy()
    expect(screen.getByTestId('workspace-dock')).toHaveClass('w-14')
    expect(screen.getByTestId('project-quick-switcher')).toBeTruthy()
    expect(screen.getByTestId('workspace-dock-projects')).toHaveClass('dock-button-active')
  })

  it('应在后台框架底栏展示仓库、许可证与 Runtime 子模块信息', () => {
    renderLayout()

    const projectLink = screen.getByRole('link', { name: 'Web-Presentation' })
    const runtimeLink = screen.getByRole('link', { name: 'web-runtime-vue' })
    expect(screen.getByText('Apache License 2.0')).toBeTruthy()
    expect(screen.getByText('runtime')).toBeTruthy()
    expect(screen.getByText('submodule')).toBeTruthy()
    expect(screen.getByText('AGPL-3.0-or-later')).toBeTruthy()
    expect(projectLink).toHaveAttribute('href', 'https://github.com/LLMxPM/web-presentation')
    expect(runtimeLink).toHaveAttribute('href', 'https://github.com/LLMxPM/web-runtime-vue')
  })

  it('Dock 辅助入口应标注为侧栏入口', () => {
    renderLayout()

    expect(screen.getByTestId('workspace-dock-panel-assets').getAttribute('title')).toContain('侧栏')
    expect(screen.getByTestId('workspace-dock-panel-components').getAttribute('title')).toContain('侧栏')
    expect(screen.queryByTestId('workspace-dock-panel-themes')).toBeNull()
  })

  it('智能体侧栏展开时应隐藏顶部品牌标题', async () => {
    renderLayout()

    expect(screen.getByTestId('app-brand-title')).toBeTruthy()

    await fireEvent.click(screen.getByTestId('agent-expand-state'))

    expect(screen.queryByTestId('app-brand-title')).toBeNull()
  })

  it.each([
    ['components', 'workspace-dock-components', 'component-manager', 'editor-component-library'],
    ['assets', 'workspace-dock-assets', 'resource-manager', 'editor-asset-library'],
    ['themes', 'workspace-dock-themes', 'agent-coordinator', 'editor-agent-sidebar'],
    ['workspaceStyles', 'workspace-dock-styles', 'agent-coordinator', 'editor-agent-sidebar'],
  ])('进入 %s 页面时应高亮对应 Dock 入口并保持正确智能体上下文', (routeName, testId, agentId, source) => {
    setRoute({
      name: routeName,
      params: { workspaceId: '1' },
      meta: { fullHeight: true, workspaceNav: resolveWorkspaceNavFromRouteName(routeName) },
    })
    renderLayout()

    expect(screen.getByTestId(testId)).toHaveClass('dock-button-active')
    expect(screen.getByTestId('agent-sidebar').dataset.agentId).toBe(agentId)
    expect(screen.getByTestId('agent-sidebar').dataset.source).toBe(source)
  })

  it('项目页面和页面详情页应统一高亮项目入口', () => {
    setRoute({
      name: 'pageDetail',
      params: { workspaceId: '1', projectId: '2', pageId: '3' },
      meta: { workspaceNav: 'projects' },
    })
    renderLayout()

    expect(screen.getByTestId('workspace-dock-projects')).toHaveClass('dock-button-active')
    expect(screen.getByTestId('project-quick-switcher').dataset.projectId).toBe('2')
  })

  it('页面详情页应显示项目内路径面包屑', async () => {
    setRoute({
      name: 'pageDetail',
      params: { workspaceId: '1', projectId: '2', pageId: '3' },
      meta: { workspaceNav: 'projects' },
    })
    renderLayout()

    expect(screen.getByText('项目列表')).toBeTruthy()
    expect(screen.getByText('项目首页')).toBeTruthy()
    expect(await screen.findByText('演示页面')).toBeTruthy()
  })

  it('项目页面列表应显示项目列表到项目首页的面包屑', () => {
    setRoute({
      name: 'pages',
      params: { workspaceId: '1', projectId: '2' },
      meta: { workspaceNav: 'projects' },
    })
    renderLayout()

    const breadcrumb = screen.getByLabelText('当前位置')
    expect(breadcrumb.textContent).toContain('项目列表')
    expect(breadcrumb.textContent).toContain('项目首页')
  })

  it('点击 Dock 完整页面入口时应关闭辅助面板并切换主路由', async () => {
    renderLayout()

    await fireEvent.click(screen.getByTestId('workspace-dock-panel-assets'))
    expect(await screen.findByTestId('asset-panel')).toBeTruthy()

    await fireEvent.click(screen.getByTestId('workspace-dock-components'))

    expect(routerMock.push).toHaveBeenCalledWith('/workspaces/1/components')
    expect(screen.queryByTestId('asset-panel')).toBeNull()
  })

  it('点击 Dock 辅助面板入口时同一时间只展开一个右侧面板', async () => {
    renderLayout()

    await fireEvent.click(screen.getByTestId('workspace-dock-panel-assets'))
    expect(await screen.findByTestId('asset-panel')).toBeTruthy()
    expect(screen.queryByTestId('component-panel')).toBeNull()

    await fireEvent.click(screen.getByTestId('workspace-dock-panel-components'))
    expect(await screen.findByTestId('component-panel')).toBeTruthy()
    expect(screen.queryByTestId('asset-panel')).toBeNull()

    expect(screen.queryByTestId('workspace-dock-panel-themes')).toBeNull()
  })

  it('进入 AI 设置页时应关闭左右两侧栏、右侧 Dock 和辅助面板', async () => {
    renderLayout()

    await fireEvent.click(screen.getByTestId('workspace-dock-panel-assets'))
    expect(await screen.findByTestId('asset-panel')).toBeTruthy()

    setRoute({
      name: 'accountAiSettings',
      params: {},
      meta: { hideSidebars: true },
    })
    await nextTick()

    await waitFor(() => {
      expect(screen.queryByTestId('agent-sidebar')).toBeNull()
      expect(screen.queryByTestId('workspace-dock')).toBeNull()
      expect(screen.queryByTestId('project-quick-switcher')).toBeNull()
      expect(screen.queryByTestId('asset-panel')).toBeNull()
    })
  })

  it('AI 设置页顶部应显著提示选择对应工作空间', () => {
    setRoute({
      name: 'accountAiSettings',
      params: {},
      meta: { hideSidebars: true },
    })
    renderLayout()

    expect(screen.getByText('选择对应工作空间，返回创作')).toBeTruthy()
    expect(screen.getByTestId('workspace-switcher').dataset.prominent).toBe('true')
    expect(screen.queryByLabelText('当前位置')).toBeNull()
  })

  it('普通工作空间页面不展示 AI 设置页的工作空间选择提示', () => {
    renderLayout()

    expect(screen.queryByText('选择对应工作空间，返回创作')).toBeNull()
    expect(screen.getByTestId('workspace-switcher').dataset.prominent).toBe('false')
  })

  it('收到智能体项目配置事件后应刷新顶部项目缓存', async () => {
    setRoute({
      name: 'pageDetail',
      params: { workspaceId: '1', projectId: '2', pageId: '3' },
      meta: { workspaceNav: 'projects' },
    })
    renderLayout()

    await waitFor(() => {
      expect(screen.getByTestId('project-quick-switcher').dataset.projectName).toBe('演示项目')
    })
    catalogApiMocks.getProject.mockResolvedValueOnce({ id: 2, name: '智能体更新项目' })

    window.dispatchEvent(new CustomEvent('agent:project-updated', {
      detail: {
        workspaceId: 1,
        projectId: 2,
        toolName: 'update_project_style_config',
        result: { success: true, project_id: 2 },
      },
    }))

    await waitFor(() => {
      expect(catalogApiMocks.getProject).toHaveBeenCalledTimes(2)
      expect(screen.getByTestId('project-quick-switcher').dataset.projectName).toBe('智能体更新项目')
    })
  })
})

/**
 * 根据路由名称返回右侧 Dock 应使用的导航 key。
 * @param routeName 路由名称
 */
function resolveWorkspaceNavFromRouteName(routeName: string): string {
  if (routeName === 'workspaceStyles') return 'styles'
  return routeName
}

/**
 * 更新 mock 路由，模拟真实布局中的路由切换响应。
 * @param route 下一个路由名称、参数和元信息
 */
function setRoute(route: MutableRoute): void {
  if (!routerMock.route) {
    throw new Error('router mock is not initialized')
  }
  routerMock.route.name = route.name
  routerMock.route.params = route.params
  routerMock.route.meta = route.meta
}

/**
 * 渲染带独立查询客户端的后台布局，避免用例之间共享查询缓存。
 */
function renderLayout() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(AdminLayout, {
    global: {
      plugins: [
        [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
      ],
      stubs: {
        AssetManagerPanel: { template: '<aside data-testid="asset-panel" />' },
        ComponentManagerPanel: { template: '<aside data-testid="component-panel" />' },
      },
    },
  })
}
