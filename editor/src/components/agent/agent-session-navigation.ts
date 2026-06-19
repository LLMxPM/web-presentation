/**
 * 文件功能：集中管理 Agent 会话选择、新建虚拟会话、路由跳转与会话菜单交互逻辑。
 */
import type { Ref } from 'vue'

import type { AgentScopeContext, AgentSessionItem } from '@/types/api'
import { buildSessionRouteLocation, resolveSessionScope, setSelectedSession } from '@/components/agent/agent-session-scope'
import { Message } from '@/utils/message'

export interface AgentSessionNavigationContext {
  activeSessionId: Ref<string>
  manuallySelectedSessionId: Ref<string>
  pendingRouteSessionId: Ref<string>
  pendingUnavailableSessionSelectionKey: Ref<string | number | null>
  sessionMenuVisible: Ref<boolean>
  virtualNewSessionKey: Ref<string | number | null>
  virtualNewSessionSequence: Ref<number>
  getActiveSessionRouteLocation: () => string | null
  getActiveSessionScope: () => AgentScopeContext | null
  getAgentId: () => string
  getAgentIssueDetail: () => string
  getAutoNavigateTarget: () => string | null | undefined
  getHasBindingIssue: () => boolean
  getRouteAvailable: () => boolean
  getRouteFullPath: () => string
  getRoutePath: () => string
  getRouteUnavailableReason: () => string | undefined
  getScope: () => AgentScopeContext
  getSessions: () => AgentSessionItem[]
  pushRoute: (target: string) => void
}

/**
 * 返回 Agent 会话导航相关事件处理器，避免面板组件直接承载路由分支。
 */
export function useAgentSessionNavigation(context: AgentSessionNavigationContext) {
  function handleCreateSession() {
    if (context.getHasBindingIssue()) {
      Message.error(context.getAgentIssueDetail())
      return
    }
    if (!context.getRouteAvailable()) {
      Message.warning(context.getRouteUnavailableReason() || '当前路由缺少工作空间上下文。')
      return
    }
    context.virtualNewSessionSequence.value += 1
    enterVirtualNewSession(`manual:${context.virtualNewSessionSequence.value}`, null)
  }

  function handleVirtualNewSession(autoCreateKey: string | number) {
    if (context.getHasBindingIssue()) {
      Message.error(context.getAgentIssueDetail())
      return
    }
    if (!context.getRouteAvailable()) {
      if (selectFirstRunnableSession()) {
        return
      }
      context.pendingUnavailableSessionSelectionKey.value = autoCreateKey
      return
    }
    enterVirtualNewSession(autoCreateKey, context.getAutoNavigateTarget())
  }

  function shouldAutoSelectRunnableSessionForUnavailableRoute(): boolean {
    if (
      context.getRouteAvailable()
      || context.getAgentId() !== 'agent-coordinator'
      || context.getScope().project_id
    ) {
      return false
    }
    if (
      context.activeSessionId.value
      && context.manuallySelectedSessionId.value === context.activeSessionId.value
    ) {
      return false
    }
    if (context.pendingUnavailableSessionSelectionKey.value) {
      return true
    }
    if (!context.activeSessionId.value) {
      return true
    }
    return !context.getActiveSessionScope()?.project_id
  }

  function selectFirstRunnableSession(): boolean {
    const targetSession = context.getSessions().find((session) => {
      const sessionScope = resolveSessionScope(session)
      if (!sessionScope || !buildSessionRouteLocation(session)) {
        return false
      }
      if (context.getAgentId() === 'agent-coordinator' && !sessionScope.project_id) {
        return false
      }
      return true
    })
    if (!targetSession) {
      return false
    }
    context.virtualNewSessionKey.value = null
    context.pendingRouteSessionId.value = ''
    context.manuallySelectedSessionId.value = ''
    context.activeSessionId.value = targetSession.session_id
    return true
  }

  function openActiveSessionRoute() {
    const targetLocation = context.getActiveSessionRouteLocation()
    if (!targetLocation || isCurrentRouteTarget(targetLocation)) {
      return
    }
    context.pendingRouteSessionId.value = context.activeSessionId.value
    context.pushRoute(targetLocation)
  }

  function toggleSessionMenu() {
    if (context.getHasBindingIssue()) {
      return
    }
    context.sessionMenuVisible.value = !context.sessionMenuVisible.value
  }

  function closeSessionMenu() {
    context.sessionMenuVisible.value = false
  }

  function handleSwitchSession(sessionId: string) {
    closeSessionMenu()
    context.virtualNewSessionKey.value = null
    context.manuallySelectedSessionId.value = sessionId
    const session = context.getSessions().find(item => item.session_id === sessionId)
    if (!session) {
      context.activeSessionId.value = sessionId
      return
    }

    const sessionScope = resolveSessionScope(session)
    if (sessionScope) {
      setSelectedSession(sessionScope, context.getAgentId(), sessionId)
    }

    const targetLocation = buildSessionRouteLocation(session)
    context.activeSessionId.value = sessionId
    if (targetLocation && targetLocation !== context.getRouteFullPath()) {
      context.pendingRouteSessionId.value = sessionId
      context.pushRoute(targetLocation)
      return
    }

    context.pendingRouteSessionId.value = ''
  }

  function enterVirtualNewSession(virtualKey: string | number, navigateTarget: string | null | undefined) {
    context.virtualNewSessionKey.value = virtualKey
    context.activeSessionId.value = ''
    context.pendingRouteSessionId.value = ''
    context.manuallySelectedSessionId.value = ''
    context.sessionMenuVisible.value = false
    if (navigateTarget && navigateTarget !== context.getRouteFullPath()) {
      context.pushRoute(navigateTarget)
    }
  }

  function isCurrentRouteTarget(targetLocation: string): boolean {
    return targetLocation === context.getRouteFullPath() || targetLocation === context.getRoutePath()
  }

  return {
    handleCreateSession,
    handleSwitchSession,
    handleVirtualNewSession,
    openActiveSessionRoute,
    selectFirstRunnableSession,
    shouldAutoSelectRunnableSessionForUnavailableRoute,
    toggleSessionMenu,
    closeSessionMenu,
  }
}
