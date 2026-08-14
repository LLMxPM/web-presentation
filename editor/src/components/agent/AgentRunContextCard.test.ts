/**
 * 文件功能：验证每轮工作上下文卡片的焦点可点击跳转到对应页面，缺所属项目时按需补齐。
 */
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AgentRunContextCard from '@/components/agent/AgentRunContextCard.vue'
import type { AgentRunContextSummary } from '@/types/api'

const getPageMock = vi.fn()
const routerPushMock = vi.fn()

vi.mock('@/api/catalog', () => ({
  getPage: (...args: unknown[]) => getPageMock(...args),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPushMock }),
}))

vi.mock('@/utils/message', () => ({
  Message: { warning: vi.fn() },
}))

/** 构造带焦点与工作集的上下文摘要。 */
function buildContext(focus: AgentRunContextSummary['focus']): AgentRunContextSummary {
  return {
    focus,
    work_scope_mode: 'workspace',
    allowed_projects: [],
    focus_version: 1,
  }
}

/** 使用关闭重试的独立查询客户端挂载上下文卡片。 */
function renderCard(context: AgentRunContextSummary) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(AgentRunContextCard, {
    props: { context },
    global: {
      plugins: [
        [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
      ],
    },
  })
}

describe('AgentRunContextCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('页面焦点应点击跳转到页面详情路由', async () => {
    renderCard(buildContext({
      scope_type: 'page',
      workspace_id: 11,
      project_id: 21,
      page_id: 31,
      page_title: '经营概览',
      source: 'editor-page-detail',
    }))

    expect(screen.getByText('经营概览')).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '跳转到本轮焦点：经营概览' }))
    expect(routerPushMock).toHaveBeenCalledWith('/workspaces/11/projects/21/pages/31')
  })

  it('页面焦点缺所属项目时应在点击时补齐项目后跳转', async () => {
    getPageMock.mockResolvedValue({ id: 31, title: '核心指标', project_id: 21 })
    renderCard(buildContext({
      scope_type: 'page',
      workspace_id: 11,
      project_id: null,
      page_id: 31,
      page_title: '核心指标',
      source: 'editor-page-detail',
    }))

    await fireEvent.click(screen.getByRole('button', { name: '跳转到本轮焦点：核心指标' }))
    expect(getPageMock).toHaveBeenCalledWith(31)
    await waitFor(() => {
      expect(routerPushMock).toHaveBeenCalledWith('/workspaces/11/projects/21/pages/31')
    })
  })

  it('页面详情补齐失败时应提示且不跳转', async () => {
    getPageMock.mockRejectedValue(new Error('not found'))
    renderCard(buildContext({
      scope_type: 'page',
      workspace_id: 11,
      project_id: null,
      page_id: 31,
      page_title: null,
      source: 'editor-page-detail',
    }))

    await fireEvent.click(screen.getByRole('button', { name: '跳转到本轮焦点：页面 #31' }))
    await waitFor(() => {
      expect(routerPushMock).not.toHaveBeenCalled()
    })
  })

  it('项目焦点应点击跳转到项目页面列表路由', async () => {
    renderCard(buildContext({
      scope_type: 'project',
      workspace_id: 11,
      project_id: 21,
      page_id: null,
      project_name: '年度发布会',
      source: 'editor-project-pages',
    }))

    await fireEvent.click(screen.getByRole('button', { name: '跳转到本轮焦点：年度发布会' }))
    expect(routerPushMock).toHaveBeenCalledWith('/workspaces/11/projects/21/pages')
  })

  it('组件焦点应点击跳转到组件库路由', async () => {
    renderCard(buildContext({
      scope_type: 'component',
      workspace_id: 11,
      project_id: null,
      page_id: null,
      component_id: 41,
      component_name: '数据卡片',
      source: 'editor-component-library',
    }))

    await fireEvent.click(screen.getByRole('button', { name: '跳转到本轮焦点：数据卡片' }))
    expect(routerPushMock).toHaveBeenCalledWith('/workspaces/11/components')
  })

  it('缺少工作空间时焦点不可点击且不跳转', async () => {
    renderCard(buildContext({
      scope_type: 'project',
      workspace_id: 0,
      project_id: 21,
      page_id: null,
      project_name: '年度发布会',
      source: 'editor-project-pages',
    }))

    const focusButton = screen.getByRole('button', { name: '跳转到本轮焦点：年度发布会' })
    expect(focusButton).toBeDisabled()
    await fireEvent.click(focusButton)
    expect(routerPushMock).not.toHaveBeenCalled()
  })
})
