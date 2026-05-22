/**
 * 文件功能：验证页面截图在列表展示和详情页保存流程中的关键交互。
 */
import { defineComponent, h, onMounted } from 'vue'
import { render, fireEvent, screen, waitFor } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PagesView from '@/views/PagesView.vue'
import PageDetailView from '@/views/PageDetailView.vue'
import { useAuthStore } from '@/stores/auth'

const routeState = {
  params: {
    workspaceId: '11',
    projectId: '21',
    pageId: '31',
  },
}

const pushMock = vi.fn()
const backMock = vi.fn()

const listPagesMock = vi.fn()
const listProjectsMock = vi.fn()
const getWorkspaceMock = vi.fn()
const getPageMock = vi.fn()
const getProjectMock = vi.fn()
const listPageVersionsMock = vi.fn()
const getPageCurrentComponentIndexMock = vi.fn()
const updatePageMock = vi.fn()
const updateProjectMock = vi.fn()
const getProjectRoutesMock = vi.fn()
const replaceProjectRoutesMock = vi.fn()
const copyPageToProjectMock = vi.fn()
const savePageScreenshotMock = vi.fn()
const createProjectPreviewArtifactMock = vi.fn()
const messageSuccessMock = vi.fn()
const messageErrorMock = vi.fn()
const messageInfoMock = vi.fn()
const messageWarningMock = vi.fn()
const anchorClickMock = vi.fn()

const defaultProjectConfigs = {
  page_width: 1600,
  page_height: 900,
  base_font_size: '20px',
  icon_default_stroke_width: 2,
  show_pdf_export_button: true,
  menu_mode: 'preview',
  theme_key: 'lightblue',
  theme_config_yaml: 'themes: {}',
  style_spec_markdown: '',
}

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({
    push: pushMock,
    back: backMock,
  }),
  RouterLink: defineComponent({
    name: 'RouterLinkStub',
    props: {
      to: {
        type: String,
        required: false,
        default: '',
      },
    },
    setup(props, { slots }) {
      return () => h('a', { href: props.to }, slots.default?.())
    },
  }),
}))

vi.mock('@/api/catalog', () => ({
  listPages: (...args: unknown[]) => listPagesMock(...args),
  listProjects: (...args: unknown[]) => listProjectsMock(...args),
  getWorkspace: (...args: unknown[]) => getWorkspaceMock(...args),
  getPage: (...args: unknown[]) => getPageMock(...args),
  getProject: (...args: unknown[]) => getProjectMock(...args),
  listPageVersions: (...args: unknown[]) => listPageVersionsMock(...args),
  getPageCurrentComponentIndex: (...args: unknown[]) => getPageCurrentComponentIndexMock(...args),
  getProjectRoutes: (...args: unknown[]) => getProjectRoutesMock(...args),
  replaceProjectRoutes: (...args: unknown[]) => replaceProjectRoutesMock(...args),
  copyPageToProject: (...args: unknown[]) => copyPageToProjectMock(...args),
  updatePage: (...args: unknown[]) => updatePageMock(...args),
  updateProject: (...args: unknown[]) => updateProjectMock(...args),
  savePageScreenshot: (...args: unknown[]) => savePageScreenshotMock(...args),
  createPageSnapshot: vi.fn(),
  getPageVersionContent: vi.fn(),
  restorePageVersion: vi.fn(),
  createPage: vi.fn(),
}))

vi.mock('@/api/preview', () => ({
  createProjectPreviewArtifact: (...args: unknown[]) => createProjectPreviewArtifactMock(...args),
  createPageVersionPreviewArtifact: vi.fn(),
}))

vi.mock('@/utils/message', () => ({
  Message: {
    success: (...args: unknown[]) => messageSuccessMock(...args),
    error: (...args: unknown[]) => messageErrorMock(...args),
    info: (...args: unknown[]) => messageInfoMock(...args),
    warning: (...args: unknown[]) => messageWarningMock(...args),
  },
  createConfirm: vi.fn().mockResolvedValue(true),
}))

vi.mock('@/components/editor/MonacoCodeEditor.vue', () => ({
  default: defineComponent({
    name: 'MonacoCodeEditorStub',
    props: {
      modelValue: {
        type: String,
        required: false,
        default: '',
      },
    },
    emits: ['update:modelValue', 'dirty-change', 'ready'],
    setup(props, { emit }) {
      onMounted(() => {
        emit('ready', {
          markClean: vi.fn(() => emit('dirty-change', false)),
        })
      })

      function markDirty() {
        emit('update:modelValue', `${props.modelValue}<section>dirty</section>`)
        emit('dirty-change', true)
      }

      return () => h('div', [
        h('button', { type: 'button', onClick: markDirty }, 'monaco-mark-dirty'),
      ])
    },
  }),
}))

vi.mock('@/components/editor/MonacoDiffViewer.vue', () => ({
  default: defineComponent({
    name: 'MonacoDiffViewerStub',
    setup() {
      return () => h('div', 'diff-viewer')
    },
  }),
}))

vi.mock('@/components/agent/AgentConversationPanel.vue', () => ({
  default: defineComponent({
    name: 'AgentConversationPanelStub',
    setup() {
      return () => h('div', 'agent-assistant-stub')
    },
  }),
}))

function createTestingRenderOptions() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
      mutations: {
        retry: false,
      },
    },
  })
  const pinia = createPinia()
  setActivePinia(pinia)
  const authStore = useAuthStore()
  authStore.user = {
    id: 1,
    username: 'admin',
    display_name: '平台系统管理员',
    role: 'platform_admin',
    status: 'active',
    last_login_at: null,
    preview_size_presets: [],
  }

  return {
    global: {
      plugins: [
        pinia,
        [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
      ],
      stubs: {
        teleport: true,
        'router-link': true,
      },
    },
  }
}

function createPageDetailPayload(overrides: Record<string, unknown> = {}) {
  return {
    id: 31,
    code: 'PG202604020001',
    page_content: '<template><SalesCard /><Icon name="home" /></template>',
    current_version_no: 1,
    file_type: 'vue',
    title: '页面详情',
    summary: '摘要',
    status: 'active',
    workspace_id: 11,
    workspace_name: '工作空间 A',
    project_id: 21,
    project_name: '项目 A',
    created_at: '2026-04-02T10:00:00Z',
    updated_at: '2026-04-02T10:00:00Z',
    created_by: 1,
    updated_by: 1,
    screenshot_url: null,
    screenshot_version_no: null,
    screenshot_config_hash: null,
    screenshot_is_latest: false,
    screenshot_updated_at: null,
    is_in_project_route: false,
    route_bindings: [],
    ...overrides,
  }
}

function createPageListPayload(overrides: Record<string, unknown> = {}) {
  return createPageDetailPayload({
    screenshot_config_hash: null,
    ...overrides,
  })
}

