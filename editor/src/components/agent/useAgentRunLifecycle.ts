/**
 * 文件功能：协调 Agent Run 的启动、SSE 订阅、取消、快照收敛及领域刷新通知。
 */
import { computed, onBeforeUnmount, watch, type ComputedRef, type Ref, type WritableComputedRef } from 'vue'
import type { QueryClient } from '@tanstack/vue-query'

import {
  AgentRequestError,
  AgentStreamInterruptedError,
  cancelAgentSessionActiveRun,
  getAgentSessionRuntime,
  startAgentRun,
  streamAgentRunEvents,
  type AgentReasoningPolicy,
} from '@/api/ai'
import { getErrorMessage } from '@/api/http'
import { buildRunIssueState } from '@/components/agent/agent-conversation-panel'
import { buildMutationRefreshEvents, type AgentMutationRefreshEvent } from '@/components/agent/agent-mutation-refresh'
import { normalizeAgentRunEvent } from '@/components/agent/agent-run-state'
import type { SessionFocusPreferences } from '@/components/agent/useAgentSessionPreferences'
import {
  isAgentSessionRunning,
  useAgentSessionRunStatus,
} from '@/components/agent/useAgentSessionRunStatus'
import { useAgentStreamControllers } from '@/components/agent/agent-stream-controllers'
import { useAgentForceCancelTicker } from '@/components/agent/agent-force-cancel-ticker'
import type { useAgentSessionStore } from '@/stores/agent-session'
import type {
  AgentActiveRunItem,
  AgentDescriptor,
  AgentImageAttachmentItem,
  AgentPendingRequirement,
  AgentRunEvent,
  AgentScopeContext,
  AgentSessionItem,
  AgentSessionRuntimeSnapshot,
} from '@/types/api'
import { logClientWarning } from '@/utils/client-logger'
import { createClientUuid } from '@/utils/id'
import { Message } from '@/utils/message'

interface AgentRunLifecycleContext {
  activeSessionId: Ref<string>
  activeRun: ComputedRef<AgentActiveRunItem | null>
  activeSession: ComputedRef<AgentSessionItem | null>
  agentId: ComputedRef<string>
  agentDisplayName: ComputedRef<string>
  selectedAgent: ComputedRef<AgentDescriptor | null>
  contextTitle: ComputedRef<string>
  nextRunFocus: ComputedRef<AgentScopeContext>
  sessionPreferences: ComputedRef<SessionFocusPreferences>
  composerText: Ref<string>
  pendingImageAttachments: WritableComputedRef<AgentImageAttachmentItem[]>
  pendingRequirement: WritableComputedRef<AgentPendingRequirement | null>
  lastRunIssue: WritableComputedRef<{ title: string, detail: string } | null>
  hasBindingIssue: ComputedRef<boolean>
  agentIssueDetail: ComputedRef<string>
  composerContextIssue: ComputedRef<string>
  visualAttachmentCapabilityAvailable: ComputedRef<boolean>
  selectedRunLlmConfigId: Ref<number | null>
  selectedRunReasoning: Ref<AgentReasoningPolicy>
  agentSessionStore: ReturnType<typeof useAgentSessionStore>
  queryClient: QueryClient
  runtimeSnapshot: Ref<AgentSessionRuntimeSnapshot | undefined>
  refetchSessions: () => Promise<AgentSessionItem[]>
  refetchActiveRuntime: () => Promise<AgentSessionRuntimeSnapshot | null>
  rememberSessions: (sessions: AgentSessionItem[]) => void
  resolveSessionRuntimeRequest: (sessionId: string, sessions?: AgentSessionItem[]) => { scope: AgentScopeContext, agentId: string }
  ensureActiveSession: () => Promise<string>
  isSessionSendInFlight: (sessionId: string) => boolean
  setSessionSendInFlight: (sessionId: string, inFlight: boolean) => void
  emitRefreshEvent: (event: AgentMutationRefreshEvent) => void
}

