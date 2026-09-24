/**
 * 文件功能：验证会话偏好排队保存时不会把旧会话修改写到新会话。
 */
import { computed, effectScope, nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { updateAgentSessionPreferences } from '@/api/ai'
import { useAgentSessionPreferences } from '@/components/agent/useAgentSessionPreferences'
import type { AgentScopeContext, AgentSessionItem } from '@/types/api'

vi.mock('@/api/ai', () => ({
  updateAgentSessionPreferences: vi.fn(),
}))

/** 创建具备下一轮偏好字段的会话夹具。 */
function session(sessionId: string): AgentSessionItem {
  return {
    session_id: sessionId,
    workspace_id: 1,
    agent_id: 'agent-coordinator',
    focus_mode: 'follow_route',
    pinned_project_id: null,
    work_scope_mode: 'workspace',
    allowed_project_ids: [],
  } as AgentSessionItem
}

/** 暂停一次保存请求，用于在旧会话在途时切换会话。 */
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

describe('useAgentSessionPreferences', () => {
  beforeEach(() => vi.clearAllMocks())

  it('会话 A 保存排队期间切到 B，后续保存仍分别使用各自的会话 ID 与完整草稿', async () => {
    const firstSave = deferred<AgentSessionItem>()
    const sessions = ref<Record<string, AgentSessionItem>>({ a: session('a'), b: session('b') })
    const activeSessionId = ref('a')
    const calls: Array<{ sessionId: string, payload: AgentSessionItem }> = []
    vi.mocked(updateAgentSessionPreferences).mockImplementation(async (sessionId, _workspaceId, payload) => {
      calls.push({ sessionId, payload: payload as AgentSessionItem })
      if (sessionId === 'a' && calls.filter(call => call.sessionId === 'a').length === 1) {
        return firstSave.promise
      }
      return { ...sessions.value[sessionId], ...payload }
    })
    const scope = effectScope()
    const preferences = scope.run(() => useAgentSessionPreferences({
      activeSessionId,
      activeSession: computed(() => sessions.value[activeSessionId.value] ?? null),
      scope: computed<AgentScopeContext>(() => ({ scope_type: 'workspace', workspace_id: 1, source: 'test' })),
      currentRouteScope: computed<AgentScopeContext>(() => ({ scope_type: 'workspace', workspace_id: 1, source: 'test' })),
      workspaceProjects: computed(() => []),
      getSession: sessionId => sessions.value[sessionId] ?? null,
      rememberSession: updated => { sessions.value = { ...sessions.value, [updated.session_id]: updated } },
      invalidateSessions: async () => {},
    }))!

    preferences.handleFocusModeChange('workspace')
    preferences.handleWorkScopeModeChange('selected_projects')
    activeSessionId.value = 'b'
    await nextTick()
    preferences.handleFocusModeChange('workspace')
    expect(calls.map(call => call.sessionId)).toEqual(['a', 'b'])
    expect(preferences.sessionPreferences.value.work_scope_mode).toBe('workspace')

    firstSave.resolve({ ...sessions.value.a, ...calls[0].payload })
    await vi.waitFor(() => expect(calls).toHaveLength(3))
    expect(calls[2].sessionId).toBe('a')
    expect(calls[2].payload.focus_mode).toBe('workspace')
    expect(calls[2].payload.work_scope_mode).toBe('selected_projects')
    expect(preferences.sessionPreferences.value.work_scope_mode).toBe('workspace')
    scope.stop()
  })

  it('保存失败但仍有更新草稿时，继续提交完整草稿而不是丢掉后续编辑', async () => {
    let rejectFirst!: (error: unknown) => void
    const firstSave = new Promise<AgentSessionItem>((_, reject) => {
      rejectFirst = reject
    })
    firstSave.catch(() => {})
    const sessions = ref<Record<string, AgentSessionItem>>({ a: session('a') })
    const activeSessionId = ref('a')
    const calls: Array<{ sessionId: string, payload: Record<string, unknown> }> = []
    vi.mocked(updateAgentSessionPreferences).mockImplementation(async (sessionId, _workspaceId, payload) => {
      calls.push({ sessionId, payload: payload as Record<string, unknown> })
      if (calls.length === 1) {
        return firstSave
      }
      return { ...sessions.value[sessionId], ...(payload as Partial<AgentSessionItem>) }
    })
    const scope = effectScope()
    const preferences = scope.run(() => useAgentSessionPreferences({
      activeSessionId,
      activeSession: computed(() => sessions.value[activeSessionId.value] ?? null),
      scope: computed<AgentScopeContext>(() => ({ scope_type: 'workspace', workspace_id: 1, source: 'test' })),
      currentRouteScope: computed<AgentScopeContext>(() => ({ scope_type: 'workspace', workspace_id: 1, source: 'test' })),
      workspaceProjects: computed(() => [{ id: 51, name: '经营项目' }]),
      getSession: sessionId => sessions.value[sessionId] ?? null,
      rememberSession: updated => { sessions.value = { ...sessions.value, [updated.session_id]: updated } },
      invalidateSessions: async () => {},
    }))!

    preferences.handleWorkScopeModeChange('selected_projects')
    await Promise.resolve()
    preferences.toggleAllowedProject(51)
    rejectFirst(new Error('save failed'))

    await vi.waitFor(() => expect(calls).toHaveLength(2))
    expect(calls[1].sessionId).toBe('a')
    expect(calls[1].payload.work_scope_mode).toBe('selected_projects')
    expect(calls[1].payload.allowed_project_ids).toEqual([51])
    expect(preferences.sessionPreferences.value.allowed_project_ids).toEqual([51])
    scope.stop()
  })
})
