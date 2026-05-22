/**
 * 文件功能：验证智能体会话切换下拉的数量展示、最近会话限制与标题搜索。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

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

function renderControls(sessions: AgentSessionItem[], props: Record<string, unknown> = {}) {
  return render(AgentSessionControls, {
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
}

describe('AgentSessionControls', () => {
  it('下拉头部应隐藏当前会话标题，并把会话数量放到右侧', () => {
    renderControls([createSession(1), createSession(2)])

    expect(screen.getByText('会话切换')).toBeInTheDocument()
    expect(screen.getByText('共 2 个')).toBeInTheDocument()
    expect(screen.queryByText('当前会话标题不应出现在下拉头部')).not.toBeInTheDocument()
  })

  it('无搜索时最多只渲染最近 50 条会话', () => {
    renderControls(Array.from({ length: 60 }, (_, index) => createSession(index + 1)))

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
    renderControls(sessions)

    await fireEvent.update(screen.getByLabelText('搜索会话标题'), '品牌')

    expect(screen.getByText('匹配 1 个')).toBeInTheDocument()
    expect(screen.getByText('品牌策略复盘')).toBeInTheDocument()
    expect(screen.queryByText('会话 1')).not.toBeInTheDocument()
  })
})
