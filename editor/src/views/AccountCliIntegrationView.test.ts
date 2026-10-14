/**
 * 文件功能：验证桌面 Agent 与 CLI 介绍页面的渲染与交互行为。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountCliIntegrationView from './AccountCliIntegrationView.vue'

const routerPushMock = vi.fn()
const routerReplaceMock = vi.fn()
const copyTextMock = vi.fn()
const listWorkspacesMock = vi.fn()
let routeQueryMock: Record<string, string | undefined> = {}

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: (...args: unknown[]) => routerPushMock(...args),
    replace: (...args: unknown[]) => routerReplaceMock(...args),
  }),
  useRoute: () => ({
    path: '/settings/account/cli',
    query: routeQueryMock,
  }),
}))

vi.mock('@/api/catalog', () => ({
  listWorkspaces: () => listWorkspacesMock(),
}))

vi.mock('@/utils/clipboard', () => ({
  copyTextToClipboard: (...args: unknown[]) => copyTextMock(...args),
}))

describe('AccountCliIntegrationView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeQueryMock = {}
    listWorkspacesMock.mockResolvedValue({
      items: [
        { id: 11, name: '核心演示空间' },
        { id: 22, name: '市场推广空间' },
      ],
    })
  })

  it('应正确渲染页面标题、工作空间上下文、核心说明与各步骤引导', async () => {
    render(AccountCliIntegrationView)

    expect(screen.getByText('桌面 Agent 与 CLI 接入')).toBeInTheDocument()
    const matchedElements = await screen.findAllByText(/核心演示空间/)
    expect(matchedElements.length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/ID: 11/).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('创建访问令牌 (PAT)')).toBeInTheDocument()
    expect(screen.getByText('复制提示词给智能体')).toBeInTheDocument()
    expect(screen.getByText('唤醒技能开始创作')).toBeInTheDocument()
    expect(screen.getByText('前往创建访问令牌')).toBeInTheDocument()
    expect(screen.getAllByText('wp skill install').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('wp skill install --scope project')).not.toBeInTheDocument()
  })

  it('点击前往创建访问令牌按钮时应携带 action=create 跳转到 tokens 页面', async () => {
    routeQueryMock = { returnTo: '/workspaces/11/home' }
    render(AccountCliIntegrationView)

    const button = await screen.findByRole('button', { name: '前往创建访问令牌' })
    await fireEvent.click(button)

    expect(routerPushMock).toHaveBeenCalledWith({
      path: '/settings/account/tokens',
      query: { action: 'create', returnTo: '/workspaces/11/home' },
    })
  })

  it('点击进入空间按钮时应导航至当前目标工作空间首页', async () => {
    render(AccountCliIntegrationView)

    const enterBtn = await screen.findByRole('button', { name: '进入空间' })
    await fireEvent.click(enterBtn)

    expect(routerPushMock).toHaveBeenCalledWith('/workspaces/11/home')
  })

  it('点击复制命令按钮时应调用复制工具函数', async () => {
    render(AccountCliIntegrationView)

    const copyButtons = await screen.findAllByRole('button', { name: /复制命令/ })
    expect(copyButtons.length).toBeGreaterThan(0)

    await fireEvent.click(copyButtons[0])
    expect(copyTextMock).toHaveBeenCalledWith('uv tool install web-presentation-cli', '命令已复制到剪贴板。')
  })

  it('应过滤已归档的工作空间，仅展示活跃工作空间供选择并生成切换命令', async () => {
    listWorkspacesMock.mockResolvedValueOnce({
      items: [
        { id: 101, name: '已归档空间A', status: 'archived' },
        { id: 102, name: '活跃空间B', status: 'active' },
      ],
    })

    render(AccountCliIntegrationView)

    expect(await screen.findByText(/活跃空间B/)).toBeInTheDocument()
    expect(screen.queryByText(/已归档空间A/)).not.toBeInTheDocument()
    expect(screen.getByText('wp workspace use 102')).toBeInTheDocument()
  })
})
