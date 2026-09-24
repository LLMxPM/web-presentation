/**
 * 文件功能：查询并选择工作空间 Agent 会话，按会话自身范围读取运行态快照。
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'

import { getAgentSessionRuntime, listAgents, listAgentSessions } from '@/api/ai'
import { listProjects } from '@/api/catalog'
import {
  findLatestSessionForScope,
  getSelectedSession,
  getSelectedWorkspaceSession,
  resolveSessionScope,
  setSelectedSession,
  setSelectedWorkspaceSession,
  isSessionTargetCurrentScope,
} from '@/components/agent/agent-session-scope'
import type { AgentScopeContext, AgentSessionItem } from '@/types/api'

interface AgentSessionContextOptions {
  scope: ComputedRef<AgentScopeContext>
  agentId: ComputedRef<string>
  activeSessionId: Ref<string>
  virtualNewSessionKey: Ref<string | number | null>
}

/** 返回会话查询、选择和范围解析入口，切路由时保留已选会话。 */
export function useAgentSessionContext(options: AgentSessionContextOptions) {
  const { scope, agentId, activeSessionId, virtualNewSessionKey } = options
  const knownSessionsById = ref<Record<string, AgentSessionItem>>({})
  const manuallySelectedSessionId = ref('')
  const agentsQuery = useQuery(
    computed(() => ({
      queryKey: ['ai-agents', agentId.value, scope.value.scope_type, scope.value.workspace_id, scope.value.project_id, scope.value.page_id, scope.value.component_id, scope.value.source],
      queryFn: () => listAgents(scope.value, agentId.value),
      enabled: !!scope.value.workspace_id,
    })),
  )
  const sessionsQuery = useQuery(
    computed(() => ({
      queryKey: ['ai-sessions', agentId.value, scope.value.workspace_id, 'workspace'],
      queryFn: () => listAgentSessions(scope.value, agentId.value),
      enabled: !!scope.value.workspace_id,
    })),
  )
  const projectsQuery = useQuery(
    computed(() => ({
      queryKey: ['projects', 'agent-focus', scope.value.workspace_id],
      queryFn: () => listProjects({ workspace_id: scope.value.workspace_id, page: 1, page_size: 100 }),
      enabled: !!scope.value.workspace_id,
    })),
  )
  const workspaceProjects = computed(() => projectsQuery.data.value?.items ?? [])
  const normalizedSessions = computed(() => sessionsQuery.data.value?.map(normalizeSessionItem))
  const activeSession = computed<AgentSessionItem | null>(() => getSession(activeSessionId.value))
  const displayedSessions = computed<AgentSessionItem[] | undefined>(() => {
    const sessions = normalizedSessions.value
    const active = activeSession.value
    if (!active) return sessions
    if (!sessions) return [active]
    return sessions.some(item => item.session_id === active.session_id) ? sessions : [active, ...sessions]
  })
  const activeSessionScope = computed(() => activeSession.value ? resolveSessionScope(activeSession.value) : null)
  const activeSessionRuntimeScope = computed(() => activeSessionScope.value ?? scope.value)
  const activeSessionRuntimeAgentId = computed(() => activeSession.value?.agent_id ?? agentId.value)
  const runtimeQuery = useQuery(
    computed(() => ({
      queryKey: [
        'ai-session-runtime',
        activeSessionRuntimeAgentId.value,
        activeSessionId.value,
        activeSessionRuntimeScope.value.scope_type,
        activeSessionRuntimeScope.value.workspace_id,
        activeSessionRuntimeScope.value.project_id,
        activeSessionRuntimeScope.value.page_id,
        activeSessionRuntimeScope.value.component_id,
        activeSessionRuntimeScope.value.source,
      ],
      queryFn: () => getAgentSessionRuntime(
        activeSessionId.value,
        activeSessionRuntimeScope.value,
        activeSessionRuntimeAgentId.value,
      ),
      enabled: !!activeSessionId.value,
      refetchOnWindowFocus: true,
    })),
  )

  /** 规范旧测试夹具和并发缓存中的会话默认字段。 */
  function normalizeSessionItem(session: AgentSessionItem): AgentSessionItem {
    return {
      ...session,
      workspace_id: session.workspace_id ?? scope.value.workspace_id,
      focus_mode: session.focus_mode ?? 'follow_route',
      pinned_project_id: session.pinned_project_id ?? null,
      work_scope_mode: session.work_scope_mode ?? 'workspace',
      allowed_project_ids: session.allowed_project_ids ?? [],
      focus_version: session.focus_version ?? 0,
    }
  }

  /** 返回列表或曾读取快照中的会话信息。 */
  function getSession(sessionId: string): AgentSessionItem | null {
    if (!sessionId) return null
    const item = normalizedSessions.value?.find(candidate => candidate.session_id === sessionId)
      ?? knownSessionsById.value[sessionId]
      ?? null
    return item ? normalizeSessionItem(item) : null
  }

  /** 记住已见会话，以便后台 Run 在路由切换后仍用原范围收尾。 */
  function rememberSessions(sessions: AgentSessionItem[]): void {
    if (!sessions.length) return
    knownSessionsById.value = {
      ...knownSessionsById.value,
      ...Object.fromEntries(sessions.map(session => {
        const normalized = normalizeSessionItem(session)
        return [normalized.session_id, normalized]
      })),
    }
  }

  /** 从会话自身解析运行态请求范围，缺失时使用当前范围。 */
  function resolveSessionRuntimeRequest(sessionId: string, sessions: AgentSessionItem[] = normalizedSessions.value ?? []) {
    const session = sessions.find(item => item.session_id === sessionId) ?? knownSessionsById.value[sessionId] ?? null
    const sessionScope = session ? resolveSessionScope(session) : null
    return { scope: sessionScope ?? scope.value, agentId: session?.agent_id ?? agentId.value }
  }

  watch(
    () => [normalizedSessions.value, agentId.value] as const,
    ([sessions]) => {
      if (virtualNewSessionKey.value) {
        activeSessionId.value = ''
        return
      }
      if (sessions === undefined) return
      rememberSessions(sessions)
      if (!sessions.length) {
        if (!activeSession.value) activeSessionId.value = ''
        return
      }
      if (activeSessionId.value && sessions.some(item => item.session_id === activeSessionId.value)) return
      if (activeSession.value) return
      const workspaceSessionId = getSelectedWorkspaceSession(scope.value, agentId.value, sessions)
      if (workspaceSessionId) {
        activeSessionId.value = workspaceSessionId
        return
      }
      const exactSessionId = getSelectedSession(scope.value, agentId.value, sessions)
      activeSessionId.value = exactSessionId || findLatestSessionForScope(sessions, scope.value)?.session_id || ''
    },
    { immediate: true },
  )
  watch(activeSessionId, (sessionId) => {
    if (!sessionId) return
    const session = activeSession.value
    const sessionScope = session ? resolveSessionScope(session) : null
    if (sessionScope) {
      setSelectedSession(sessionScope, agentId.value, sessionId)
      setSelectedWorkspaceSession(sessionScope, agentId.value, sessionId)
    } else if (!session || isSessionTargetCurrentScope(session, scope.value)) {
      setSelectedSession(scope.value, agentId.value, sessionId)
      setSelectedWorkspaceSession(scope.value, agentId.value, sessionId)
    }
  })

  return {
    manuallySelectedSessionId,
    agentsQuery,
    sessionsQuery,
    projectsQuery,
    workspaceProjects,
    normalizedSessions,
    activeSession,
    displayedSessions,
    activeSessionScope,
    activeSessionRuntimeScope,
    activeSessionRuntimeAgentId,
    runtimeQuery,
    getSession,
    rememberSessions,
    resolveSessionRuntimeRequest,
  }
}
