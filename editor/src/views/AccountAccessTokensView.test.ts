/**
 * 文件功能：验证访问令牌 (PAT) 管理页面的渲染、桌面 Agent 接入指南跳转、创建与重置成功弹窗的智能体提示词及作用域切换交互。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountAccessTokensView from './AccountAccessTokensView.vue'

const listAccessTokensMock = vi.fn()
const listAccessTokenScopesMock = vi.fn()
const listWorkspacesMock = vi.fn()
const createAccessTokenMock = vi.fn()
const resetAccessTokenMock = vi.fn()
const revokeAccessTokenMock = vi.fn()
const updateAccessTokenMock = vi.fn()

const routerPushMock = vi.fn()
const routerReplaceMock = vi.fn()
const copyTextMock = vi.fn()
let routeQueryMock: Record<string, string | undefined> = {}

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: (...args: unknown[]) => routerPushMock(...args),
    replace: (...args: unknown[]) => routerReplaceMock(...args),
  }),
  useRoute: () => ({
    path: '/settings/account/tokens',
    query: routeQueryMock,
  }),
}))

vi.mock('@/api/accessTokens', () => ({
  listAccessTokens: () => listAccessTokensMock(),
  listAccessTokenScopes: () => listAccessTokenScopesMock(),
  createAccessToken: (...args: unknown[]) => createAccessTokenMock(...args),
  resetAccessToken: (...args: unknown[]) => resetAccessTokenMock(...args),
  revokeAccessToken: (...args: unknown[]) => revokeAccessTokenMock(...args),
  updateAccessToken: (...args: unknown[]) => updateAccessTokenMock(...args),
}))

vi.mock('@/api/catalog', () => ({
  listWorkspaces: () => listWorkspacesMock(),
}))

vi.mock('@/utils/clipboard', () => ({
  copyTextToClipboard: (...args: unknown[]) => copyTextMock(...args),
}))

vi.mock('@/utils/cli-prompts', async () => {
  const actual = await vi.importActual<typeof import('@/utils/cli-prompts')>('@/utils/cli-prompts')
  return {
    ...actual,
    resolveCurrentEndpoint: () => 'https://presentation.example.com',
  }
})

describe('AccountAccessTokensView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeQueryMock = {}
    listAccessTokensMock.mockResolvedValue({
      items: [
        {
          id: 1,
          name: 'CLI 个人令牌',
          token_masked: 'wp_pat_mock...xxxx',
          scopes: ['read:all', 'write:all'],
          is_active: true,
          all_workspaces: true,
          workspace_ids: [],
          expires_at: null,
          created_at: '2026-08-18T10:00:00Z',
          last_used_at: null,
          last_used_ip: null,
          revoked_at: null,
        },
      ],
      max_active_tokens: 10,
    })
    listAccessTokenScopesMock.mockResolvedValue([
      { scope: 'read:all', description: '只读权限', operation_count: 5 },
      { scope: 'write:all', description: '写入权限', operation_count: 8 },
    ])
    listWorkspacesMock.mockResolvedValue({
      items: [{ id: 11, name: '演示空间' }],
    })
  })

  it('页面头部应常驻渲染「桌面 Agent 接入指南」按钮，点击时路由至 /settings/account/cli', async () => {
    render(AccountAccessTokensView)
    expect(await screen.findByText('CLI 个人令牌')).toBeInTheDocument()

    const guideBtn = screen.getByRole('button', { name: /桌面 Agent 接入指南/ })
    expect(guideBtn).toBeInTheDocument()

    await fireEvent.click(guideBtn)
    expect(routerPushMock).toHaveBeenCalledWith('/settings/account/cli')
  })

  it('当暂无访问令牌 (空状态) 时，应渲染指引链接且包含查看指南按钮', async () => {
    listAccessTokensMock.mockResolvedValueOnce({
      items: [],
      max_active_tokens: 10,
    })

    render(AccountAccessTokensView)
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(screen.getByText('暂无访问令牌')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '创建首个令牌' })).toBeInTheDocument()

    const emptyGuideBtn = screen.getByRole('button', { name: /查看桌面 Agent 接入指南/ })
    expect(emptyGuideBtn).toBeInTheDocument()

    await fireEvent.click(emptyGuideBtn)
    expect(routerPushMock).toHaveBeenCalledWith('/settings/account/cli')
  })

  it('路由携带 action=create 打开页面时应自动唤起创建令牌弹窗并清除参数，关闭弹窗后应恢复 body 点击交互', async () => {
    routeQueryMock = { action: 'create' }

    render(AccountAccessTokensView)

    const heading = await screen.findByRole('heading', { name: '创建个人访问令牌' })
    expect(heading).toBeInTheDocument()
    expect(routerReplaceMock).toHaveBeenCalledWith({
      path: '/settings/account/tokens',
      query: { action: undefined },
    })

    const cancelBtn = screen.getByRole('button', { name: '取消' })
    await fireEvent.click(cancelBtn)

    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: '创建个人访问令牌' })).not.toBeInTheDocument()
    })
    expect(document.body.style.pointerEvents).not.toBe('none')
  })

  it('创建令牌成功后应展示智能体提示词，并包含直接安装技能的指令', async () => {
    createAccessTokenMock.mockResolvedValue({
      token: 'wp_pat_secret_abc123',
    })

    render(AccountAccessTokensView)
    expect(await screen.findByText('CLI 个人令牌')).toBeInTheDocument()

    const createBtn = await screen.findByRole('button', { name: '创建新令牌' })
    await fireEvent.click(createBtn)

    const nameInput = screen.getByPlaceholderText('例如：CLI-MacBook-Pro 或 CI-Build-Worker')
    await fireEvent.update(nameInput, 'Cursor 协同令牌')

    const submitBtn = screen.getByRole('button', { name: '生成令牌' })
    await fireEvent.click(submitBtn)

    expect(await screen.findByRole('heading', { name: '令牌创建成功' })).toBeInTheDocument()

    const textarea = (await screen.findByTestId('agent-prompt-textarea')) as HTMLTextAreaElement
    expect(textarea.value).toContain('wp_pat_secret_abc123')
    expect(textarea.value).toContain('https://presentation.example.com')
    expect(textarea.value).toContain('wp skill install')
    expect(textarea.value).not.toContain('--scope project')

    // 复制提示词
    const copyAgentPromptBtn = screen.getByRole('button', { name: '复制提示词给智能体' })
    await fireEvent.click(copyAgentPromptBtn)
    expect(copyTextMock).toHaveBeenCalledWith(
      textarea.value,
      '智能体提示词已复制！请直接粘贴给 Cursor / Claude 等 AI 助手。'
    )
  })

  it('重置令牌成功后应默认展示重新登录提示词，切换为全新安装时展示全套提示词与作用域控制', async () => {
    resetAccessTokenMock.mockResolvedValue({
      token: 'wp_pat_new_secret_789',
    })

    render(AccountAccessTokensView)
    expect(await screen.findByText('CLI 个人令牌')).toBeInTheDocument()

    const resetBtn = await screen.findByRole('button', { name: '重置' })
    await fireEvent.click(resetBtn)

    const confirmResetBtn = screen.getByRole('button', { name: '确认重置并生成新密钥' })
    await fireEvent.click(confirmResetBtn)

    expect(await screen.findByRole('heading', { name: '令牌重置成功' })).toBeInTheDocument()

    // 默认处于重新登录模式
    const textarea = (await screen.findByTestId('agent-prompt-textarea')) as HTMLTextAreaElement
    expect(textarea.value).toContain('wp login --endpoint https://presentation.example.com --token wp_pat_new_secret_789')
    expect(textarea.value).toContain('wp whoami')
    expect(textarea.value).not.toContain('uv tool install')

    // 切换为全新安装模式
    const freshInstallTab = screen.getByText('全新安装')
    await fireEvent.click(freshInstallTab)

    expect(textarea.value).toContain('uv tool install web-presentation-cli')
    expect(textarea.value).toContain('wp skill install')
    expect(textarea.value).not.toContain('--scope project')
  })
})
