/**
 * 文件功能：以会话为唯一状态分片，保存智能体运行态与会话交互状态。
 */
import { defineStore } from 'pinia'

import {
  applyAgentRunEvent,
  applyAgentRuntimeSnapshot,
  createAgentSessionRuntimeState,
  type AgentSessionRuntimeState,
} from '@/components/agent/agent-run-state'
import { compactMutationRefreshEvents, type AgentMutationRefreshEvent } from '@/components/agent/agent-mutation-refresh'
import {
  appendLocalRunTimelineItems,
  markPendingRequirementResolvedInTimeline,
} from '@/stores/agent-session-timeline'
import { logClientWarning } from '@/utils/client-logger'
import type {
  AgentActiveRunItem,
  AgentContextStatusItem,
  AgentFeedbackSelection,
  AgentImageAttachmentItem,
  AgentPendingRequirement,
  AgentRunEvent,
  AgentSessionRuntimeSnapshot,
  AgentTimelineItem,
} from '@/types/api'

export interface AgentSessionUiState {
  mutationRefreshEvents: AgentMutationRefreshEvent[]
  interrupting: boolean
  imageUploading: boolean
  hitlActionInFlight: boolean
  sendInFlight: boolean
}

export interface AgentSessionState {
  runtime: AgentSessionRuntimeState
  ui: AgentSessionUiState
}

/** 创建一个会话的运行态和交互态，避免两套映射维护同一字段。 */
function createSessionState(): AgentSessionState {
  return {
    runtime: createAgentSessionRuntimeState(),
    ui: {
      mutationRefreshEvents: [],
      interrupting: false,
      imageUploading: false,
      hitlActionInFlight: false,
      sendInFlight: false,
    },
  }
}

