/**
 * 文件功能：集中管理 Agent 会话选择、新建虚拟会话、显式打开工作页与会话菜单交互逻辑。
 */
import type { Ref } from 'vue'

import type { AgentSessionItem } from '@/types/api'
import { resolveSessionScope, setSelectedSession } from '@/components/agent/agent-session-scope'
import { Message } from '@/utils/message'

export interface AgentSessionNavigationContext {
  activeSessionId: Ref<string>
  manuallySelectedSessionId: Ref<string>
  sessionMenuVisible: Ref<boolean>
  virtualNewSessionKey: Ref<string | number | null>
  virtualNewSessionSequence: Ref<number>
  getActiveSessionRouteLocation: () => string | null
  getAgentId: () => string
  getAgentIssueDetail: () => string
  getHasBindingIssue: () => boolean
  getRouteAvailable: () => boolean
  getRouteFullPath: () => string
  getRoutePath: () => string
  getRouteUnavailableReason: () => string | undefined
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
    enterVirtualNewSession(`manual:${context.virtualNewSessionSequence.value}`)
  }

  function handleVirtualNewSession(autoCreateKey: string | number) {
    if (context.getHasBindingIssue()) {
      Message.error(context.getAgentIssueDetail())
      return
    }
    if (!context.getRouteAvailable()) {
      return
    }
    enterVirtualNewSession(autoCreateKey)
  }

  function openActiveSessionRoute() {
    const targetLocation = context.getActiveSessionRouteLocation()
    if (!targetLocation || isCurrentRouteTarget(targetLocation)) {
      return
    }
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

    context.activeSessionId.value = sessionId
  }

  function enterVirtualNewSession(virtualKey: string | number) {
    context.virtualNewSessionKey.value = virtualKey
    context.activeSessionId.value = ''
    context.manuallySelectedSessionId.value = ''
    context.sessionMenuVisible.value = false
  }

  function isCurrentRouteTarget(targetLocation: string): boolean {
    return targetLocation === context.getRouteFullPath() || targetLocation === context.getRoutePath()
  }

  return {
    handleCreateSession,
    handleSwitchSession,
    handleVirtualNewSession,
    openActiveSessionRoute,
    toggleSessionMenu,
    closeSessionMenu,
  }
}
