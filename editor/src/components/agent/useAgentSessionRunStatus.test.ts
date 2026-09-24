/**
 * 文件功能：验证会话运行徽标与临时名判定。
 */
import { describe, expect, it } from 'vitest'

import {
  getAgentSessionRunBadge,
  shouldAutonameSession,
} from '@/components/agent/useAgentSessionRunStatus'
import type { useAgentSessionStore } from '@/stores/agent-session'
import type { AgentSessionItem, AgentTimelineItem } from '@/types/api'

/** 构造只读 store 视图，覆盖徽标判定所需字段。 */
function fakeStore(activeRun: { status: string, pending_requirement?: unknown } | null, ui: { interrupting?: boolean, stream?: { streaming?: boolean } } = {}) {
  return {
    getSession: () => ({
      runtime: {
        activeRun,
        stream: { streaming: ui.stream?.streaming ?? false },
      },
      ui: { interrupting: ui.interrupting ?? false },
    }),
  } as unknown as ReturnType<typeof useAgentSessionStore>
}

describe('useAgentSessionRunStatus', () => {
  it('paused / cancelling / running 映射到对应徽标', () => {
    expect(getAgentSessionRunBadge('a', fakeStore({ status: 'paused' }))).toEqual({ label: '待确认', tone: 'warning' })
    expect(getAgentSessionRunBadge('a', fakeStore({ status: 'cancelling' }))).toEqual({ label: '停止中', tone: 'warning' })
    expect(getAgentSessionRunBadge('a', fakeStore({ status: 'running' }, { interrupting: true }))).toEqual({ label: '停止中', tone: 'info' })
    expect(getAgentSessionRunBadge('a', fakeStore({ status: 'failed' }))).toEqual({ label: '失败', tone: 'danger' })
  })

  it('临时名且已有助手回复时才允许自动命名', () => {
    const items = [
      { kind: 'message', role: 'user', content: '你好' },
      { kind: 'message', role: 'assistant', content: '在的' },
    ] as AgentTimelineItem[]
    const session = { session_name: '智能体会话 会话' } as AgentSessionItem
    expect(shouldAutonameSession(session, items, ['', '智能体会话 会话'])).toBe(true)
    expect(shouldAutonameSession({ ...session, session_name: '自定义' }, items, ['', '智能体会话 会话'])).toBe(false)
    expect(shouldAutonameSession(session, items.slice(0, 1), ['', '智能体会话 会话'])).toBe(false)
  })
})