/** 每个面板实例管理自己的流控制器，后台 Run 仍由服务端持有。 */
export function useAgentRunLifecycle(context: AgentRunLifecycleContext) {
  const {
    activeSessionId,
    activeRun,
    activeSession,
    agentId,
    agentDisplayName,
    selectedAgent,
    contextTitle,
    nextRunFocus,
    sessionPreferences,
    composerText,
    pendingImageAttachments,
    pendingRequirement,
    lastRunIssue,
    hasBindingIssue,
    agentIssueDetail,
    composerContextIssue,
    visualAttachmentCapabilityAvailable,
    selectedRunLlmConfigId,
    selectedRunReasoning,
    agentSessionStore,
    queryClient,
    runtimeSnapshot,
    refetchSessions,
    refetchActiveRuntime,
    rememberSessions,
    resolveSessionRuntimeRequest,
    ensureActiveSession,
    isSessionSendInFlight,
    setSessionSendInFlight,
    emitRefreshEvent,
  } = context
  let componentDisposed = false
  const {
    abortAllStreamControllers,
    clearStreamAbortController,
    createStreamAbortController,
    getStreamAbortController,
    hasStreamAbortController,
  } = useAgentStreamControllers()
  const { forceCancelTick, startForceCancelTicker, stopForceCancelTicker } = useAgentForceCancelTicker()
  const { getSessionRunBadge, maybeAutonameActiveSession } = useAgentSessionRunStatus({
    agentSessionStore,
    getActiveSessionId: () => activeSessionId.value,
    getSelectedAgent: () => selectedAgent.value,
    getContextTitle: () => contextTitle.value,
    resolveSessionRuntimeRequest,
    queryClient,
    refetchSessions,
  })
  const isStreaming = computed(() => isAgentSessionRunning(activeSessionId.value, agentSessionStore))
  const isInterrupting = computed(() => agentSessionStore.getSession(activeSessionId.value)?.ui.interrupting ?? false)

  /**
   * 更新当前会话的流式执行标记，用于脱离 task store 后控制按钮状态。
   */
  function setSessionStreaming(sessionId: string, value: boolean) {
    agentSessionStore.setStreaming(sessionId, value)
  }

  /**
   * 判断 active-run 是否需要继续订阅后台事件。
   */
  function shouldSubscribeRunEvents(run: AgentActiveRunItem) {
    return Boolean(run.run_id && (run.status === 'pending' || run.status === 'running' || run.status === 'waiting_external' || run.status === 'cancelling'))
  }

  /**
   * 判断 runtime 快照是否属于当前会话；路由变化时仍允许保留并刷新原会话。
   */
  function isRuntimeSnapshotForCurrentSession(runtime: AgentSessionRuntimeSnapshot) {
    if (runtime.session.session_id !== activeSessionId.value) {
      return false
    }
    return true
  }

  /**
   * 判断 runtime 快照是否可以写入本地状态；流式中只接受暂停、终态或非当前 run 的权威收敛。
   */
  function shouldApplyRuntimeSnapshot(runtime: AgentSessionRuntimeSnapshot) {
    if (!isRuntimeSnapshotForCurrentSession(runtime)) {
      return false
    }
    if (!isStreaming.value) {
      return true
    }
    const sessionId = activeSessionId.value
    const currentRunId = agentSessionStore.getSession(sessionId)?.runtime.stream.runId ?? null
    const snapshotRun = runtime.active_run ?? runtime.last_run
    if (!snapshotRun?.run_id || (currentRunId && snapshotRun.run_id !== currentRunId)) {
      return false
    }
    return runtime.active_run?.status === 'paused'
      || runtime.active_run?.status === 'waiting_external'
      || runtime.active_run?.status === 'cancelling'
      || runtime.active_run === null
  }

  /**
   * 订阅已存在后台 run 的事件流；用于刷新、切回会话和停止后的状态收敛。
   */
  function ensureRunEventSubscription(sessionId: string, run: AgentActiveRunItem, afterEventIndex = -1) {
    if (componentDisposed || !sessionId || !run.run_id || hasStreamAbortController(run.run_id)) {
      return
    }
    const streamAbortController = createStreamAbortController(run.run_id)
    const runtimeRequest = resolveSessionRuntimeRequest(sessionId)
    setSessionStreaming(sessionId, true)
    streamAgentRunEvents(
      sessionId,
      run.run_id,
      runtimeRequest.scope,
      {
        agent_id: runtimeRequest.agentId,
        event_index: Math.max(afterEventIndex, agentSessionStore.getLastSequence(sessionId, run.run_id)),
      },
      { onEvent: event => handleRunEvent(event, sessionId), signal: streamAbortController.signal },
    )
      .then(() => {
        if (!componentDisposed) {
          return finalizeRun(sessionId)
        }
        return undefined
      })
      .catch((error) => {
        if (error instanceof AgentStreamInterruptedError) {
          return
        }
        logClientWarning('Failed to subscribe agent run events', error)
      })
      .finally(() => {
        clearStreamAbortController(run.run_id, streamAbortController)
        setSessionStreaming(sessionId, false)
      })
  }

  /**
   * paused Run 进入新执行阶段时替换旧订阅，避免上一阶段的收尾请求吞掉重新订阅。
   */
  function restartRunEventSubscription(sessionId: string, run: AgentActiveRunItem, afterEventIndex = -1) {
    const previousController = getStreamAbortController(run.run_id)
    if (previousController) {
      previousController.abort()
      clearStreamAbortController(run.run_id, previousController)
    }
    ensureRunEventSubscription(sessionId, run, afterEventIndex)
  }

  /** 将后端 active-run 写入会话唯一运行态，requirement 随 paused Run 保存。 */
  function syncActiveRun(sessionId: string, run: AgentActiveRunItem | null) {
    agentSessionStore.setActiveRun(sessionId, run)
  }

  watch(
    runtimeSnapshot,
    (runtime) => {
      if (!activeSessionId.value || !runtime || !isRuntimeSnapshotForCurrentSession(runtime)) {
        return
      }
      const sessionId = activeSessionId.value
      rememberSessions([runtime.session])
      if (shouldApplyRuntimeSnapshot(runtime)) {
        agentSessionStore.applyRuntimeSnapshot(sessionId, runtime)
      }
      if (runtime.active_run && shouldSubscribeRunEvents(runtime.active_run)) {
        ensureRunEventSubscription(sessionId, runtime.active_run, agentSessionStore.getLastSequence(sessionId, runtime.active_run.run_id))
      }
    },
    { immediate: true },
  )

  /**
   * 发送一条用户消息并启动新的智能体 run。
   */
  async function handleSend() {
    if (hasBindingIssue.value) {
      Message.error(agentIssueDetail.value)
      return
    }
    if (composerContextIssue.value) {
      Message.warning(composerContextIssue.value)
      return
    }
    const message = composerText.value.trim()
    const attachments = [...pendingImageAttachments.value]
    const draftSessionId = activeSessionId.value
    if ((!message && attachments.length === 0) || isStreaming.value || isSessionSendInFlight(draftSessionId)) return
    if (attachments.length && !visualAttachmentCapabilityAvailable.value) {
      Message.error('请先在 AI 设置中配置图片理解或图片生成模型。')
      return
    }
    const runAgentDisplayName = agentDisplayName.value

    setSessionSendInFlight(draftSessionId, true)
    let sessionId = ''
    try {
      sessionId = await ensureActiveSession()
    } catch (error) {
      setSessionSendInFlight(draftSessionId, false)
      Message.error(getErrorMessage(error, '初始化智能体会话失败。'))
      return
    }
    if (sessionId !== draftSessionId) {
      setSessionSendInFlight(draftSessionId, false)
      setSessionSendInFlight(sessionId, true)
    }
    const runtimeRequest = resolveSessionRuntimeRequest(sessionId)
    const runScope = { ...nextRunFocus.value }
    const runAgentId = runtimeRequest.agentId

    composerText.value = ''
    pendingImageAttachments.value = []
    pendingRequirement.value = null
    lastRunIssue.value = null
    agentSessionStore.clearMutationRefreshEvents(sessionId)

    const runId = createClientUuid()
    agentSessionStore.beginLocalRun(sessionId, message, attachments, runId)
    setSessionStreaming(sessionId, true)

    try {
      agentSessionStore.setCurrentRunId(sessionId, runId)
      // 乐观 Run 的工作范围与 nextRunFocus 同源，避免新会话尚未回填 activeSession 时闪变。
      syncActiveRun(sessionId, {
        run_id: runId,
        session_id: sessionId,
        agent_id: runAgentId,
        status: 'running',
        focus: runScope,
        work_scope_mode: sessionPreferences.value.work_scope_mode,
        allowed_project_ids: [...sessionPreferences.value.allowed_project_ids],
        focus_version: activeSession.value?.focus_version ?? 0,
        pending_requirement: null,
        content: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        cancel_requested_at: null,
        event_index: -1,
      })
      const response = await startAgentRun(sessionId, runScope, {
        run_id: runId,
        message,
        agent_id: runAgentId,
        image_attachment_ids: attachments.map(attachment => attachment.id),
        llm_config_id: selectedRunLlmConfigId.value,
        reasoning: { ...selectedRunReasoning.value },
      })
      syncActiveRun(sessionId, {
        ...(activeRun.value ?? {
          run_id: response.run_id,
          session_id: response.session_id,
          agent_id: runAgentId,
          focus: runScope,
          work_scope_mode: sessionPreferences.value.work_scope_mode,
          allowed_project_ids: [...sessionPreferences.value.allowed_project_ids],
          focus_version: activeSession.value?.focus_version ?? 0,
          pending_requirement: null,
          content: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          cancel_requested_at: null,
        }),
        run_id: response.run_id,
        session_id: response.session_id,
        status: response.status,
        event_index: response.event_index,
      })
      const backgroundRun = agentSessionStore.getSession(sessionId)?.runtime.activeRun ?? null
      if (backgroundRun) {
        ensureRunEventSubscription(sessionId, backgroundRun, response.event_index)
      }
    } catch (error) {
      if (isAgentRunActiveError(error)) {
        await recoverActiveRunAfterConflict(sessionId)
        return
      }
      const detail = getErrorMessage(error, '智能体执行失败。')
      const issue = buildRunIssueState(detail, runAgentDisplayName)
      agentSessionStore.setLastIssue(sessionId, issue)
      Message.warning(issue.title)
    } finally {
      if (runId) {
        const controller = getStreamAbortController(runId)
        if (controller) {
          clearStreamAbortController(runId, controller)
        }
      }
      setSessionSendInFlight(sessionId, false)
      if (!runId || !hasStreamAbortController(runId)) {
        setSessionStreaming(sessionId, false)
      }
    }
  }

  /**
   * 中断当前仍在执行中的 run；停止语义必须先写入后端，SSE 订阅只负责接收结果。
   */
  async function handleInterruptRun() {
    const sessionId = activeSessionId.value
    if (!sessionId || !isStreaming.value || isInterrupting.value) {
      return
    }

    try {
      agentSessionStore.setInterrupting(sessionId, true)
      const targetRunId = activeRun.value?.run_id || agentSessionStore.getSession(sessionId)?.runtime.stream.runId
      if (!targetRunId) {
        throw new Error('当前运行缺少 run_id，无法停止。')
      }
      const runtimeRequest = resolveSessionRuntimeRequest(sessionId)
      const response = await cancelAgentSessionActiveRun(sessionId, runtimeRequest.scope, {
        agent_id: runtimeRequest.agentId,
      })
      syncActiveRun(sessionId, {
        run_id: response.run_id,
        session_id: response.session_id,
        agent_id: runtimeRequest.agentId,
        status: 'cancelling',
        focus: activeRun.value?.focus ?? nextRunFocus.value,
        work_scope_mode: activeRun.value?.work_scope_mode ?? activeSession.value?.work_scope_mode ?? 'workspace',
        allowed_project_ids: activeRun.value?.allowed_project_ids ?? activeSession.value?.allowed_project_ids ?? [],
        focus_version: activeRun.value?.focus_version ?? activeSession.value?.focus_version ?? 0,
        pending_requirement: null,
        content: null,
        created_at: activeRun.value?.created_at ?? new Date().toISOString(),
        updated_at: new Date().toISOString(),
        cancel_requested_at: new Date().toISOString(),
        event_index: activeRun.value?.event_index ?? -1,
      })
      ensureRunEventSubscription(sessionId, {
        run_id: response.run_id,
        session_id: response.session_id,
        agent_id: runtimeRequest.agentId,
        status: 'cancelling',
        focus: activeRun.value?.focus ?? nextRunFocus.value,
        work_scope_mode: activeRun.value?.work_scope_mode ?? activeSession.value?.work_scope_mode ?? 'workspace',
        allowed_project_ids: activeRun.value?.allowed_project_ids ?? activeSession.value?.allowed_project_ids ?? [],
        focus_version: activeRun.value?.focus_version ?? activeSession.value?.focus_version ?? 0,
        pending_requirement: null,
        content: null,
        created_at: activeRun.value?.created_at ?? new Date().toISOString(),
        updated_at: new Date().toISOString(),
        cancel_requested_at: new Date().toISOString(),
        event_index: activeRun.value?.event_index ?? -1,
      }, activeRun.value?.event_index ?? -1)
      window.setTimeout(() => {
        void refreshAfterStreamInterrupted(sessionId)
      }, 5000)
    } catch (error) {
      agentSessionStore.setInterrupting(sessionId, false)
      Message.error(getErrorMessage(error, '停止失败，请稍后再试。'))
    }
  }

  /**
   * 停止中超过兜底窗口后，允许用户强制释放当前会话占用。
   */
  async function handleForceCancelRun() {
    const sessionId = activeSessionId.value
    if (!sessionId || activeRun.value?.status !== 'cancelling') {
      return
    }
    try {
      const runtimeRequest = resolveSessionRuntimeRequest(sessionId)
      const response = await cancelAgentSessionActiveRun(sessionId, runtimeRequest.scope, {
        agent_id: runtimeRequest.agentId,
        force: true,
      })
      Message.info('已停止。')
      await finalizeRun(response.session_id, { preserveLocalCancelled: true })
    } catch (error) {
      Message.error(getErrorMessage(error, '强制结束失败，请稍后再试。'))
    }
  }

  /**
   * 流式中断后的刷新不阻塞按钮反馈；失败只记录日志，避免误报为执行失败。
   */
  async function refreshAfterStreamInterrupted(sessionId: string) {
    if (componentDisposed) {
      return
    }
    try {
      await finalizeRun(sessionId, { preserveLocalCancelled: true })
      const run = agentSessionStore.getSession(sessionId)?.runtime.activeRun ?? null
      if (run && shouldSubscribeRunEvents(run)) {
        ensureRunEventSubscription(sessionId, run, run.event_index ?? -1)
      }
    } catch (error) {
      logClientWarning('Failed to refresh after stream interruption', error)
    }
  }

  /**
   * 发送新消息遇到后端 active-run 冲突时，刷新状态并恢复事件订阅。
   */
  async function recoverActiveRunAfterConflict(sessionId: string) {
    await finalizeRun(sessionId)
    const run = agentSessionStore.getSession(sessionId)?.runtime.activeRun ?? null
    if (run && shouldSubscribeRunEvents(run)) {
      ensureRunEventSubscription(sessionId, run, run.event_index ?? -1)
    }
    Message.warning('当前会话已有未结束的智能体运行，已恢复运行状态。')
  }

  /**
   * 判断异常是否表示当前会话已有未结束 run。
   */
  function isAgentRunActiveError(error: unknown) {
    return error instanceof AgentRequestError && error.code === 'AI_SESSION_RUN_ACTIVE'
  }

  /**
   * 消费后端返回的流式事件，并同步更新消息、内嵌工具状态与待确认状态。
   */
  function handleRunEvent(event: AgentRunEvent, fallbackSessionId = activeSessionId.value) {
    const normalizedEvent = normalizeAgentRunEvent(event)
    const targetSessionId = normalizedEvent.session_id || fallbackSessionId
    if (!targetSessionId) {
      return
    }
    const isActiveEvent = targetSessionId === activeSessionId.value
    const result = agentSessionStore.applyRunEvent(targetSessionId, normalizedEvent, {
      agentId: agentId.value,
      agentDisplayName: agentDisplayName.value,
    })
    if (!result.applied) {
      return
    }
    switch (normalizedEvent.event) {
      case 'context.status':
        break
      case 'run.started':
        break
      case 'run.continued':
        break
      case 'run.waiting':
        break
      case 'message.delta':
        break
      case 'tool.started':
        break
      case 'tool.completed':
        appendMutationRefreshEvents(targetSessionId, normalizedEvent)
        emitMutationRefreshEvents(targetSessionId)
        break
      case 'tool.error':
        break
      case 'run.paused':
        break
      case 'run.cancelled':
        agentSessionStore.setInterrupting(targetSessionId, false)
        if (isActiveEvent) {
          Message.info('已停止。')
        }
        break
      case 'run.error':
        agentSessionStore.setInterrupting(targetSessionId, false)
        if (isActiveEvent && lastRunIssue.value) {
          Message.warning(lastRunIssue.value.title)
        }
        break
      case 'run.completed':
        agentSessionStore.setInterrupting(targetSessionId, false)
        break
      default:
        break
    }
  }

  /**
   * 记录工具写入带来的领域刷新事件，供工具完成即时派发和 run 结束兜底派发复用。
   */
  function appendMutationRefreshEvents(sessionId: string, event: AgentRunEvent): void {
    const runtimeRequest = resolveSessionRuntimeRequest(sessionId)
    const runFocus = agentSessionStore.getSession(sessionId)?.runtime.activeRun?.focus ?? runtimeRequest.scope
    const nextEvents = buildMutationRefreshEvents(event, {
      workspaceId: runFocus.workspace_id ?? null,
      projectId: runFocus.project_id ?? null,
      pageId: runFocus.page_id ?? null,
      componentId: runFocus.component_id ?? null,
    })
    if (!nextEvents.length) {
      return
    }
    agentSessionStore.appendMutationRefreshEvents(sessionId, nextEvents)
  }

  /**
   * 批量派发领域刷新事件；同类同目标事件只保留最后一次。
   */
  function emitMutationRefreshEvents(sessionId: string): void {
    const events = agentSessionStore.drainMutationRefreshEvents(sessionId)
    if (!events.length) {
      return
    }
    for (const event of events) {
      emitRefreshEvent(event)
    }
  }

  /**
   * 在一次流式运行结束后刷新会话与消息缓存。
   */
  async function finalizeRun(
    sessionId = activeSessionId.value,
    options: { preserveLocalCancelled?: boolean } = {},
  ) {
    if (!sessionId) {
      return
    }
    await queryClient.invalidateQueries({ queryKey: ['ai-sessions'] })
    await queryClient.invalidateQueries({ queryKey: ['ai-session-runtime'] })
    const latestSessions = await refetchSessions()
    const runtimeRequest = resolveSessionRuntimeRequest(sessionId, latestSessions)
    const latestRuntime = sessionId === activeSessionId.value
      ? await refetchActiveRuntime()
      : await getAgentSessionRuntime(sessionId, runtimeRequest.scope, runtimeRequest.agentId)
    const latestRun = latestRuntime?.active_run ?? null
    const localRunBeforeSnapshot = agentSessionStore.getSession(sessionId)?.runtime.activeRun ?? null
    const preserveLocalCancelled = Boolean(
      options.preserveLocalCancelled
      && localRunBeforeSnapshot?.status === 'cancelled'
      && shouldPreserveLocalCancelled(localRunBeforeSnapshot, latestRun),
    )
    if (latestRuntime) {
      rememberSessions([latestRuntime.session])
      agentSessionStore.applyRuntimeSnapshot(sessionId, latestRuntime)
    }
    if (preserveLocalCancelled && localRunBeforeSnapshot) {
      syncActiveRun(sessionId, localRunBeforeSnapshot)
    } else {
      syncActiveRun(sessionId, latestRun)
    }
    const latestContextStatus = latestRuntime?.context_status ?? null
    agentSessionStore.setContextStatus(sessionId, latestContextStatus)
    if (latestRuntime) {
      await maybeAutonameActiveSession(latestSessions, latestRuntime.timeline_items, sessionId)
    }
    emitMutationRefreshEvents(sessionId)
    agentSessionStore.setStreamingTimelineItemId(sessionId, null)
  }

  /**
   * 中断后后端可能短暂仍返回 running/pending；此时保留本地 cancelled，等下一轮刷新自然收敛。
   */
  function shouldPreserveLocalCancelled(localRun: AgentActiveRunItem, latestRun: AgentActiveRunItem | null) {
    return latestRun !== null
      && (!localRun.run_id || localRun.run_id === latestRun.run_id)
      && (latestRun.status === 'pending' || latestRun.status === 'running')
  }

  watch(activeRun, (run) => {
    if (run?.status === 'cancelling') startForceCancelTicker()
    else stopForceCancelTicker()
  }, { immediate: true })

  onBeforeUnmount(() => {
    componentDisposed = true
    abortAllStreamControllers()
    stopForceCancelTicker()
  })

  return {
    isStreaming,
    isInterrupting,
    forceCancelTick,
    setSessionStreaming,
    syncActiveRun,
    ensureRunEventSubscription,
    restartRunEventSubscription,
    handleSend,
    handleInterruptRun,
    handleForceCancelRun,
    finalizeRun,
    getSessionRunBadge,
  }
}
