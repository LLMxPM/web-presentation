/**
 * 文件功能：管理 Agent 会话的下一轮焦点与工作集草稿，并按会话串行保存偏好。
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'

import { updateAgentSessionPreferences } from '@/api/ai'
import { getErrorMessage } from '@/api/http'
import type { AgentScopeContext, AgentSessionItem } from '@/types/api'
import { Message } from '@/utils/message'

export type SessionFocusPreferences = Pick<
  AgentSessionItem,
  'focus_mode' | 'pinned_project_id' | 'work_scope_mode' | 'allowed_project_ids'
>

interface SessionPreferenceContext {
  activeSessionId: Ref<string>
  activeSession: ComputedRef<AgentSessionItem | null>
  scope: ComputedRef<AgentScopeContext>
  currentRouteScope: ComputedRef<AgentScopeContext>
  workspaceProjects: ComputedRef<Array<{ id: number; name: string }>>
  getSession: (sessionId: string) => AgentSessionItem | null
  rememberSession: (session: AgentSessionItem) => void
  invalidateSessions: () => Promise<void>
}

/** 返回会话偏好状态与操作；所有在途保存都绑定发起时的 sessionId。 */
export function useAgentSessionPreferences(context: SessionPreferenceContext) {
  const draftPreferences = ref<SessionFocusPreferences>(createDefaultSessionPreferences())
  const preferencesBySession = ref<Record<string, SessionFocusPreferences>>({})
  const queuedBySession = new Map<string, SessionFocusPreferences>()
  const savingSessions = new Set<string>()
  const focusProjectSearch = ref('')
  const workScopeProjectSearch = ref('')

  const focusModeOptions = [
    { label: '跟随当前路由', value: 'follow_route' },
    { label: '固定项目', value: 'pinned_project' },
    { label: '工作空间级', value: 'workspace' },
  ]
  const workScopeOptions = [
    { label: '全部项目', value: 'workspace' },
    { label: '仅选择的项目', value: 'selected_projects' },
  ]
  const sessionPreferences = computed<SessionFocusPreferences>(() => {
    const sessionId = context.activeSessionId.value
    return sessionId
      ? preferencesBySession.value[sessionId] ?? (context.activeSession.value
          ? extractSessionPreferences(context.activeSession.value)
          : createDefaultSessionPreferences())
      : draftPreferences.value
  })
  const filteredFocusProjects = computed(() => filterProjectsByKeyword(context.workspaceProjects.value, focusProjectSearch.value))
  const filteredWorkScopeProjects = computed(() => filterProjectsByKeyword(context.workspaceProjects.value, workScopeProjectSearch.value))
  const pinnedProjectId = computed(() => (
    sessionPreferences.value.focus_mode === 'pinned_project' ? sessionPreferences.value.pinned_project_id : null
  ))
  const workScopeCompactLabel = computed(() => {
    const preferences = sessionPreferences.value
    if (preferences.work_scope_mode === 'workspace') return '全部项目'
    return preferences.allowed_project_ids.length ? `已选 ${preferences.allowed_project_ids.length} 项` : '未选择项目'
  })
  const workScopeBadgeClass = computed(() => {
    const preferences = sessionPreferences.value
    if (preferences.work_scope_mode === 'workspace') return 'bg-surface-muted text-text-muted'
    return preferences.allowed_project_ids.length
      ? 'bg-info-muted text-info-strong'
      : 'bg-warning-muted text-warning-strong'
  })
  const nextRunFocus = computed<AgentScopeContext>(() => {
    const preferences = sessionPreferences.value
    if (preferences.focus_mode === 'follow_route') return context.currentRouteScope.value
    if (preferences.focus_mode === 'pinned_project' && preferences.pinned_project_id) {
      const project = context.workspaceProjects.value.find(item => item.id === preferences.pinned_project_id)
      return {
        scope_type: 'project',
        workspace_id: context.scope.value.workspace_id,
        project_id: preferences.pinned_project_id,
        project_name: project?.name ?? null,
        source: 'session-pinned-project',
      }
    }
    return {
      scope_type: 'workspace',
      workspace_id: context.scope.value.workspace_id,
      workspace_name: context.currentRouteScope.value.workspace_name ?? context.scope.value.workspace_name ?? null,
      source: 'session-workspace',
    }
  })

  watch(context.activeSession, (session) => {
    if (!session || savingSessions.has(session.session_id) || queuedBySession.has(session.session_id)) return
    preferencesBySession.value = {
      ...preferencesBySession.value,
      [session.session_id]: extractSessionPreferences(session),
    }
  }, { immediate: true })

  /** 重置尚未创建会话的偏好草稿。 */
  function resetDraftPreferences(): void {
    draftPreferences.value = createDefaultSessionPreferences()
  }

  /** 乐观更新目标会话，并把完整偏好排入该会话自己的保存队列。 */
  function saveSessionPreferences(overrides: Partial<SessionFocusPreferences>): void {
    const current = sessionPreferences.value
    const next: SessionFocusPreferences = {
      focus_mode: overrides.focus_mode ?? current.focus_mode,
      pinned_project_id: overrides.pinned_project_id !== undefined ? overrides.pinned_project_id : current.pinned_project_id,
      work_scope_mode: overrides.work_scope_mode ?? current.work_scope_mode,
      allowed_project_ids: overrides.allowed_project_ids ? [...overrides.allowed_project_ids] : [...current.allowed_project_ids],
    }
    const sessionId = context.activeSessionId.value
    if (!sessionId || !context.activeSession.value) {
      draftPreferences.value = next
      return
    }
    preferencesBySession.value = { ...preferencesBySession.value, [sessionId]: next }
    queuedBySession.set(sessionId, next)
    void flushPreferenceSaves(sessionId)
  }

  /**
   * 每次请求使用固定会话身份；后续更改合并成该会话最新完整草稿。
   * 失败策略：仅回滚无后续草稿时的展示；已有更新草稿则继续提交，避免丢编辑。
   */
  async function flushPreferenceSaves(sessionId: string): Promise<void> {
    if (savingSessions.has(sessionId)) return
    savingSessions.add(sessionId)
    try {
      while (queuedBySession.has(sessionId)) {
        const payload = queuedBySession.get(sessionId)!
        queuedBySession.delete(sessionId)
        const session = context.getSession(sessionId)
        if (!session) break
        try {
          const updated = await updateAgentSessionPreferences(
            sessionId,
            session.workspace_id,
            payload,
            session.agent_id,
          )
          context.rememberSession(updated)
          await context.invalidateSessions()
          if (!queuedBySession.has(sessionId)) {
            preferencesBySession.value = {
              ...preferencesBySession.value,
              [sessionId]: extractSessionPreferences(updated),
            }
          }
        } catch (error) {
          Message.error(getErrorMessage(error, '保存会话焦点失败。'))
          // 失败只回滚当前展示；若用户已继续修改，保留完整草稿并串行提交，不丢掉后续编辑。
          if (!queuedBySession.has(sessionId)) {
            const currentSession = context.getSession(sessionId)
            if (currentSession) {
              preferencesBySession.value = {
                ...preferencesBySession.value,
                [sessionId]: extractSessionPreferences(currentSession),
              }
            }
            break
          }
        }
      }
    } finally {
      savingSessions.delete(sessionId)
    }
  }

  /** 切换焦点模式，固定项目优先采用当前路由项目或列表首项。 */
  function handleFocusModeChange(value: string | number | Array<string | number> | null): void {
    const focusMode = String(value) as AgentSessionItem['focus_mode']
    const nextPinnedProjectId = focusMode === 'pinned_project'
      ? (sessionPreferences.value.pinned_project_id ?? context.currentRouteScope.value.project_id ?? context.workspaceProjects.value[0]?.id ?? null)
      : null
    if (focusMode === 'pinned_project' && !nextPinnedProjectId) {
      Message.warning('当前工作空间没有可固定的项目。')
      return
    }
    const allowedProjectIds = focusMode === 'pinned_project'
      && sessionPreferences.value.work_scope_mode === 'selected_projects'
      && nextPinnedProjectId
      ? [...new Set([...sessionPreferences.value.allowed_project_ids, nextPinnedProjectId])]
      : undefined
    saveSessionPreferences({ focus_mode: focusMode, pinned_project_id: nextPinnedProjectId, allowed_project_ids: allowedProjectIds })
  }

  /** 固定项目始终并入显式工作集，只影响下一轮 Run。 */
  function handlePinnedProjectChange(projectId: number): void {
    if (!Number.isFinite(projectId) || projectId <= 0) return
    const allowedProjectIds = sessionPreferences.value.work_scope_mode === 'selected_projects'
      ? [...new Set([...sessionPreferences.value.allowed_project_ids, projectId])]
      : undefined
    saveSessionPreferences({ focus_mode: 'pinned_project', pinned_project_id: projectId, allowed_project_ids: allowedProjectIds })
  }

  /** 切换工作集模式，空显式工作集表示暂不允许项目操作。 */
  function handleWorkScopeModeChange(value: string): void {
    if (value === 'workspace') {
      saveSessionPreferences({ work_scope_mode: 'workspace', allowed_project_ids: [] })
    } else {
      saveSessionPreferences({
        work_scope_mode: 'selected_projects',
        allowed_project_ids: pinnedProjectId.value ? [pinnedProjectId.value] : [],
      })
    }
  }

  /** 增删工作集项目，固定焦点项目不可移除。 */
  function toggleAllowedProject(projectId: number): void {
    if (isPinnedProject(projectId)) return
    const selected = new Set(sessionPreferences.value.allowed_project_ids)
    if (selected.has(projectId)) selected.delete(projectId)
    else selected.add(projectId)
    saveSessionPreferences({ work_scope_mode: 'selected_projects', allowed_project_ids: [...selected] })
  }

  /** 判断项目是否同时为固定焦点。 */
  function isPinnedProject(projectId: number): boolean {
    return pinnedProjectId.value === projectId
  }

  /** 将当前过滤结果加入工作集，并保留固定项目。 */
  function selectAllWorkspaceProjects(): void {
    const ids = new Set(filteredWorkScopeProjects.value.map(project => project.id))
    if (pinnedProjectId.value) ids.add(pinnedProjectId.value)
    saveSessionPreferences({ work_scope_mode: 'selected_projects', allowed_project_ids: [...ids] })
  }

  /** 清空工作集，固定焦点项目继续保留。 */
  function clearSelectedProjects(): void {
    saveSessionPreferences({
      work_scope_mode: 'selected_projects',
      allowed_project_ids: pinnedProjectId.value ? [pinnedProjectId.value] : [],
    })
  }

  return {
    focusProjectSearch,
    workScopeProjectSearch,
    focusModeOptions,
    workScopeOptions,
    filteredFocusProjects,
    filteredWorkScopeProjects,
    sessionPreferences,
    nextRunFocus,
    pinnedProjectId,
    workScopeCompactLabel,
    workScopeBadgeClass,
    resetDraftPreferences,
    handleFocusModeChange,
    handlePinnedProjectChange,
    handleWorkScopeModeChange,
    toggleAllowedProject,
    isPinnedProject,
    selectAllWorkspaceProjects,
    clearSelectedProjects,
  }
}

/** 从服务端会话复制偏好，避免直接修改 API 缓存对象。 */
function extractSessionPreferences(session: AgentSessionItem): SessionFocusPreferences {
  return {
    focus_mode: session.focus_mode,
    pinned_project_id: session.pinned_project_id,
    work_scope_mode: session.work_scope_mode,
    allowed_project_ids: [...session.allowed_project_ids],
  }
}

/** 创建尚未落库的新会话默认偏好。 */
function createDefaultSessionPreferences(): SessionFocusPreferences {
  return {
    focus_mode: 'follow_route',
    pinned_project_id: null,
    work_scope_mode: 'workspace',
    allowed_project_ids: [],
  }
}

/** 按名称关键字过滤项目列表。 */
function filterProjectsByKeyword(projects: Array<{ id: number; name: string }>, keyword: string) {
  const query = keyword.trim().toLowerCase()
  return query ? projects.filter(project => project.name.toLowerCase().includes(query)) : projects
}