export const useAgentSessionStore = defineStore('agent-session', {
  state: () => ({
    sessions: {} as Record<string, AgentSessionState>,
  }),
  actions: {
    /** 返回已创建的会话分片；只读场景不为未知会话分配状态。 */
    getSession(sessionId: string): AgentSessionState | null {
      return sessionId ? this.sessions[sessionId] ?? null : null
    },
    /** 为指定会话创建唯一的状态分片。 */
    ensureSession(sessionId: string): AgentSessionState {
      if (!this.sessions[sessionId]) {
        this.sessions[sessionId] = createSessionState()
      }
      return this.sessions[sessionId]
    },
    /** 用服务端快照收敛指定会话，不改写其他会话的状态。 */
    applyRuntimeSnapshot(sessionId: string, snapshot: AgentSessionRuntimeSnapshot): void {
      if (!sessionId) return
      applyAgentRuntimeSnapshot(this.ensureSession(sessionId).runtime, {
        timelineItems: snapshot.timeline_items,
        activeRun: snapshot.active_run,
        lastRun: snapshot.last_run,
        pendingImageAttachments: snapshot.pending_attachments,
        contextStatus: snapshot.context_status,
        eventIndex: snapshot.event_index,
      })
    },
    /** 按事件序号更新指定会话的运行态。 */
    applyRunEvent(sessionId: string, event: AgentRunEvent, options: { agentId: string, agentDisplayName: string }) {
      if (!sessionId) return { applied: false, terminal: false }
      return applyAgentRunEvent(this.ensureSession(sessionId).runtime, event, options)
    },
    /** 替换指定会话的时间线，供服务端收敛和 HITL 回滚使用。 */
    setTimelineItems(sessionId: string, items: AgentTimelineItem[]): void {
      if (!sessionId) return
      this.ensureSession(sessionId).runtime.timelineItems = items
    },
    /** 在指定会话时间线后追加本地项。 */
    appendTimelineItems(sessionId: string, items: AgentTimelineItem[]): void {
      if (!sessionId || !items.length) return
      const state = this.ensureSession(sessionId).runtime
      state.timelineItems = [...state.timelineItems, ...items]
    },
    /** 写入归一化的活跃 Run，并更新本地运行标记。 */
    setActiveRun(sessionId: string, run: AgentActiveRunItem | null): void {
      if (!sessionId) return
      const state = this.ensureSession(sessionId).runtime
      const normalizedRun = normalizeActiveRun(run)
      state.activeRun = normalizedRun
      state.stream.runId = run?.run_id ?? state.stream.runId
      state.stream.streaming = Boolean(normalizedRun && ['pending', 'running', 'waiting_external', 'cancelling'].includes(normalizedRun.status))
    },
    /**
     * 更新 paused activeRun 上的待处理 requirement。
     * 契约：requirement 只允许挂在 status === 'paused' 的 activeRun 上；显式 null 可立即隐藏待处理卡片。
     * 写入非 null 前调用方必须先保证 activeRun 已是 paused（例如 HITL 恢复时先 syncActiveRun(pausedRun)），
     * 否则写入会被拒绝并告警，避免状态机外挂载 requirement。
     */
    setPendingRequirement(sessionId: string, requirement: AgentPendingRequirement | null): void {
      if (!sessionId) return
      const state = this.ensureSession(sessionId).runtime
      if (state.activeRun?.status === 'paused') {
        state.activeRun = { ...state.activeRun, pending_requirement: requirement }
        return
      }
      if (requirement) {
        logClientWarning(
          `Ignore setPendingRequirement for session ${sessionId}: activeRun status is ${state.activeRun?.status ?? 'null'}, require paused`,
        )
      }
    },
    /** 更新指定会话的待发送图片附件。 */
    setPendingImageAttachments(sessionId: string, attachments: AgentImageAttachmentItem[]): void {
      if (!sessionId) return
      this.ensureSession(sessionId).runtime.pendingImageAttachments = attachments
    },
    /** 更新指定会话的上下文用量快照。 */
    setContextStatus(sessionId: string, status: AgentContextStatusItem | null): void {
      if (!sessionId) return
      this.ensureSession(sessionId).runtime.contextStatus = status
    },
    /** 记录当前会话最近一次运行错误。 */
    setLastIssue(sessionId: string, issue: { title: string, detail: string } | null): void {
      if (!sessionId) return
      this.ensureSession(sessionId).runtime.lastIssue = issue
    },
    /** 标记本地订阅或乐观发送仍在进行。 */
    setStreaming(sessionId: string, value: boolean): void {
      if (!sessionId) return
      this.ensureSession(sessionId).runtime.stream.streaming = value
    },
    /** 记录当前订阅目标 Run ID。 */
    setCurrentRunId(sessionId: string, runId: string | null): void {
      if (!sessionId) return
      this.ensureSession(sessionId).runtime.stream.runId = runId
    },
    /** 记录正在流式写入的时间线项 ID。 */
    setStreamingTimelineItemId(sessionId: string, itemId: string | null): void {
      if (!sessionId) return
      this.ensureSession(sessionId).runtime.stream.streamingTimelineItemId = itemId
    },
    /** 返回指定 Run 已消费的最大事件序号。 */
    getLastSequence(sessionId: string, runId: string): number {
      return this.getSession(sessionId)?.runtime.stream.lastSequenceByRun[runId] ?? -1
    },
    /** 在首个服务端事件到达前追加用户消息和等待提示。 */
    beginLocalRun(sessionId: string, message: string, attachments: AgentImageAttachmentItem[], runId?: string | null): void {
      if (!sessionId) return
      const state = this.ensureSession(sessionId).runtime
      state.pendingImageAttachments = []
      state.lastIssue = null
      state.stream.runId = runId ?? state.stream.runId
      appendLocalRunTimelineItems(state, sessionId, message, attachments, runId)
      state.stream.streamingTimelineItemId = null
      state.stream.streaming = true
    },
    /** 本地处理 HITL 答复并等待服务端权威事件。 */
    markPendingRequirementResolved(
      sessionId: string,
      requirement: AgentPendingRequirement,
      feedbackSelections: AgentFeedbackSelection[] = [],
    ): void {
      if (!sessionId) return
      const state = this.ensureSession(sessionId).runtime
      this.setPendingRequirement(sessionId, null)
      state.stream.runId = requirement.run_id || state.stream.runId
      markPendingRequirementResolvedInTimeline(state, sessionId, requirement, feedbackSelections)
      state.stream.streaming = true
    },
    /** 更新当前会话的取消请求状态。 */
    setInterrupting(sessionId: string, value: boolean): void {
      if (!sessionId) return
      this.ensureSession(sessionId).ui.interrupting = value
    },
    /** 更新当前会话的图片上传状态。 */
    setImageUploading(sessionId: string, value: boolean): void {
      if (!sessionId) return
      this.ensureSession(sessionId).ui.imageUploading = value
    },
    /** 更新当前会话的 HITL 提交状态。 */
    setHitlActionInFlight(sessionId: string, value: boolean): void {
      if (!sessionId) return
      this.ensureSession(sessionId).ui.hitlActionInFlight = value
    },
    /** 更新当前会话的消息发送状态。 */
    setSendInFlight(sessionId: string, value: boolean): void {
      if (!sessionId) return
      this.ensureSession(sessionId).ui.sendInFlight = value
    },
    /** 清空新一轮 Run 开始前的领域刷新事件。 */
    clearMutationRefreshEvents(sessionId: string): void {
      if (!sessionId) return
      this.ensureSession(sessionId).ui.mutationRefreshEvents = []
    },
    /** 合并同一会话的工具写入刷新事件。 */
    appendMutationRefreshEvents(sessionId: string, events: AgentMutationRefreshEvent[]): void {
      if (!sessionId || !events.length) return
      const state = this.ensureSession(sessionId).ui
      state.mutationRefreshEvents = compactMutationRefreshEvents([...state.mutationRefreshEvents, ...events])
    },
    /** 取出后立即清空队列，保证工具完成与 run 收尾不会重复通知。 */
    drainMutationRefreshEvents(sessionId: string): AgentMutationRefreshEvent[] {
      if (!sessionId) return []
      const state = this.ensureSession(sessionId).ui
      const events = compactMutationRefreshEvents(state.mutationRefreshEvents)
      state.mutationRefreshEvents = []
      return events
    },
  },
})

/** 清理非暂停 run 携带的历史 requirement。 */
function normalizeActiveRun(run: AgentActiveRunItem | null): AgentActiveRunItem | null {
  if (!run || run.status === 'paused' || run.pending_requirement === null) {
    return run
  }
  return { ...run, pending_requirement: null }
}