describe('page screenshot views', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    anchorClickMock.mockImplementation(() => undefined)
    Object.defineProperty(HTMLAnchorElement.prototype, 'click', { configurable: true, value: anchorClickMock })
    routeState.params.workspaceId = '11'
    routeState.params.projectId = '21'
    routeState.params.pageId = '31'

    listProjectsMock.mockResolvedValue({
      items: [{
        id: 21,
        name: '项目 A',
        code: 'PRJ202604020001',
        status: 'active',
        description: null,
        workspace_id: 11,
        workspace_name: '工作空间 A',
        ...defaultProjectConfigs,
        created_at: '2026-04-02T10:00:00Z',
        updated_at: '2026-04-02T10:00:00Z',
        created_by: 1,
        updated_by: 1,
      }],
      total: 1,
      page: 1,
      page_size: 100,
    })
    getWorkspaceMock.mockResolvedValue({
      id: 11,
      code: 'WS202604020001',
      name: '工作空间 A',
      description: null,
      status: 'active',
      last_opened_at: null,
      default_theme_key: 'lightblue',
      created_at: '2026-04-02T10:00:00Z',
      updated_at: '2026-04-02T10:00:00Z',
      created_by: 1,
      updated_by: 1,
    })
    getProjectMock.mockResolvedValue({
      id: 21,
      workspace_id: 11,
      workspace_name: '工作空间 A',
      code: 'PRJ202604020001',
      name: '项目 A',
      description: null,
      status: 'active',
      ...defaultProjectConfigs,
      created_at: '2026-04-02T10:00:00Z',
      updated_at: '2026-04-02T10:00:00Z',
      created_by: 1,
      updated_by: 1,
    })
    listPageVersionsMock.mockResolvedValue([])
    getPageCurrentComponentIndexMock.mockResolvedValue({
      page_id: 31,
      current_version_no: 1,
      page_version_id: 101,
      components: ['Icon'],
      resources: [{ component_name: 'Icon', resource_attr: 'name', resource_name: 'home' }],
    })
    getProjectRoutesMock.mockResolvedValue({ routes: [] })
    replaceProjectRoutesMock.mockResolvedValue({ routes: [] })
    listPagesMock.mockResolvedValue({
      items: [createPageListPayload()],
      total: 1,
      page: 1,
      page_size: 100,
    })
    updateProjectMock.mockResolvedValue({
      id: 21,
      workspace_id: 11,
      workspace_name: '工作空间 A',
      code: 'PRJ202604020001',
      name: '项目 A',
      description: null,
      status: 'active',
      ...defaultProjectConfigs,
      created_at: '2026-04-02T10:00:00Z',
      updated_at: '2026-04-02T10:00:00Z',
      created_by: 1,
      updated_by: 1,
    })
    copyPageToProjectMock.mockResolvedValue(createPageDetailPayload({
      id: 41,
      code: 'PG202604020041',
      title: '页面复制',
      project_id: 22,
      project_name: '项目 B',
      is_in_project_route: false,
      route_bindings: [],
    }))
    createProjectPreviewArtifactMock.mockResolvedValue({
      preview_url: 'http://runtime.local/__preview?ticket=current',
      artifact_id: 'artifact-1',
      preview_kind: 'page',
      entry_descriptor: {
        entry_type: 'module',
        module_path: 'src/views/PG202604020001.vue',
      },
      viewport_width: 1600,
      viewport_height: 900,
    })
  })

  it('PagesView 应展示页面截图图片', async () => {
    listPagesMock.mockResolvedValue({
      items: [
        {
          id: 31,
          code: 'PG202604020001',
          page_content: '<template><div>demo</div></template>',
          current_version_no: 1,
          file_type: 'vue',
          title: '页面截图',
          summary: '摘要',
          status: 'active',
          workspace_id: 11,
          workspace_name: '工作空间 A',
          project_id: 21,
          project_name: '项目 A',
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:00:00Z',
          created_by: 1,
          updated_by: 1,
          screenshot_url: '/media/page-screenshots/PG202604020001.png?v=1712049120000',
          screenshot_version_no: 1,
          screenshot_is_latest: true,
          screenshot_updated_at: '2026-04-02T10:05:00Z',
          is_in_project_route: true,
          route_bindings: [
            {
              route_id: 101,
              parent_route: null,
              route: 'home',
              full_path: '/home',
            },
          ],
        },
      ],
      total: 1,
      page: 1,
      page_size: 100,
    })

    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('页面截图')).toBeInTheDocument()
    expect(screen.getByAltText('页面截图 截图')).toHaveAttribute('src', '/media/page-screenshots/PG202604020001.png?v=1712049120000')
    expect(screen.getByText('已加入路由')).toBeInTheDocument()
    expect(screen.getByText('1 条路由绑定')).toBeInTheDocument()
    expect(screen.getByText('/home')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '查看页面' })).toBeNull()
    expect(screen.queryByRole('button', { name: '编辑名称和描述' })).toBeNull()

    await fireEvent.click(screen.getByTestId('page-card'))

    expect(pushMock).toHaveBeenCalledWith('/workspaces/11/projects/21/pages/31')
  })

  it('PagesView 页头应支持缓存预览卡片尺寸', async () => {
    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    const standardButton = screen.getByRole('button', { name: '卡片标准' })
    expect(standardButton).toHaveAttribute('aria-pressed', 'true')

    await fireEvent.click(screen.getByRole('button', { name: '卡片超大' }))

    expect(localStorage.getItem('web-presentation:pages-view:preview-card-size')).toBe('huge')
    expect(screen.getByRole('button', { name: '卡片超大' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('PagesView 未加入路由分区应支持批量加入顶层路由', async () => {
    listPagesMock.mockResolvedValue({
      items: [
        createPageListPayload({
          id: 31,
          code: 'PG202604020001',
          title: '未路由 A',
          is_in_project_route: false,
          route_bindings: [],
        }),
        createPageListPayload({
          id: 32,
          code: 'PG202604020002',
          title: '未路由 B',
          is_in_project_route: false,
          route_bindings: [],
        }),
      ],
      total: 2,
      page: 1,
      page_size: 100,
    })

    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('未路由 A')).toBeInTheDocument()
    await fireEvent.click(screen.getByTestId('batch-unrouted-select-all'))
    expect(screen.getByText('已选 2')).toBeInTheDocument()

    await fireEvent.click(screen.getByTestId('batch-unrouted-add-route'))

    await waitFor(() => {
      expect(replaceProjectRoutesMock).toHaveBeenCalledTimes(1)
    })
    expect(replaceProjectRoutesMock.mock.calls[0][0]).toBe(21)
    expect(replaceProjectRoutesMock.mock.calls[0][1]).toEqual({
      routes: [
        expect.objectContaining({ route_type: 'page', route: 'pg202604020001', page_id: 31, order: 10 }),
        expect.objectContaining({ route_type: 'page', route: 'pg202604020002', page_id: 32, order: 20 }),
      ],
    })
    await waitFor(() => {
      expect(messageSuccessMock).toHaveBeenCalledWith('已将 2 个页面加入项目路由。')
    })
  })

  it('PagesView 已加入路由分区应支持批量移出路由', async () => {
    listPagesMock.mockResolvedValue({
      items: [
        createPageListPayload({
          id: 31,
          code: 'PG202604020001',
          title: '路由 A',
          is_in_project_route: true,
          route_bindings: [{ route_id: 101, parent_route: null, route: 'home', full_path: '/home', order: 10 }],
        }),
        createPageListPayload({
          id: 32,
          code: 'PG202604020002',
          title: '路由 B',
          is_in_project_route: true,
          route_bindings: [{ route_id: 102, parent_route: 'chapter', route: 'intro', full_path: '/chapter/intro', parent_order: 20, order: 10 }],
        }),
      ],
      total: 2,
      page: 1,
      page_size: 100,
    })
    getProjectRoutesMock.mockResolvedValue({
      routes: [
        {
          id: 101,
          route_type: 'page',
          route: 'home',
          order: 10,
          icon: null,
          hidden: false,
          page_id: 31,
          page_code: 'PG202604020001',
          page_title: '路由 A',
          display_title: '路由 A',
          children: [],
        },
        {
          id: 201,
          route_type: 'group',
          route: 'chapter',
          order: 20,
          icon: null,
          hidden: false,
          group_title: '章节',
          page_id: null,
          page_code: null,
          page_title: null,
          display_title: '章节',
          children: [
            {
              id: 102,
              route_type: 'page',
              route: 'intro',
              order: 10,
              icon: null,
              hidden: false,
              page_id: 32,
              page_code: 'PG202604020002',
              page_title: '路由 B',
              display_title: '路由 B',
            },
          ],
        },
      ],
    })

    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('路由 A')).toBeInTheDocument()
    await fireEvent.click(screen.getByTestId('batch-routed-select-all'))
    await fireEvent.click(screen.getByTestId('batch-routed-remove-route'))

    await waitFor(() => {
      expect(replaceProjectRoutesMock).toHaveBeenCalledWith(21, { routes: [] })
    })
    await waitFor(() => {
      expect(messageSuccessMock).toHaveBeenCalledWith('已将 2 个页面移出项目路由。')
    })
  })

  it('PagesView 应支持批量复制选中页面到其他项目', async () => {
    listPagesMock.mockResolvedValue({
      items: [
        createPageListPayload({
          id: 31,
          code: 'PG202604020001',
          title: '复制 A',
          is_in_project_route: false,
          route_bindings: [],
        }),
        createPageListPayload({
          id: 32,
          code: 'PG202604020002',
          title: '复制 B',
          is_in_project_route: false,
          route_bindings: [],
        }),
      ],
      total: 2,
      page: 1,
      page_size: 100,
    })
    listProjectsMock.mockResolvedValue({
      items: [
        {
          id: 21,
          name: '项目 A',
          code: 'PRJ202604020001',
          status: 'active',
          description: null,
          workspace_id: 11,
          workspace_name: '工作空间 A',
          ...defaultProjectConfigs,
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:00:00Z',
          created_by: 1,
          updated_by: 1,
        },
        {
          id: 22,
          name: '项目 B',
          code: 'PRJ202604020002',
          status: 'active',
          description: null,
          workspace_id: 11,
          workspace_name: '工作空间 A',
          ...defaultProjectConfigs,
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:00:00Z',
          created_by: 1,
          updated_by: 1,
        },
      ],
      total: 2,
      page: 1,
      page_size: 100,
    })

    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('复制 A')).toBeInTheDocument()
    await fireEvent.click(screen.getByTestId('batch-unrouted-select-all'))
    await fireEvent.click(screen.getByTestId('batch-unrouted-copy'))
    await screen.findByText('项目 B')
    await fireEvent.click(screen.getByRole('button', { name: '批量复制' }))

    await waitFor(() => {
      expect(copyPageToProjectMock).toHaveBeenCalledTimes(2)
    })
    expect(copyPageToProjectMock).toHaveBeenNthCalledWith(1, 31, {
      target_project_id: 22,
      route_placement: 'none',
      parent_route_id: null,
      route: null,
    })
    expect(copyPageToProjectMock).toHaveBeenNthCalledWith(2, 32, {
      target_project_id: 22,
      route_placement: 'none',
      parent_route_id: null,
      route: null,
    })
    await waitFor(() => {
      expect(messageSuccessMock).toHaveBeenCalledWith('批量复制完成 2 个页面。')
    })
  })

  it('PagesView 已加入路由页面应按路由顺序排序', async () => {
    listPagesMock.mockResolvedValue({
      items: [
        {
          id: 31,
          code: 'PG202604020001',
          page_content: '<template><div>second</div></template>',
          current_version_no: 1,
          file_type: 'vue',
          title: '第二页',
          summary: null,
          status: 'active',
          workspace_id: 11,
          workspace_name: '工作空间 A',
          project_id: 21,
          project_name: '项目 A',
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:00:00Z',
          created_by: 1,
          updated_by: 1,
          screenshot_url: null,
          screenshot_version_no: null,
          screenshot_is_latest: false,
          screenshot_updated_at: null,
          is_in_project_route: true,
          route_bindings: [
            {
              route_id: 101,
              parent_route: null,
              route: 'z-second',
              full_path: '/z-second',
              parent_order: null,
              order: 20,
            },
          ],
        },
        {
          id: 32,
          code: 'PG202604020002',
          page_content: '<template><div>first</div></template>',
          current_version_no: 1,
          file_type: 'vue',
          title: '第一页',
          summary: null,
          status: 'active',
          workspace_id: 11,
          workspace_name: '工作空间 A',
          project_id: 21,
          project_name: '项目 A',
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:00:00Z',
          created_by: 1,
          updated_by: 1,
          screenshot_url: null,
          screenshot_version_no: null,
          screenshot_is_latest: false,
          screenshot_updated_at: null,
          is_in_project_route: true,
          route_bindings: [
            {
              route_id: 102,
              parent_route: null,
              route: 'a-first',
              full_path: '/a-first',
              parent_order: null,
              order: 10,
            },
          ],
        },
        {
          id: 33,
          code: 'PG202604020003',
          page_content: '<template><div>third</div></template>',
          current_version_no: 1,
          file_type: 'vue',
          title: '分组页',
          summary: null,
          status: 'active',
          workspace_id: 11,
          workspace_name: '工作空间 A',
          project_id: 21,
          project_name: '项目 A',
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:00:00Z',
          created_by: 1,
          updated_by: 1,
          screenshot_url: null,
          screenshot_version_no: null,
          screenshot_is_latest: false,
          screenshot_updated_at: null,
          is_in_project_route: true,
          route_bindings: [
            {
              route_id: 103,
              parent_route: 'chapter',
              route: 'child',
              full_path: '/chapter/child',
              parent_order: 30,
              order: 1,
            },
          ],
        },
      ],
      total: 3,
      page: 1,
      page_size: 100,
    })

    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('第一页')).toBeInTheDocument()
    const cardTexts = screen.getAllByTestId('page-card').map(card => card.textContent ?? '')
    expect(cardTexts[0]).toContain('第一页')
    expect(cardTexts[1]).toContain('第二页')
    expect(cardTexts[2]).toContain('分组页')
  })

  it('PagesView 应在未加入路由分区展示页面截图', async () => {
    listPagesMock.mockResolvedValue({
      items: [
        {
          id: 31,
          code: 'PG202604020001',
          page_content: '<template><div>demo</div></template>',
          current_version_no: 2,
          file_type: 'vue',
          title: '旧截图页面',
          summary: '摘要',
          status: 'active',
          workspace_id: 11,
          workspace_name: '工作空间 A',
          project_id: 21,
          project_name: '项目 A',
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:10:00Z',
          created_by: 1,
          updated_by: 1,
          screenshot_url: '/media/page-screenshots/PG202604020001.png?v=1712049120000',
          screenshot_version_no: 1,
          screenshot_is_latest: false,
          screenshot_updated_at: '2026-04-02T10:05:00Z',
          is_in_project_route: false,
          route_bindings: [],
        },
      ],
      total: 1,
      page: 1,
      page_size: 100,
    })

    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('旧截图页面')).toBeInTheDocument()
    expect(screen.getByText('未加入路由')).toBeInTheDocument()
    expect(screen.getByAltText('旧截图页面 截图')).toHaveAttribute('src', '/media/page-screenshots/PG202604020001.png?v=1712049120000')
  })

  it('PagesView 卡片应支持调用后端更新截图', async () => {
    listPagesMock.mockResolvedValue({
      items: [
        {
          id: 31,
          code: 'PG202604020001',
          page_content: '<template><div>demo</div></template>',
          current_version_no: 2,
          file_type: 'vue',
          title: '待更新截图',
          summary: '摘要',
          status: 'active',
          workspace_id: 11,
          workspace_name: '工作空间 A',
          project_id: 21,
          project_name: '项目 A',
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:10:00Z',
          created_by: 1,
          updated_by: 1,
          screenshot_url: '/media/page-screenshots/PG202604020001.png?v=1712049120000',
          screenshot_version_no: 1,
          screenshot_is_latest: false,
          screenshot_updated_at: '2026-04-02T10:05:00Z',
          is_in_project_route: false,
          route_bindings: [],
        },
      ],
      total: 1,
      page: 1,
      page_size: 100,
    })
    savePageScreenshotMock.mockResolvedValue({
      id: 31,
      code: 'PG202604020001',
      page_content: '<template><div>demo</div></template>',
      current_version_no: 2,
      file_type: 'vue',
      title: '待更新截图',
      summary: '摘要',
      status: 'active',
      workspace_id: 11,
      workspace_name: '工作空间 A',
      project_id: 21,
      project_name: '项目 A',
      created_at: '2026-04-02T10:00:00Z',
      updated_at: '2026-04-02T10:10:00Z',
      created_by: 1,
      updated_by: 1,
      screenshot_url: '/media/page-screenshots/PG202604020001.png?v=1712049720000',
      screenshot_version_no: 2,
      screenshot_is_latest: true,
      screenshot_updated_at: '2026-04-02T10:12:00Z',
      is_in_project_route: false,
      route_bindings: [],
    })

    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('待更新截图')).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '更新截图' }))

    await waitFor(() => {
      expect(savePageScreenshotMock).toHaveBeenCalledWith(31)
    })
    expect(pushMock).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(messageSuccessMock).toHaveBeenCalledWith('「待更新截图」截图已更新。')
    })
  })

  it('PagesView 应支持批量刷新缺失或旧截图', async () => {
    listPagesMock.mockResolvedValue({
      items: [
        {
          id: 31,
          code: 'PG202604020001',
          page_content: '<template><div>demo</div></template>',
          current_version_no: 2,
          file_type: 'vue',
          title: '待批量更新截图',
          summary: '摘要',
          status: 'active',
          workspace_id: 11,
          workspace_name: '工作空间 A',
          project_id: 21,
          project_name: '项目 A',
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:10:00Z',
          created_by: 1,
          updated_by: 1,
          screenshot_url: '/media/page-screenshots/PG202604020001.png?v=1712049120000',
          screenshot_version_no: 1,
          screenshot_config_hash: 'old-config',
          screenshot_is_latest: false,
          screenshot_updated_at: '2026-04-02T10:05:00Z',
          is_in_project_route: false,
          route_bindings: [],
        },
        {
          id: 32,
          code: 'PG202604020002',
          page_content: '<template><div>missing</div></template>',
          current_version_no: 1,
          file_type: 'vue',
          title: '缺失截图页面',
          summary: '摘要',
          status: 'active',
          workspace_id: 11,
          workspace_name: '工作空间 A',
          project_id: 21,
          project_name: '项目 A',
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:10:00Z',
          created_by: 1,
          updated_by: 1,
          screenshot_url: null,
          screenshot_version_no: null,
          screenshot_config_hash: null,
          screenshot_is_latest: false,
          screenshot_updated_at: null,
          is_in_project_route: false,
          route_bindings: [],
        },
      ],
      total: 2,
      page: 1,
      page_size: 100,
    })
    savePageScreenshotMock.mockResolvedValue({})

    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('待批量更新截图')).toBeInTheDocument()
    expect(await screen.findByText('缺失截图页面')).toBeInTheDocument()
    await fireEvent.click(screen.getByTestId('batch-refresh-unrouted-page-screenshots'))

    await waitFor(() => {
      expect(savePageScreenshotMock).toHaveBeenCalledTimes(2)
    })
    expect(savePageScreenshotMock).toHaveBeenNthCalledWith(1, 31)
    expect(savePageScreenshotMock).toHaveBeenNthCalledWith(2, 32)
    await waitFor(() => {
      expect(messageSuccessMock).toHaveBeenCalledWith('批量截图完成 2 个页面。')
    })
  })

  it('PagesView 无需刷新的 Vue 截图时应禁用刷新截图按钮', async () => {
    listPagesMock.mockResolvedValue({
      items: [
        {
          id: 31,
          code: 'PG202604020001',
          page_content: '<template><div>latest</div></template>',
          current_version_no: 1,
          file_type: 'vue',
          title: '最新截图页面',
          summary: '摘要',
          status: 'active',
          workspace_id: 11,
          workspace_name: '工作空间 A',
          project_id: 21,
          project_name: '项目 A',
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:10:00Z',
          created_by: 1,
          updated_by: 1,
          screenshot_url: '/media/page-screenshots/PG202604020001.png?v=1712049120000',
          screenshot_version_no: 1,
          screenshot_config_hash: 'current-config',
          screenshot_is_latest: true,
          screenshot_updated_at: '2026-04-02T10:05:00Z',
          is_in_project_route: false,
          route_bindings: [],
        },
        {
          id: 32,
          code: 'PG202604020002',
          page_content: 'export const value = 1',
          current_version_no: 1,
          file_type: 'ts',
          title: '非 Vue 缺失截图页面',
          summary: '摘要',
          status: 'active',
          workspace_id: 11,
          workspace_name: '工作空间 A',
          project_id: 21,
          project_name: '项目 A',
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:10:00Z',
          created_by: 1,
          updated_by: 1,
          screenshot_url: null,
          screenshot_version_no: null,
          screenshot_config_hash: null,
          screenshot_is_latest: false,
          screenshot_updated_at: null,
          is_in_project_route: false,
          route_bindings: [],
        },
      ],
      total: 2,
      page: 1,
      page_size: 100,
    })

    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('最新截图页面')).toBeInTheDocument()
    expect(screen.getByTestId('batch-refresh-unrouted-page-screenshots')).toBeDisabled()
  })

  it('PagesView 应支持页面归档与归档弹窗恢复', async () => {
    listPagesMock.mockImplementation((params: { status?: string }) => {
      if (params.status === 'archived') {
        return Promise.resolve({
          items: [
            {
              id: 32,
              code: 'PG202604020002',
              page_content: '<template><div>archived</div></template>',
              current_version_no: 1,
              file_type: 'vue',
              title: '归档页面',
              summary: '归档摘要',
              status: 'archived',
              workspace_id: 11,
              workspace_name: '工作空间 A',
              project_id: 21,
              project_name: '项目 A',
              created_at: '2026-04-02T09:00:00Z',
              updated_at: '2026-04-02T10:20:00Z',
              created_by: 1,
              updated_by: 1,
              screenshot_url: '/media/page-screenshots/PG202604020002.png?v=1712049660000',
              screenshot_version_no: 1,
              screenshot_is_latest: true,
              screenshot_updated_at: '2026-04-02T10:21:00Z',
              is_in_project_route: false,
              route_bindings: [],
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        })
      }

      return Promise.resolve({
        items: [
          {
            id: 31,
            code: 'PG202604020001',
            page_content: '<template><div>demo</div></template>',
            current_version_no: 1,
            file_type: 'vue',
            title: '当前页面',
            summary: '摘要',
            status: 'active',
            workspace_id: 11,
            workspace_name: '工作空间 A',
            project_id: 21,
            project_name: '项目 A',
            created_at: '2026-04-02T10:00:00Z',
            updated_at: '2026-04-02T10:00:00Z',
            created_by: 1,
            updated_by: 1,
            screenshot_url: null,
            screenshot_version_no: null,
            screenshot_is_latest: false,
            screenshot_updated_at: null,
            is_in_project_route: false,
            route_bindings: [],
          },
        ],
        total: 1,
        page: 1,
        page_size: 100,
      })
    })
    updatePageMock.mockResolvedValue({
      id: 31,
      code: 'PG202604020001',
      page_content: '<template><div>demo</div></template>',
      current_version_no: 1,
      file_type: 'vue',
      title: '当前页面',
      summary: '摘要',
      status: 'archived',
      workspace_id: 11,
      workspace_name: '工作空间 A',
      project_id: 21,
      project_name: '项目 A',
      created_at: '2026-04-02T10:00:00Z',
      updated_at: '2026-04-02T10:00:00Z',
      created_by: 1,
      updated_by: 1,
      screenshot_url: null,
      screenshot_version_no: null,
      screenshot_is_latest: false,
      screenshot_updated_at: null,
      is_in_project_route: false,
      route_bindings: [],
    })

    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('当前页面')).toBeInTheDocument()
    const archiveButtons = screen.getAllByRole('button', { name: '归档页面' })
    await fireEvent.click(archiveButtons[1])

    await waitFor(() => {
      expect(updatePageMock).toHaveBeenCalledWith(31, { status: 'archived' })
    })

    await fireEvent.click(archiveButtons[0])

    expect((await screen.findAllByText('归档页面')).length).toBeGreaterThan(0)
    expect(await screen.findByAltText('归档页面 最新截图')).toHaveAttribute('src', '/media/page-screenshots/PG202604020002.png?v=1712049660000')

    await fireEvent.click(screen.getByRole('button', { name: '恢复' }))

    await waitFor(() => {
      expect(updatePageMock).toHaveBeenCalledWith(32, { status: 'active' })
    })
  })

  it('PagesView 整项目预览应交由后端选择默认入口路由', async () => {
    listPagesMock.mockResolvedValue({
      items: [
        {
          id: 31,
          code: 'PG202604020001',
          page_content: '<template><div>demo</div></template>',
          current_version_no: 1,
          file_type: 'vue',
          title: '项目首页',
          summary: '摘要',
          status: 'active',
          workspace_id: 11,
          workspace_name: '工作空间 A',
          project_id: 21,
          project_name: '项目 A',
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:00:00Z',
          created_by: 1,
          updated_by: 1,
          screenshot_url: null,
          screenshot_version_no: null,
          screenshot_is_latest: false,
          screenshot_updated_at: null,
          is_in_project_route: true,
          route_bindings: [
            {
              route_id: 101,
              parent_route: null,
              route: 'home',
              full_path: '/home',
            },
          ],
        },
      ],
      total: 1,
      page: 1,
      page_size: 100,
    })
    const windowOpenMock = vi.spyOn(window, 'open').mockImplementation(() => null)

    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('项目首页')).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: /^预览$/ }))

    await waitFor(() => {
      expect(createProjectPreviewArtifactMock).toHaveBeenCalledWith(21)
    })
    expect(windowOpenMock).toHaveBeenCalledWith('http://runtime.local/__preview?ticket=current', '_blank')
    windowOpenMock.mockRestore()
  })

  it('PagesView 收到智能体创建页面事件后应刷新列表并跳转新页面', async () => {
    listPagesMock
      .mockResolvedValueOnce({
        items: [],
        total: 0,
        page: 1,
        page_size: 100,
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: 42,
            code: 'PG202604020042',
            page_content: '<template><div>created</div></template>',
            current_version_no: 1,
            file_type: 'vue',
            title: '智能体创建页面',
            summary: null,
            status: 'active',
            workspace_id: 11,
            workspace_name: '工作空间 A',
            project_id: 21,
            project_name: '项目 A',
            created_at: '2026-04-02T10:30:00Z',
            updated_at: '2026-04-02T10:30:00Z',
            created_by: 1,
            updated_by: 1,
            screenshot_url: null,
            screenshot_version_no: null,
            screenshot_is_latest: false,
            screenshot_updated_at: null,
            is_in_project_route: false,
            route_bindings: [],
          },
        ],
        total: 1,
        page: 1,
        page_size: 100,
      })

    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('未加入路由')).toBeInTheDocument()
    window.dispatchEvent(new CustomEvent('agent:project-pages-updated', {
      detail: {
        workspaceId: 11,
        projectId: 21,
        pageId: 42,
        toolName: 'create_project_page',
        result: { success: true, page_id: 42 },
      },
    }))

    await waitFor(() => {
      expect(listPagesMock.mock.calls.length).toBeGreaterThanOrEqual(2)
      expect(pushMock).toHaveBeenCalledWith('/workspaces/11/projects/21/pages/42')
    })
  })

  it('PagesView 收到智能体项目配置事件后应刷新项目详情', async () => {
    render(PagesView, createTestingRenderOptions())

    expect(await screen.findByText('项目 A')).toBeInTheDocument()
    getProjectMock.mockResolvedValueOnce({
      id: 21,
      workspace_id: 11,
      workspace_name: '工作空间 A',
      code: 'PRJ202604020001',
      name: '智能体更新项目',
      description: '样式配置已刷新',
      status: 'active',
      ...defaultProjectConfigs,
      created_at: '2026-04-02T10:00:00Z',
      updated_at: '2026-04-02T10:30:00Z',
      created_by: 1,
      updated_by: 1,
    })

    window.dispatchEvent(new CustomEvent('agent:project-updated', {
      detail: {
        workspaceId: 11,
        projectId: 21,
        toolName: 'update_project_style_config',
        result: { success: true, project_id: 21 },
      },
    }))

    await waitFor(() => {
      expect(getProjectMock.mock.calls.length).toBeGreaterThanOrEqual(2)
      expect(screen.getByText('智能体更新项目')).toBeInTheDocument()
    })
  })

  it('PageDetailView 收到智能体页面写回事件后应刷新详情并重建 Runtime 预览', async () => {
    getPageMock
      .mockResolvedValueOnce({
        id: 31,
        code: 'PG202604020001',
        page_content: '<template><div>old</div></template>',
        current_version_no: 1,
        file_type: 'vue',
        title: '页面详情',
        summary: '摘要',
        status: 'active',
        workspace_id: 11,
        workspace_name: '工作空间 A',
        project_id: 21,
        project_name: '项目 A',
        created_at: '2026-04-02T10:00:00Z',
        updated_at: '2026-04-02T10:00:00Z',
        created_by: 1,
        updated_by: 1,
        screenshot_url: null,
        screenshot_version_no: null,
        screenshot_is_latest: false,
        screenshot_updated_at: null,
        is_in_project_route: false,
        route_bindings: [],
      })
      .mockResolvedValueOnce({
        id: 31,
        code: 'PG202604020001',
        page_content: '<template><div>agent updated</div></template>',
        current_version_no: 2,
        file_type: 'vue',
        title: '智能体更新后',
        summary: '摘要',
        status: 'active',
        workspace_id: 11,
        workspace_name: '工作空间 A',
        project_id: 21,
        project_name: '项目 A',
        created_at: '2026-04-02T10:00:00Z',
        updated_at: '2026-04-02T10:20:00Z',
        created_by: 1,
        updated_by: 1,
        screenshot_url: null,
        screenshot_version_no: null,
        screenshot_is_latest: false,
        screenshot_updated_at: null,
        is_in_project_route: false,
        route_bindings: [],
      })

    render(PageDetailView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    await waitFor(() => {
      expect(createProjectPreviewArtifactMock).toHaveBeenCalledWith(21, 'src/views/PG202604020001.vue')
    })
    createProjectPreviewArtifactMock.mockClear()

    window.dispatchEvent(new CustomEvent('agent:page-updated', {
      detail: {
        workspaceId: 11,
        projectId: 21,
        pageId: 31,
        toolName: 'apply_page_edits',
        result: { success: true, page_id: 31 },
      },
    }))

    await waitFor(() => {
      expect(getPageMock).toHaveBeenCalledTimes(2)
      expect(createProjectPreviewArtifactMock).toHaveBeenCalledWith(21, 'src/views/PG202604020001.vue')
      expect(screen.getByText('智能体更新后')).toBeInTheDocument()
    })
    expect(screen.getByTitle('runtime-preview')).toHaveAttribute('src', expect.stringContaining('http://runtime.local/__preview?ticket=current&t='))
  })

  it('PageDetailView 收到项目页面列表事件后应刷新当前页详情但不重建 Runtime 预览', async () => {
    getPageMock
      .mockResolvedValueOnce(createPageDetailPayload())
      .mockResolvedValueOnce(createPageDetailPayload({
        title: '路由刷新后的页面',
        is_in_project_route: true,
        route_bindings: [{ route_id: 101, parent_route: null, route: 'home', full_path: '/home' }],
      }))

    render(PageDetailView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    await waitFor(() => {
      expect(createProjectPreviewArtifactMock).toHaveBeenCalledWith(21, 'src/views/PG202604020001.vue')
    })
    createProjectPreviewArtifactMock.mockClear()

    window.dispatchEvent(new CustomEvent('agent:project-pages-updated', {
      detail: {
        workspaceId: 11,
        projectId: 21,
        toolName: 'apply_project_route_tree',
        result: { success: true },
      },
    }))

    await waitFor(() => {
      expect(getPageMock).toHaveBeenCalledTimes(2)
      expect(screen.getByText('路由刷新后的页面')).toBeInTheDocument()
    })
    expect(createProjectPreviewArtifactMock).not.toHaveBeenCalled()
  })

  it('PageDetailView 收到截图刷新事件后只刷新页面数据，不重建 Runtime 预览', async () => {
    getPageMock
      .mockResolvedValueOnce(createPageDetailPayload())
      .mockResolvedValueOnce(createPageDetailPayload({
        screenshot_url: '/media/page-screenshots/PG202604020001.png?v=1712049300000',
        screenshot_version_no: 1,
        screenshot_is_latest: true,
        screenshot_updated_at: '2026-04-02T10:30:00Z',
      }))

    render(PageDetailView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    await waitFor(() => {
      expect(createProjectPreviewArtifactMock).toHaveBeenCalledWith(21, 'src/views/PG202604020001.vue')
    })
    createProjectPreviewArtifactMock.mockClear()

    window.dispatchEvent(new CustomEvent('agent:page-updated', {
      detail: {
        workspaceId: 11,
        projectId: 21,
        pageId: 31,
        toolName: 'get_page_screenshot',
        result: { success: true, page_id: 31, screenshot_refreshed: true },
      },
    }))
    window.dispatchEvent(new CustomEvent('agent:project-pages-updated', {
      detail: {
        workspaceId: 11,
        projectId: 21,
        pageId: 31,
        toolName: 'get_page_screenshot',
        result: { success: true, page_id: 31, screenshot_refreshed: true },
      },
    }))

    await waitFor(() => {
      expect(getPageMock).toHaveBeenCalledTimes(2)
    })
    expect(createProjectPreviewArtifactMock).not.toHaveBeenCalled()
  })

  it('PageDetailView 预览与编辑器模式应展示不同页头操作并隐藏状态元信息', async () => {
    getPageMock.mockResolvedValue(createPageDetailPayload())

    render(PageDetailView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    expect(screen.getByText('摘要')).toBeInTheDocument()
    expect(screen.queryByText('.vue')).toBeNull()
    expect(screen.queryByText('启用')).toBeNull()
    expect(screen.queryByText('未修改')).toBeNull()
    expect(screen.queryByText(/最近更新/)).toBeNull()

    expect(screen.getByRole('button', { name: '上一页' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '下一页' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '版本' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '截图' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '资源' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '复制' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '保存' })).toBeNull()
    expect(screen.queryByRole('button', { name: '刷新' })).toBeNull()

    await fireEvent.click(screen.getByRole('button', { name: '编辑器' }))

    expect(screen.getByRole('button', { name: '版本' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '资源' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '上一页' })).toBeNull()
    expect(screen.queryByRole('button', { name: '下一页' })).toBeNull()
    expect(screen.queryByRole('button', { name: '截图' })).toBeNull()
    expect(screen.queryByRole('button', { name: '复制' })).toBeNull()
    expect(screen.queryByRole('button', { name: '刷新' })).toBeNull()
  })

  it('PageDetailView 应在详情页编辑页面名称和描述', async () => {
    getPageMock.mockResolvedValue(createPageDetailPayload())
    updatePageMock.mockResolvedValue(createPageDetailPayload({
      title: '页面详情新标题',
      summary: '新摘要',
    }))

    render(PageDetailView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '编辑页面名称和描述' }))
    await fireEvent.update(screen.getByPlaceholderText('请输入页面名称'), '页面详情新标题')
    await fireEvent.update(screen.getByPlaceholderText('补充页面用途、关键内容或使用约束'), '新摘要')
    await fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(updatePageMock).toHaveBeenCalledWith(31, {
        title: '页面详情新标题',
        summary: '新摘要',
      })
    })
    await waitFor(() => {
      expect(messageSuccessMock).toHaveBeenCalledWith('页面信息已更新。')
      expect(screen.getByText('页面详情新标题')).toBeInTheDocument()
    })
  })

  it('PageDetailView 从编辑器切换到预览时应先保存再刷新预览', async () => {
    getPageMock.mockResolvedValue(createPageDetailPayload())
    updatePageMock.mockResolvedValue(createPageDetailPayload({
      page_content: '<template><SalesCard /><Icon name="home" /></template><section>dirty</section>',
      current_version_no: 2,
      updated_at: '2026-04-02T10:10:00Z',
    }))

    render(PageDetailView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    await waitFor(() => {
      expect(createProjectPreviewArtifactMock).toHaveBeenCalledWith(21, 'src/views/PG202604020001.vue')
    })
    createProjectPreviewArtifactMock.mockClear()

    await fireEvent.click(screen.getByRole('button', { name: '编辑器' }))
    await fireEvent.click(screen.getByRole('button', { name: 'monaco-mark-dirty' }))
    await fireEvent.click(screen.getByRole('button', { name: '预览' }))

    await waitFor(() => {
      expect(updatePageMock).toHaveBeenCalledWith(31, {
        page_content: '<template><SalesCard /><Icon name="home" /></template><section>dirty</section>',
        file_type: 'vue',
      })
      expect(createProjectPreviewArtifactMock).toHaveBeenCalledWith(21, 'src/views/PG202604020001.vue')
    })
    expect(updatePageMock.mock.invocationCallOrder[0]).toBeLessThan(createProjectPreviewArtifactMock.mock.invocationCallOrder[0])
    expect(await screen.findByTitle('runtime-preview')).toHaveAttribute('src', expect.stringContaining('http://runtime.local/__preview?ticket=current&t='))
  })

  it('PageDetailView 已加入路由页面应按路由顺序翻页', async () => {
    getPageMock.mockResolvedValue(createPageDetailPayload({
      is_in_project_route: true,
      route_bindings: [{ route_id: 102, parent_route: null, route: 'middle', full_path: '/middle', parent_order: null, order: 20 }],
    }))
    listPagesMock.mockResolvedValue({
      items: [
        createPageListPayload({
          id: 30,
          code: 'PG202604020000',
          title: '前一页',
          is_in_project_route: true,
          route_bindings: [{ route_id: 101, parent_route: null, route: 'first', full_path: '/first', parent_order: null, order: 10 }],
        }),
        createPageListPayload({
          id: 31,
          code: 'PG202604020001',
          title: '当前页',
          is_in_project_route: true,
          route_bindings: [{ route_id: 102, parent_route: null, route: 'middle', full_path: '/middle', parent_order: null, order: 20 }],
        }),
        createPageListPayload({
          id: 32,
          code: 'PG202604020002',
          title: '后一页',
          is_in_project_route: true,
          route_bindings: [{ route_id: 103, parent_route: 'chapter', route: 'last', full_path: '/chapter/last', parent_order: 30, order: 10 }],
        }),
      ],
      total: 3,
      page: 1,
      page_size: 100,
    })

    render(PageDetailView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '上一页' })).toBeEnabled()
      expect(screen.getByRole('button', { name: '下一页' })).toBeEnabled()
    })

    await fireEvent.click(screen.getByRole('button', { name: '上一页' }))
    await fireEvent.click(screen.getByRole('button', { name: '下一页' }))

    expect(pushMock).toHaveBeenCalledWith('/workspaces/11/projects/21/pages/30')
    expect(pushMock).toHaveBeenCalledWith('/workspaces/11/projects/21/pages/32')
  })

  it('PageDetailView 未加入路由页面应按 page_code 升序翻页', async () => {
    getPageMock.mockResolvedValue(createPageDetailPayload({
      code: 'page_b',
      is_in_project_route: false,
      route_bindings: [],
    }))
    listPagesMock.mockResolvedValue({
      items: [
        createPageListPayload({ id: 31, code: 'page_b', title: '当前页', is_in_project_route: false, route_bindings: [] }),
        createPageListPayload({ id: 32, code: 'page_c', title: '后一页', is_in_project_route: false, route_bindings: [] }),
        createPageListPayload({ id: 30, code: 'page_a', title: '前一页', is_in_project_route: false, route_bindings: [] }),
        createPageListPayload({
          id: 40,
          code: 'page_routed',
          title: '路由页',
          is_in_project_route: true,
          route_bindings: [{ route_id: 201, parent_route: null, route: 'routed', full_path: '/routed', parent_order: null, order: 10 }],
        }),
      ],
      total: 4,
      page: 1,
      page_size: 100,
    })
    createProjectPreviewArtifactMock.mockResolvedValue({
      preview_url: 'http://runtime.local/__preview?ticket=current',
      artifact_id: 'artifact-1',
      preview_kind: 'page',
      entry_descriptor: {
        entry_type: 'module',
        module_path: 'src/views/page_b.vue',
      },
      viewport_width: 1600,
      viewport_height: 900,
    })

    render(PageDetailView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '上一页' })).toBeEnabled()
      expect(screen.getByRole('button', { name: '下一页' })).toBeEnabled()
    })

    await fireEvent.click(screen.getByRole('button', { name: '上一页' }))
    await fireEvent.click(screen.getByRole('button', { name: '下一页' }))

    expect(pushMock).toHaveBeenCalledWith('/workspaces/11/projects/21/pages/30')
    expect(pushMock).toHaveBeenCalledWith('/workspaces/11/projects/21/pages/32')
  })

  it('PageDetailView 收到当前页引用组件更新事件后应重建 Runtime 预览', async () => {
    getPageMock.mockResolvedValue(createPageDetailPayload())
    getPageCurrentComponentIndexMock.mockResolvedValue({
      page_id: 31,
      current_version_no: 1,
      page_version_id: 101,
      components: ['SalesCard'],
      resources: [],
    })

    render(PageDetailView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    await waitFor(() => {
      expect(createProjectPreviewArtifactMock).toHaveBeenCalledWith(21, 'src/views/PG202604020001.vue')
    })
    await waitFor(() => {
      expect(getPageCurrentComponentIndexMock).toHaveBeenCalled()
    })
    createProjectPreviewArtifactMock.mockClear()

    window.dispatchEvent(new CustomEvent('agent:component-updated', {
      detail: {
        workspaceId: 11,
        projectId: 21,
        toolName: 'publish_component',
        result: {
          success: true,
          component: {
            id: 99,
            import_name: 'SalesCard',
          },
        },
      },
    }))

    await waitFor(() => {
      expect(createProjectPreviewArtifactMock).toHaveBeenCalledWith(21, 'src/views/PG202604020001.vue')
    })
  })

  it('PageDetailView 收到无关组件更新事件后不应重建 Runtime 预览', async () => {
    getPageMock.mockResolvedValue(createPageDetailPayload())
    getPageCurrentComponentIndexMock.mockResolvedValue({
      page_id: 31,
      current_version_no: 1,
      page_version_id: 101,
      components: ['SalesCard'],
      resources: [],
    })

    render(PageDetailView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    await waitFor(() => {
      expect(createProjectPreviewArtifactMock).toHaveBeenCalledWith(21, 'src/views/PG202604020001.vue')
    })
    await waitFor(() => {
      expect(getPageCurrentComponentIndexMock).toHaveBeenCalled()
    })
    createProjectPreviewArtifactMock.mockClear()

    window.dispatchEvent(new CustomEvent('agent:component-updated', {
      detail: {
        workspaceId: 11,
        projectId: 21,
        toolName: 'apply_component_edits',
        result: {
          success: true,
          component: {
            id: 100,
            import_name: 'OtherCard',
          },
        },
      },
    }))
    await Promise.resolve()

    expect(createProjectPreviewArtifactMock).not.toHaveBeenCalled()
  })

  it('PageDetailView 收到当前页引用资源更新事件后应重建 Runtime 预览', async () => {
    getPageMock.mockResolvedValue(createPageDetailPayload())
    getPageCurrentComponentIndexMock.mockResolvedValue({
      page_id: 31,
      current_version_no: 1,
      page_version_id: 101,
      components: [],
      resources: [{ component_name: 'Icon', resource_attr: 'name', resource_name: 'home' }],
    })

    render(PageDetailView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    await waitFor(() => {
      expect(createProjectPreviewArtifactMock).toHaveBeenCalledWith(21, 'src/views/PG202604020001.vue')
    })
    await waitFor(() => {
      expect(getPageCurrentComponentIndexMock).toHaveBeenCalled()
    })
    createProjectPreviewArtifactMock.mockClear()

    window.dispatchEvent(new CustomEvent('agent:asset-updated', {
      detail: {
        workspaceId: 11,
        projectId: 21,
        toolName: 'apply_resource_content_diff',
        result: {
          success: true,
          asset: {
            id: 8,
            name: 'home',
          },
        },
      },
    }))

    await waitFor(() => {
      expect(createProjectPreviewArtifactMock).toHaveBeenCalledWith(21, 'src/views/PG202604020001.vue')
    })
  })

  it('PageDetailView 复制页面成功后应跳转到目标项目新页面', async () => {
    getPageMock.mockResolvedValue(createPageDetailPayload())
    listProjectsMock.mockResolvedValue({
      items: [
        {
          id: 21,
          name: '项目 A',
          code: 'PRJ202604020001',
          status: 'active',
          description: null,
          workspace_id: 11,
          workspace_name: '工作空间 A',
          ...defaultProjectConfigs,
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:00:00Z',
          created_by: 1,
          updated_by: 1,
        },
        {
          id: 22,
          name: '项目 B',
          code: 'PRJ202604020002',
          status: 'active',
          description: null,
          workspace_id: 11,
          workspace_name: '工作空间 A',
          ...defaultProjectConfigs,
          created_at: '2026-04-02T10:00:00Z',
          updated_at: '2026-04-02T10:00:00Z',
          created_by: 1,
          updated_by: 1,
        },
      ],
      total: 2,
      page: 1,
      page_size: 100,
    })

    render(PageDetailView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '复制' }))
    await screen.findByText('项目 B')
    await fireEvent.click(screen.getByRole('button', { name: '复制页面' }))

    await waitFor(() => {
      expect(copyPageToProjectMock).toHaveBeenCalledWith(31, {
        target_project_id: 22,
        title: '页面详情',
        summary: '摘要',
        route_placement: 'none',
        parent_route_id: null,
        route: null,
      })
    })
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/workspaces/11/projects/22/pages/41')
    })
  })

  it('PageDetailView 重新截图时应先保存未保存修改再调用截图接口', async () => {
    getPageMock.mockResolvedValue({
      id: 31,
      code: 'PG202604020001',
      page_content: '<template><div>demo</div></template>',
      current_version_no: 1,
      file_type: 'vue',
      title: '页面详情',
      summary: '摘要',
      status: 'active',
      workspace_id: 11,
      workspace_name: '工作空间 A',
      project_id: 21,
      project_name: '项目 A',
      created_at: '2026-04-02T10:00:00Z',
      updated_at: '2026-04-02T10:00:00Z',
      created_by: 1,
      updated_by: 1,
      screenshot_url: null,
      screenshot_version_no: null,
      screenshot_is_latest: false,
      screenshot_updated_at: null,
      is_in_project_route: false,
      route_bindings: [],
    })
    updatePageMock.mockResolvedValue({
      id: 31,
      code: 'PG202604020001',
      page_content: '<template><div>demo</div></template><section>dirty</section>',
      current_version_no: 2,
      file_type: 'vue',
      title: '页面详情',
      summary: '摘要',
      status: 'active',
      workspace_id: 11,
      workspace_name: '工作空间 A',
      project_id: 21,
      project_name: '项目 A',
      created_at: '2026-04-02T10:00:00Z',
      updated_at: '2026-04-02T10:10:00Z',
      created_by: 1,
      updated_by: 1,
      screenshot_url: null,
      screenshot_version_no: null,
      screenshot_is_latest: false,
      screenshot_updated_at: null,
      is_in_project_route: false,
      route_bindings: [],
    })
    savePageScreenshotMock.mockResolvedValue({
      id: 31,
      code: 'PG202604020001',
      page_content: '<template><div>demo</div></template><section>dirty</section>',
      current_version_no: 2,
      file_type: 'vue',
      title: '页面详情',
      summary: '摘要',
      status: 'active',
      workspace_id: 11,
      workspace_name: '工作空间 A',
      project_id: 21,
      project_name: '项目 A',
      created_at: '2026-04-02T10:00:00Z',
      updated_at: '2026-04-02T10:10:00Z',
      created_by: 1,
      updated_by: 1,
      screenshot_url: '/media/page-screenshots/PG202604020001.png?v=1712049720000',
      screenshot_version_no: 2,
      screenshot_is_latest: true,
      screenshot_updated_at: '2026-04-02T10:12:00Z',
      is_in_project_route: false,
      route_bindings: [],
    })

    render(PageDetailView, createTestingRenderOptions())

    expect(await screen.findByText('页面详情')).toBeInTheDocument()
    await waitFor(() => {
      expect(createProjectPreviewArtifactMock).toHaveBeenCalled()
    })

    await fireEvent.click(screen.getByRole('button', { name: '编辑器' }))
    await fireEvent.click(screen.getByRole('button', { name: 'monaco-mark-dirty' }))
    await fireEvent.click(screen.getByRole('button', { name: '预览' }))
    await waitFor(() => {
      expect(updatePageMock).toHaveBeenCalledTimes(1)
      expect(screen.getByRole('button', { name: '截图' })).toBeInTheDocument()
    })
    await fireEvent.click(screen.getByRole('button', { name: '截图' }))
    await fireEvent.click(screen.getByRole('button', { name: /重新截图/ }))

    await waitFor(() => {
      expect(updatePageMock).toHaveBeenCalledTimes(1)
      expect(savePageScreenshotMock).toHaveBeenCalledTimes(1)
    })
    expect(createProjectPreviewArtifactMock).toHaveBeenCalledWith(21, 'src/views/PG202604020001.vue')
    expect(updatePageMock.mock.invocationCallOrder[0]).toBeLessThan(savePageScreenshotMock.mock.invocationCallOrder[0])
    await waitFor(() => {
      expect(messageSuccessMock.mock.calls.some(call => call[0] === '页面截图已重新生成。')).toBe(true)
    })
    expect(await screen.findByAltText('页面详情 页面截图大图')).toHaveAttribute('src', '/media/page-screenshots/PG202604020001.png?v=1712049720000')

    const clickedAnchor = { value: null as HTMLAnchorElement | null }
    anchorClickMock.mockImplementation(function (this: HTMLAnchorElement) {
      clickedAnchor.value = this
    })
    await fireEvent.click(screen.getByRole('button', { name: '下载截图' }))

    await waitFor(() => {
      expect(anchorClickMock).toHaveBeenCalled()
    })
    expect(clickedAnchor.value?.pathname).toBe('/media/page-screenshots/PG202604020001.png')
    expect(clickedAnchor.value?.search).toBe('?v=1712049720000&download=1')
    expect(clickedAnchor.value?.download).toBe('页面详情-v2.png')
  })
})
