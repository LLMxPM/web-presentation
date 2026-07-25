/**
 * 文件功能：验证智能体会话切换下拉的数量展示、最近会话限制与标题搜索。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import AgentSessionControls from '@/components/agent/AgentSessionControls.vue'
import type { AgentSessionItem } from '@/types/api'

function createSession(index: number, overrides: Partial<AgentSessionItem> = {}): AgentSessionItem {
  return {
    session_id: `session-${index}`,
    agent_id: 'agent-coordinator',
    session_name: `会话 ${index}`,
    created_at: `2026-05-${String(Math.max(1, index)).padStart(2, '0')}T10:00:00+08:00`,
    updated_at: new Date(Date.UTC(2026, 4, 31, 10, 0, 0) - index * 60_000).toISOString(),
    metadata: {
      scope_type: 'page',
      workspace_id: 11,
      workspace_name: '演示工作区',
      project_id: 21,
      project_name: '发布会方案',
      page_id: index,
      page_title: `页面 ${index}`,
      source: 'editor-page-detail',
    },
    ...overrides,
  }
}

async function renderControls(sessions: AgentSessionItem[], props: Record<string, unknown> = {}) {
  const result = render(AgentSessionControls, {
    props: {
      sessions,
      activeSessionId: sessions[0]?.session_id ?? '',
      activeSessionLabel: '当前会话标题不应出现在下拉头部',
      isFetching: false,
      menuVisible: true,
      createDisabled: false,
      switchDisabled: false,
      align: 'left',
      getSessionRunBadge: vi.fn(() => null),
      ...props,
    },
  })
  // UiPopover 内容经 Reka UI Teleport 挂载到 body，需等待异步挂载完成后才能被 screen 查询到。
  await nextTick()
  return result
}

describe('AgentSessionControls', () => {
  it('下拉头部应隐藏当前会话标题，并把会话数量放到右侧', async () => {
    await renderControls([createSession(1), createSession(2)])

    expect(screen.getByText('会话切换')).toBeInTheDocument()
    expect(screen.getByText('共 2 个')).toBeInTheDocument()
    expect(screen.queryByText('当前会话标题不应出现在下拉头部')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /会话 1/ })).toHaveAttribute('aria-current', 'true')
  })

  it('会话项应使用可换行的专用列表按钮，避免继承 UiButton 的单行内容层', async () => {
    const { emitted } = await renderControls([createSession(1), createSession(2)])
    const sessionButton = screen.getByRole('button', { name: /会话 2/ })

    expect(sessionButton).not.toHaveClass('whitespace-nowrap')
    expect(sessionButton.querySelector(':scope > span')).toBeNull()

    await fireEvent.click(sessionButton)
    expect(emitted()['switch-session']).toEqual([['session-2']])
  })

  it('无搜索时最多只渲染最近 50 条会话', async () => {
    await renderControls(Array.from({ length: 60 }, (_, index) => createSession(index + 1)))

    expect(screen.getByText('最近 50 / 共 60')).toBeInTheDocument()
    expect(screen.getByText('会话 1')).toBeInTheDocument()
    expect(screen.getByText('会话 50')).toBeInTheDocument()
    expect(screen.queryByText('会话 51')).not.toBeInTheDocument()
  })

  it('应按会话标题执行本地搜索，并仍限制最多 50 条结果', async () => {
    const sessions = [
      ...Array.from({ length: 60 }, (_, index) => createSession(index + 1)),
      createSession(61, { session_name: '品牌策略复盘' }),
    ]
    await renderControls(sessions)

    await fireEvent.update(screen.getByLabelText('搜索会话标题'), '品牌')

    expect(screen.getByText('匹配 1 个')).toBeInTheDocument()
    expect(screen.getByText('品牌策略复盘')).toBeInTheDocument()
    expect(screen.queryByText('会话 1')).not.toBeInTheDocument()
  })

  it('空会话列表加载时应展示统一加载状态', async () => {
    await renderControls([], { isFetching: true })

    expect(screen.getByText('正在加载')).toBeInTheDocument()
  })

  it('空会话列表应展示统一空状态说明', async () => {
    await renderControls([])

    expect(screen.getByText('当前范围还没有智能体会话，发送第一条消息后会自动创建。')).toBeInTheDocument()
  })
})
