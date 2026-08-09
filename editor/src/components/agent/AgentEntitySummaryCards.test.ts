/**
 * 文件功能：验证本轮项目与页面摘要通过详情接口展示业务名称和编码，并隐藏数据库 ID。
 */
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

import AgentEntitySummaryCards from '@/components/agent/AgentEntitySummaryCards.vue'
import type { AgentEntityChangeItem } from '@/components/agent/agent-entity-change-summary'

const getProjectMock = vi.fn()
const getPageMock = vi.fn()
const routerPushMock = vi.fn()

vi.mock('@/api/catalog', () => ({
  getProject: (...args: unknown[]) => getProjectMock(...args),
  getPage: (...args: unknown[]) => getPageMock(...args),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { workspaceId: '11' } }),
  useRouter: () => ({ push: routerPushMock }),
}))

const items: AgentEntityChangeItem[] = [
  {
    resourceType: 'project',
    id: 21,
    projectId: 21,
    workspaceId: 11,
    name: null,
    effect: 'update',
    runId: 'run-1',
    sourceToolName: 'update_entity',
  },
  {
    resourceType: 'page',
    id: 31,
    projectId: null,
    workspaceId: 11,
    name: null,
    effect: 'create',
    runId: 'run-1',
    sourceToolName: 'create_entity',
  },
]

/** 使用关闭重试的独立查询客户端挂载摘要卡片。 */
function renderCards() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(AgentEntitySummaryCards, {
    props: { items },
    global: {
      plugins: [
        [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
      ],
    },
  })
}

describe('AgentEntitySummaryCards', () => {
  it('应请求项目与页面详情并展示名称和编码', async () => {
    getProjectMock.mockResolvedValue({ id: 21, name: '年度发布会', code: 'annual-launch' })
    getPageMock.mockResolvedValue({ id: 31, title: '核心指标', code: 'key-metrics', project_id: 21 })

    renderCards()

    await waitFor(() => {
      expect(screen.getByText('年度发布会')).toBeInTheDocument()
      expect(screen.getByText('项目 · annual-launch')).toBeInTheDocument()
      expect(screen.getByText('核心指标')).toBeInTheDocument()
      expect(screen.getByText('页面 · key-metrics')).toBeInTheDocument()
    })
    expect(screen.queryByText(/#21|#31/)).not.toBeInTheDocument()
    expect(getProjectMock).toHaveBeenCalledWith(21)
    expect(getPageMock).toHaveBeenCalledWith(31)

    await fireEvent.click(screen.getByRole('button', { name: '新增页面：核心指标' }))
    expect(routerPushMock).toHaveBeenCalledWith('/workspaces/11/projects/21/pages/31')
  })

  it('详情请求失败时应显示友好状态且不回退展示 ID', async () => {
    getProjectMock.mockRejectedValue(new Error('not found'))
    getPageMock.mockRejectedValue(new Error('not found'))

    renderCards()

    await waitFor(() => {
      expect(screen.getByText('项目名称暂不可用')).toBeInTheDocument()
      expect(screen.getByText('页面名称暂不可用')).toBeInTheDocument()
      expect(screen.getAllByText(/编码暂不可用/)).toHaveLength(2)
    })
    expect(screen.queryByText(/#21|#31/)).not.toBeInTheDocument()
  })
})
