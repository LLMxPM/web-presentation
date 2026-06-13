/**
 * 文件功能：验证全局智能体侧栏的手动助手切换、业务 scope 与可用性禁用态。
 */
import { defineComponent, h, reactive } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AgentGlobalSidebar from '@/components/agent/AgentGlobalSidebar.vue'

const listAgentsMock = vi.fn()
const routeMock = reactive({
  name: 'components',
})

vi.mock('@/api/ai', () => ({
  listAgents: (...args: unknown[]) => listAgentsMock(...args),
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeMock,
}))

describe('AgentGlobalSidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeMock.name = 'components'
    listAgentsMock.mockResolvedValue([
      {
        id: 'component-manager',
        name: '组件助手',
        icon: 'component-blocks',
        summary: '管理组件库。',
        default_session_name: '组件助手会话',
        capabilities: ['组件库管理'],
        scope_type: 'workspace',
        entry_kind: 'agent',
        available: true,
        unavailable_reason: null,
        llm_slot: 'component_manager',
        llm_binding_ready: true,
        bound_llm_name: '组件模型',
        bound_provider_label: 'OpenAI',
        scope: {
          scope_type: 'component',
          workspace_id: 11,
          project_id: null,
          page_id: null,
          component_id: 99,
          source: 'editor-component-library',
        },
      },
    ])
  })

  it('主题页可切换到 resource-manager，但不能发起资源库对话', async () => {
    routeMock.name = 'themes'
    listAgentsMock.mockResolvedValueOnce([
      {
        id: 'resource-manager',
        name: '资源助手',
        icon: 'resource-images',
        summary: '管理资源库。',
        default_session_name: '资源助手会话',
        capabilities: ['资源管理'],
        scope_type: 'workspace',
        entry_kind: 'agent',
        available: true,
        unavailable_reason: null,
        llm_slot: 'resource_manager',
        llm_binding_ready: true,
        bound_llm_name: '资源模型',
        bound_provider_label: 'OpenAI',
        scope: {
          scope_type: 'workspace',
          workspace_id: 11,
          project_id: null,
          page_id: null,
          component_id: null,
          source: 'editor-asset-library',
        },
      },
    ])
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(AgentGlobalSidebar, {
      props: {
        agentId: 'resource-manager',
        workspaceId: 11,
        source: 'editor-theme-font-library',
      },
      global: {
        plugins: [
          [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
        ],
        stubs: {
          AgentAssistantPanel: defineComponent({
            name: 'AgentAssistantPanel',
            props: ['agentId', 'scope', 'autoCreateKey', 'autoNavigateTarget', 'routeAvailable', 'routeUnavailableReason'],
            setup(props) {
              return () => h('div', {
                'data-testid': 'agent-panel',
                'data-agent-id': props.agentId,
                'data-source': props.scope?.source,
                'data-auto-create-key': String(props.autoCreateKey ?? ''),
                'data-auto-navigate-target': props.autoNavigateTarget,
                'data-route-available': String(props.routeAvailable),
                'data-route-unavailable-reason': props.routeUnavailableReason,
              })
            },
          }),
        },
      },
    })

    const openButton = await waitFor(() => screen.getByTitle('资源助手'))
    expect(openButton).toHaveProperty('disabled', false)
    await fireEvent.click(openButton)

    const panel = screen.getByTestId('agent-panel')
    expect(panel.dataset.agentId).toBe('resource-manager')
    expect(panel.dataset.source).toBe('editor-asset-library')
    expect(panel.dataset.autoCreateKey).toBe('')
    expect(panel.dataset.autoNavigateTarget).toBe('/workspaces/11/assets')
    expect(panel.dataset.routeAvailable).toBe('false')
    expect(panel.dataset.routeUnavailableReason).toBe('资源助手只能在资源库页面发起对话。')
  })

  it('组件库路由可用同一侧栏打开 component-manager，并使用组件库工作空间 scope', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(AgentGlobalSidebar, {
      props: {
        agentId: 'component-manager',
        workspaceId: 11,
        componentId: 99,
        componentName: '销售卡片',
        source: 'editor-component-library',
      },
      global: {
        plugins: [
          [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
        ],
        stubs: {
          AgentAssistantPanel: defineComponent({
            name: 'AgentAssistantPanel',
            props: ['agentId', 'scope', 'contextTitle'],
            setup(props) {
              return () => h('div', {
                'data-testid': 'agent-panel',
                'data-agent-id': props.agentId,
                'data-scope-type': props.scope?.scope_type,
                'data-component-id': String(props.scope?.component_id ?? ''),
                'data-source': props.scope?.source,
                'data-context-title': props.contextTitle,
              })
            },
          }),
        },
      },
    })

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalledWith(
        expect.objectContaining({
          scope_type: 'workspace',
          workspace_id: 11,
          component_id: null,
          source: 'editor-component-library',
        }),
      )
    })

    const openButton = await waitFor(() => screen.getByTitle('组件助手'))
    await fireEvent.click(openButton)

    const panel = screen.getByTestId('agent-panel')
    expect(panel.dataset.agentId).toBe('component-manager')
    expect(panel.dataset.scopeType).toBe('workspace')
    expect(panel.dataset.componentId).toBe('')
    expect(panel.dataset.source).toBe('editor-component-library')
    expect(panel.dataset.contextTitle).toBe('组件库')
  })

  it('当前路由下不可用的助手入口应禁用并展示原因', async () => {
    listAgentsMock.mockResolvedValueOnce([
      {
        id: 'component-manager',
        name: '组件助手',
        icon: 'component-blocks',
        summary: '管理组件库。',
        default_session_name: '组件助手会话',
        capabilities: ['组件库管理'],
        scope_type: 'workspace',
        entry_kind: 'agent',
        available: false,
        unavailable_reason: '当前路由下组件助手不可用。',
        llm_slot: 'component_manager',
        llm_binding_ready: true,
        bound_llm_name: '组件模型',
        bound_provider_label: 'OpenAI',
        scope: {
          scope_type: 'workspace',
          workspace_id: 11,
          project_id: null,
          page_id: null,
          component_id: null,
          source: 'editor-component-library',
        },
      },
    ])
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(AgentGlobalSidebar, {
      props: {
        agentId: 'component-manager',
        workspaceId: 11,
        source: 'editor-component-library',
      },
      global: {
        plugins: [
          [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
        ],
        stubs: {
          AgentAssistantPanel: defineComponent({
            name: 'AgentAssistantPanel',
            template: '<div data-testid="agent-panel" />',
          }),
        },
      },
    })

    const disabledButton = await waitFor(() => screen.getByTitle('组件助手：当前路由下组件助手不可用。'))
    expect(disabledButton).toHaveProperty('disabled', true)
  })

  it('页面路由可切换到组件助手，但不能发起组件库对话', async () => {
    routeMock.name = 'pageDetail'
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(AgentGlobalSidebar, {
      props: {
        agentId: 'agent-coordinator',
        workspaceId: 11,
        projectId: 21,
        pageId: 31,
        pageTitle: 'AI 页面',
        source: 'editor-agent-sidebar',
      },
      global: {
        plugins: [
          [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
        ],
        stubs: {
          AgentAssistantPanel: defineComponent({
            name: 'AgentAssistantPanel',
            props: ['agentId', 'scope', 'autoCreateKey', 'autoNavigateTarget', 'routeAvailable', 'routeUnavailableReason'],
            setup(props) {
              return () => h('div', {
                'data-testid': 'agent-panel',
                'data-agent-id': props.agentId,
                'data-scope-type': props.scope?.scope_type,
                'data-component-id': String(props.scope?.component_id ?? ''),
                'data-source': props.scope?.source,
                'data-auto-create-key': String(props.autoCreateKey ?? ''),
                'data-auto-navigate-target': props.autoNavigateTarget,
                'data-route-available': String(props.routeAvailable),
                'data-route-unavailable-reason': props.routeUnavailableReason,
              })
            },
          }),
        },
      },
    })

    const openButton = await waitFor(() => screen.getByTitle('组件助手'))
    expect(openButton).toHaveProperty('disabled', false)
    await fireEvent.click(openButton)

    const panel = screen.getByTestId('agent-panel')
    expect(panel.dataset.agentId).toBe('component-manager')
    expect(panel.dataset.scopeType).toBe('workspace')
    expect(panel.dataset.componentId).toBe('')
    expect(panel.dataset.source).toBe('editor-component-library')
    expect(panel.dataset.autoCreateKey).toBe('')
    expect(panel.dataset.autoNavigateTarget).toBe('/workspaces/11/components')
    expect(panel.dataset.routeAvailable).toBe('false')
    expect(panel.dataset.routeUnavailableReason).toBe('组件助手只能在组件库页面发起对话。')
  })

  it.each([
    ['component-manager', '组件助手', '组件助手只能在组件库页面发起对话。'],
    ['resource-manager', '资源助手', '资源助手只能在资源库页面发起对话。'],
  ])('页面路由切换到 %s 后应禁用发起能力', async (targetAgentId, buttonTitle, unavailableReason) => {
    routeMock.name = 'pageDetail'
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(AgentGlobalSidebar, {
      props: {
        agentId: 'agent-coordinator',
        workspaceId: 11,
        projectId: 21,
        pageId: 31,
        pageTitle: 'AI 页面',
        source: 'editor-agent-sidebar',
      },
      global: {
        plugins: [
          [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
        ],
        stubs: {
          AgentAssistantPanel: defineComponent({
            name: 'AgentAssistantPanel',
            props: ['agentId', 'scope', 'routeScope', 'autoCreateKey', 'autoNavigateTarget', 'routeAvailable', 'routeUnavailableReason'],
            setup(props) {
              return () => h('div', {
                'data-testid': 'agent-panel',
                'data-agent-id': props.agentId,
                'data-scope-source': props.scope?.source,
                'data-route-scope-type': props.routeScope?.scope_type,
                'data-route-source': props.routeScope?.source,
                'data-route-page-id': String(props.routeScope?.page_id ?? ''),
                'data-auto-create-key': String(props.autoCreateKey ?? ''),
                'data-auto-navigate-target': props.autoNavigateTarget,
                'data-route-available': String(props.routeAvailable),
                'data-route-unavailable-reason': props.routeUnavailableReason,
              })
            },
          }),
        },
      },
    })

    const openButton = await waitFor(() => screen.getByTitle(buttonTitle))
    expect(openButton).toHaveProperty('disabled', false)
    await fireEvent.click(openButton)

    const panel = screen.getByTestId('agent-panel')
    expect(panel.dataset.agentId).toBe(targetAgentId)
    expect(panel.dataset.routeScopeType).toBe('page')
    expect(panel.dataset.routeSource).toBe('editor-agent-sidebar')
    expect(panel.dataset.routePageId).toBe('31')
    expect(panel.dataset.autoCreateKey).toBe('')
    expect(panel.dataset.routeAvailable).toBe('false')
    expect(panel.dataset.routeUnavailableReason).toBe(unavailableReason)
  })

  it('路由切到其他库页面时应保留当前助手但禁止继续发起', async () => {
    routeMock.name = 'components'
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    const { rerender } = render(AgentGlobalSidebar, {
      props: {
        agentId: 'component-manager',
        workspaceId: 11,
        source: 'editor-component-library',
      },
      global: {
        plugins: [
          [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
        ],
        stubs: {
          AgentAssistantPanel: defineComponent({
            name: 'AgentAssistantPanel',
            props: ['agentId', 'scope', 'routeAvailable', 'routeUnavailableReason'],
            setup(props) {
              return () => h('div', {
                'data-testid': 'agent-panel',
                'data-agent-id': props.agentId,
                'data-scope-type': props.scope?.scope_type,
                'data-source': props.scope?.source,
                'data-route-available': String(props.routeAvailable),
                'data-route-unavailable-reason': props.routeUnavailableReason,
              })
            },
          }),
        },
      },
    })

    await fireEvent.click(await waitFor(() => screen.getByTitle('组件助手')))
    expect(screen.getByTestId('agent-panel').dataset.agentId).toBe('component-manager')

    routeMock.name = 'assets'
    await rerender({
      agentId: 'resource-manager',
      workspaceId: 11,
      projectId: null,
      pageId: null,
      source: 'editor-asset-library',
    })

    await waitFor(() => {
      const panel = screen.getByTestId('agent-panel')
      expect(panel.dataset.agentId).toBe('component-manager')
      expect(panel.dataset.scopeType).toBe('workspace')
      expect(panel.dataset.source).toBe('editor-component-library')
      expect(panel.dataset.routeAvailable).toBe('false')
      expect(panel.dataset.routeUnavailableReason).toBe('组件助手只能在组件库页面发起对话。')
    })

    await fireEvent.click(await waitFor(() => screen.getByTitle('资源助手')))
    const switchedPanel = screen.getByTestId('agent-panel')
    expect(switchedPanel.dataset.agentId).toBe('resource-manager')
    expect(switchedPanel.dataset.source).toBe('editor-asset-library')
    expect(switchedPanel.dataset.routeAvailable).toBe('true')
  })

  it.each([
    ['workspaceHome'],
    ['themes'],
    ['workspaceStyles'],
  ])('%s 下内容助手入口应可切换并提示进入具体项目后才能运行', async (routeName) => {
    routeMock.name = routeName
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(AgentGlobalSidebar, {
      props: {
        agentId: 'agent-coordinator',
        workspaceId: 11,
        workspaceName: '演示空间',
        source: 'editor-agent-sidebar',
      },
      global: {
        plugins: [
          [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
        ],
        stubs: {
          AgentAssistantPanel: defineComponent({
            name: 'AgentAssistantPanel',
            props: ['routeAvailable', 'routeUnavailableReason'],
            setup(props) {
              return () => h('div', {
                'data-testid': 'agent-panel',
                'data-route-available': String(props.routeAvailable),
                'data-route-unavailable-reason': props.routeUnavailableReason,
              })
            },
          }),
        },
      },
    })

    const contentButton = await waitFor(() => screen.getByTitle('内容助手'))
    expect(contentButton).toHaveProperty('disabled', false)
    await fireEvent.click(contentButton)

    const panel = screen.getByTestId('agent-panel')
    expect(panel.dataset.routeAvailable).toBe('false')
    expect(panel.dataset.routeUnavailableReason).toBe('内容助手需要进入具体项目后才能启动。')
  })

  it('项目页面列表路由下内容助手应可用并生成项目 scope', async () => {
    routeMock.name = 'pages'
    listAgentsMock.mockResolvedValueOnce([
      {
        id: 'agent-coordinator',
        name: '内容助手',
        icon: 'content-spark',
        summary: '处理项目任务。',
        default_session_name: '内容助手会话',
        capabilities: ['页面源码修改'],
        scope_type: 'workspace',
        entry_kind: 'team',
        available: true,
        unavailable_reason: null,
        llm_slot: 'agent_coordinator',
        llm_binding_ready: true,
        bound_llm_name: '总控模型',
        bound_provider_label: 'OpenAI',
        scope: {
          scope_type: 'project',
          workspace_id: 11,
          project_id: 21,
          page_id: null,
          component_id: null,
          source: 'editor-agent-sidebar',
        },
      },
    ])
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(AgentGlobalSidebar, {
      props: {
        agentId: 'agent-coordinator',
        workspaceId: 11,
        projectId: 21,
        projectName: '发布会方案',
        source: 'editor-agent-sidebar',
      },
      global: {
        plugins: [
          [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
        ],
        stubs: {
          AgentAssistantPanel: defineComponent({
            name: 'AgentAssistantPanel',
            props: ['agentId', 'scope', 'autoNavigateTarget', 'routeAvailable'],
            setup(props) {
              return () => h('div', {
                'data-testid': 'agent-panel',
                'data-agent-id': props.agentId,
                'data-scope-type': props.scope?.scope_type,
                'data-project-id': String(props.scope?.project_id ?? ''),
                'data-auto-navigate-target': props.autoNavigateTarget,
                'data-route-available': String(props.routeAvailable),
              })
            },
          }),
        },
      },
    })

    const openButton = await waitFor(() => screen.getByTitle('内容助手'))
    expect(openButton).toHaveProperty('disabled', false)
    await fireEvent.click(openButton)

    const panel = screen.getByTestId('agent-panel')
    expect(panel.dataset.agentId).toBe('agent-coordinator')
    expect(panel.dataset.scopeType).toBe('project')
    expect(panel.dataset.projectId).toBe('21')
    expect(panel.dataset.autoNavigateTarget).toBe('/workspaces/11/projects/21/pages')
    expect(panel.dataset.routeAvailable).toBe('true')
  })

  it('应桥接组件刷新事件并补齐当前上下文', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    const componentUpdatedListener = vi.fn()
    window.addEventListener('agent:component-updated', componentUpdatedListener)

    try {
      render(AgentGlobalSidebar, {
        props: {
          agentId: 'component-manager',
          workspaceId: 11,
          componentId: 99,
          componentName: '销售卡片',
          source: 'editor-component-library',
        },
        global: {
          plugins: [
            [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
          ],
          stubs: {
            AgentAssistantPanel: defineComponent({
              name: 'AgentAssistantPanel',
              emits: ['component-updated'],
              setup(_, { emit }) {
                return () => h('button', {
                  type: 'button',
                  onClick: () => emit('component-updated', {
                    kind: 'component',
                    workspaceId: null,
                    projectId: null,
                    pageId: null,
                    componentId: null,
                    toolName: 'apply_component_edits',
                    result: { success: true, component_id: 99 },
                  }),
                }, '触发组件刷新')
              },
            }),
          },
        },
      })

      const openButton = await waitFor(() => screen.getByTitle('组件助手'))
      await fireEvent.click(openButton)
      await fireEvent.click(screen.getByRole('button', { name: '触发组件刷新' }))

      const event = componentUpdatedListener.mock.calls[0]?.[0] as CustomEvent<unknown>
      expect(event.detail).toEqual(expect.objectContaining({
        kind: 'component',
        workspaceId: 11,
        componentId: null,
        toolName: 'apply_component_edits',
        result: { success: true, component_id: 99 },
      }))
    } finally {
      window.removeEventListener('agent:component-updated', componentUpdatedListener)
    }
  })
})
