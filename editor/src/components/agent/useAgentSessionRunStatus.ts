/**
 * 文件功能：提供会话运行状态判断、列表徽标与首轮完成后自动命名。
 */
import type { QueryClient } from '@tanstack/vue-query'

import { renameAgentSession } from '@/api/ai'
import type { useAgentSessionStore } from '@/stores/agent-session'
import type {
  AgentDescriptor,
  AgentScopeContext,
  AgentSessionItem,
  AgentTimelineItem,
} from '@/types/api'
import { logClientWarning } from '@/utils/client-logger'

interface AgentSessionRunStatusContext {
  agentSessionStore: ReturnType<typeof useAgentSessionStore>
  getActiveSessionId: () => string
  getSelectedAgent: () => AgentDescriptor | null
  getContextTitle: () => string
  resolveSessionRuntimeRequest: (sessionId: string, sessions?: AgentSessionItem[]) => { scope: AgentScopeContext, agentId: string }
  queryClient: QueryClient
  refetchSessions: () => Promise<AgentSessionItem[]>
}

/**
 * 判断指定会话是否仍在流式运行或处于平台非终态运行中。
 */
export function isAgentSessionRunning(
  sessionId: string,
  agentSessionStore: ReturnType<typeof useAgentSessionStore>,
): boolean {
  if (!sessionId) {
    return false
  }
  if (agentSessionStore.getSession(sessionId)?.runtime.stream.streaming) {
    return true
  }
  const run = agentSessionStore.getSession(sessionId)?.runtime.activeRun ?? null
  return run?.status === 'pending' || run?.status === 'running' || run?.status === 'waiting_external' || run?.status === 'cancelling'
}

/**
 * 返回会话列表中的运行状态标记。
 */
export function getAgentSessionRunBadge(
  sessionId: string,
  agentSessionStore: ReturnType<typeof useAgentSessionStore>,
) {
  const run = agentSessionStore.getSession(sessionId)?.runtime.activeRun ?? null
  if (run?.status === 'paused') {
    return {
      label: '待确认',
      tone: 'warning' as const,
    }
  }
  if (run?.status === 'cancelling') {
    return {
      label: '停止中',
      tone: 'warning' as const,
    }
  }
  if (isAgentSessionRunning(sessionId, agentSessionStore)) {
    return {
      label: agentSessionStore.getSession(sessionId)?.ui.interrupting ? '停止中' : '运行中',
      tone: 'info' as const,
    }
  }
  if (run?.status === 'failed') {
    return {
      label: '失败',
      tone: 'danger' as const,
    }
  }
  return null
}

/**
 * 判断当前会话是否仍应视为“临时名”，满足首轮完成后自动改名的条件。
 */
export function shouldAutonameSession(
  session: AgentSessionItem | null | undefined,
  items: AgentTimelineItem[],
  fallbackNames: Iterable<string>,
): boolean {
  if (!session) {
    return false
  }
  const visibleMessages = items.filter(item => item.kind === 'message' && (item.role === 'user' || item.role === 'assistant'))
  if (visibleMessages.length < 2 || !visibleMessages.some(item => item.role === 'assistant' && (item.content ?? '').trim())) {
    return false
  }
  const sessionName = (session.session_name || '').trim()
  return new Set(fallbackNames).has(sessionName)
}

/** 返回会话列表徽标与首轮自动命名入口。 */
export function useAgentSessionRunStatus(context: AgentSessionRunStatusContext) {
  const autoNamingSessionIds = new Set<string>()

  /** 返回会话列表中的运行状态标记。 */
  function getSessionRunBadge(sessionId: string) {
    return getAgentSessionRunBadge(sessionId, context.agentSessionStore)
  }

  /**
   * 在首轮消息完成后尝试自动生成会话名，避免会话列表长期停留在通用标题。
   */
  async function maybeAutonameActiveSession(
    sessions: AgentSessionItem[],
    items: AgentTimelineItem[],
    sessionId = context.getActiveSessionId(),
  ) {
    if (!sessionId || autoNamingSessionIds.has(sessionId)) {
      return
    }
    const session = sessions.find(item => item.session_id === sessionId)
    const fallbackNames = [
      '',
      context.getSelectedAgent()?.default_session_name ?? '',
      `${context.getContextTitle()} 会话`,
      `${context.getContextTitle()} 对话`,
    ]
    if (!shouldAutonameSession(session, items, fallbackNames)) {
      return
    }
    autoNamingSessionIds.add(sessionId)
    try {
      const runtimeRequest = context.resolveSessionRuntimeRequest(sessionId, sessions)
      await renameAgentSession(sessionId, runtimeRequest.scope, { autogenerate: true }, runtimeRequest.agentId)
      await context.queryClient.invalidateQueries({ queryKey: ['ai-sessions'] })
      await context.refetchSessions()
    } catch (error) {
      logClientWarning('Failed to autogenerate session name', error)
    } finally {
      autoNamingSessionIds.delete(sessionId)
    }
  }

  return {
    getSessionRunBadge,
    maybeAutonameActiveSession,
  }
}
