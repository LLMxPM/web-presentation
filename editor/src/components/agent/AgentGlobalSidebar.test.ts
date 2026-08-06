/**
 * 文件功能：验证全局侧栏只展示统一内容助手，并按当前路由提供业务上下文。
 */
import { defineComponent, reactive } from 'vue'
import { render, screen, waitFor } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AgentGlobalSidebar from '@/components/agent/AgentGlobalSidebar.vue'

const listAgentsMock = vi.fn()
const routeMock = reactive<{ name: string }>({ name: 'components' })

vi.mock('@/api/ai', () => ({
  listAgents: (...args: unknown[]) => listAgentsMock(...args),
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeMock,
}))

const unifiedAgent = {
  id: 'agent-coordinator',
  name: '内容助手',
  icon: 'content-spark',
  summary: '统一管理工作空间内容。',
  default_session_name: '内容助手会话',
  capabilities: ['通用业务管理'],
  scope_type: 'workspace',
  entry_kind: 'agent',
  available: true,
  unavailable_reason: null,
  llm_slot: 'agent_coordinator',
  llm_binding_ready: true,
  bound_llm_name: '内容模型',
  bound_provider_label: 'OpenAI',
}

describe('AgentGlobalSidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeMock.name = 'components'
    listAgentsMock.mockResolvedValue([unifiedAgent])
  })

  it('单智能体模式不展示助手切换 Tab 并默认展开', async () => {
    renderSidebar()

    expect(screen.getByTestId('agent-sidebar-panel')).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('agent-panel').dataset.agentId).toBe('agent-coordinator'))
    expect(screen.queryByRole('tab')).toBeNull()
    expect(screen.queryByText('内容助手')).toBeNull()
    expect(screen.queryByText('组件助手')).toBeNull()
    expect(screen.queryByText('资源助手')).toBeNull()
  })

  it('即使接口混入旧助手也只保留统一内容助手', async () => {
    listAgentsMock.mockResolvedValue([
      unifiedAgent,
      { ...unifiedAgent, id: 'component-manager', name: '组件助手' },
      { ...unifiedAgent, id: 'resource-manager', name: '资源助手' },
    ])
    renderSidebar()

    await waitFor(() => expect(screen.queryByRole('tab')).toBeNull())
    expect(screen.getByTestId('agent-panel').dataset.agentId).toBe('agent-coordinator')
  })

  it('组件库和页面路由都复用同一助手，并传入当前业务上下文', async () => {
    const view = renderSidebar({ projectId: 7, pageId: 9, source: 'editor-page-detail' })

    await waitFor(() => expect(screen.getByTestId('agent-panel').dataset.agentId).toBe('agent-coordinator'))
    expect(screen.getByTestId('agent-panel').dataset.scopeType).toBe('workspace')

    routeMock.name = 'pageDetail'
    await view.rerender({
      workspaceId: 11,
      projectId: 7,
      pageId: 9,
      source: 'editor-page-detail',
    })
    await waitFor(() => expect(screen.getByTestId('agent-panel').dataset.scopeType).toBe('page'))
    expect(screen.getByTestId('agent-panel').dataset.projectId).toBe('7')
    expect(screen.getByTestId('agent-panel').dataset.pageId).toBe('9')
  })
})

/** 渲染带最小查询环境和可观测助手面板替身的侧栏。 */
function renderSidebar(props: Record<string, unknown> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(AgentGlobalSidebar, {
    props: { workspaceId: 11, ...props },
    global: {
      plugins: [[VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }]],
      stubs: {
        AgentAssistantPanel: defineComponent({
          name: 'AgentAssistantPanel',
          props: ['agentId', 'scope'],
          template: `<div
            data-testid="agent-panel"
            :data-agent-id="agentId"
            :data-scope-type="scope.scope_type"
            :data-project-id="scope.project_id"
            :data-page-id="scope.page_id"
          />`,
        }),
      },
    },
  })
}
