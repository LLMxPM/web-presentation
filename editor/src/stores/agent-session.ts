/**
 * 文件功能：集中管理智能体会话运行时状态，承接后端 runtime timeline 与 run 事件流。
 */
import { defineStore } from 'pinia'

import {
  applyAgentRunEvent,
  applyAgentRuntimeSnapshot,
  createAgentSessionRuntimeState,
  type AgentSessionRuntimeState,
} from '@/components/agent/agent-run-state'
import {
  appendLocalRunTimelineItems,
  markPendingRequirementResolvedInTimeline,
} from '@/stores/agent-session-timeline'
import type {
  AgentActiveRunItem,
  AgentFeedbackSelection,
  AgentContextStatusItem,
  AgentImageAttachmentItem,
  AgentMemberRunItem,
  AgentPendingRequirement,
  AgentRunEvent,
  AgentSessionRuntimeSnapshot,
  AgentTimelineItem,
} from '@/types/api'
import type { AgentMutationRefreshEvent } from '@/components/agent/agent-conversation-panel'

export const useAgentSessionStore = defineStore('agent-session', {
  state: () => ({
    sessions: {} as Record<string, AgentSessionRuntimeState>,
    timelineItemsBySession: {} as Record<string, AgentTimelineItem[]>,
    memberRunsBySession: {} as Record<string, AgentMemberRunItem[]>,
    pendingRequirementBySession: {} as Record<string, AgentPendingRequirement | null>,
    pendingImageAttachmentsBySession: {} as Record<string, AgentImageAttachmentItem[]>,
    activeRunBySession: {} as Record<string, AgentActiveRunItem | null>,
    streamingBySession: {} as Record<string, boolean>,
    currentRunIdBySession: {} as Record<string, string | null>,
    streamingTimelineItemIdBySession: {} as Record<string, string | null>,
    lastRunIssueBySession: {} as Record<string, { title: string, detail: string } | null>,
    contextStatusBySession: {} as Record<string, AgentContextStatusItem | null>,
    mutationRefreshEventsBySession: {} as Record<string, AgentMutationRefreshEvent[]>,
    interruptingBySession: {} as Record<string, boolean>,
    imageUploadingBySession: {} as Record<string, boolean>,
  }),
  actions: {
    ensureSession(sessionId: string): AgentSessionRuntimeState {
      if (!this.sessions[sessionId]) {
        this.sessions[sessionId] = createAgentSessionRuntimeState()
      }
      return this.sessions[sessionId]
    },
    applyRuntimeSnapshot(sessionId: string, snapshot: AgentSessionRuntimeSnapshot): void {
      if (!sessionId) return
      applyAgentRuntimeSnapshot(this.ensureSession(sessionId), {
        timelineItems: snapshot.timeline_items,
        memberRuns: snapshot.member_runs ?? [],
        activeRun: snapshot.active_run,
        lastRun: snapshot.last_run,
        pendingRequirement: snapshot.pending_requirement,
        pendingImageAttachments: snapshot.pending_attachments,
        contextStatus: snapshot.context_status,
        eventIndex: snapshot.event_index,
      })
      this.syncFlatMaps(sessionId)
    },
    applyRunEvent(sessionId: string, event: AgentRunEvent, options: { agentId: string, agentDisplayName: string }) {
      if (!sessionId) return { applied: false, terminal: false }
      this.hydrateSessionFromFlatMaps(sessionId)
      const result = applyAgentRunEvent(this.ensureSession(sessionId), event, options)
      this.syncFlatMaps(sessionId)
      return result
    },
    setTimelineItems(sessionId: string, items: AgentTimelineItem[]): void {
      if (!sessionId) return
      this.ensureSession(sessionId).timelineItems = items
      this.syncFlatMaps(sessionId)
    },
    appendTimelineItems(sessionId: string, items: AgentTimelineItem[]): void {
      if (!sessionId || !items.length) return
      const state = this.ensureSession(sessionId)
      state.timelineItems = [...state.timelineItems, ...items]
      this.syncFlatMaps(sessionId)
    },
    setActiveRun(sessionId: string, run: AgentActiveRunItem | null): void {
      if (!sessionId) return
      const state = this.ensureSession(sessionId)
      const normalizedRun = normalizeActiveRun(run)
      state.activeRun = normalizedRun
      state.stream.runId = run?.run_id ?? state.stream.runId
      state.stream.streaming = Boolean(normalizedRun && ['pending', 'running', 'waiting_external', 'cancelling'].includes(normalizedRun.status))
      if (normalizedRun?.status === 'paused') {
        state.pendingRequirement = normalizedRun.pending_requirement
      } else {
        state.pendingRequirement = null
      }
      this.syncFlatMaps(sessionId)
    },
    setPendingRequirement(sessionId: string, requirement: AgentPendingRequirement | null): void {
      if (!sessionId) return
      this.ensureSession(sessionId).pendingRequirement = requirement
      this.syncFlatMaps(sessionId)
    },
    setPendingImageAttachments(sessionId: string, attachments: AgentImageAttachmentItem[]): void {
      if (!sessionId) return
      this.ensureSession(sessionId).pendingImageAttachments = attachments
      this.syncFlatMaps(sessionId)
    },
    setContextStatus(sessionId: string, status: AgentContextStatusItem | null): void {
      if (!sessionId) return
      this.ensureSession(sessionId).contextStatus = status
      this.syncFlatMaps(sessionId)
    },
    setLastIssue(sessionId: string, issue: { title: string, detail: string } | null): void {
      if (!sessionId) return
      this.ensureSession(sessionId).lastIssue = issue
      this.syncFlatMaps(sessionId)
    },
    setStreaming(sessionId: string, value: boolean): void {
      if (!sessionId) return
      this.ensureSession(sessionId).stream.streaming = value
      this.syncFlatMaps(sessionId)
    },
    setCurrentRunId(sessionId: string, runId: string | null): void {
      if (!sessionId) return
      this.ensureSession(sessionId).stream.runId = runId
      this.syncFlatMaps(sessionId)
    },
    setStreamingTimelineItemId(sessionId: string, itemId: string | null): void {
      if (!sessionId) return
      this.ensureSession(sessionId).stream.streamingTimelineItemId = itemId
      this.syncFlatMaps(sessionId)
    },
    getLastSequence(sessionId: string, runId: string): number {
      if (!sessionId) return -1
      return this.ensureSession(sessionId).stream.lastSequenceByRun[runId] ?? -1
    },
    beginLocalRun(sessionId: string, message: string, attachments: AgentImageAttachmentItem[], runId?: string | null): void {
      if (!sessionId) return
      const state = this.ensureSession(sessionId)
      state.pendingImageAttachments = []
      state.pendingRequirement = null
      state.lastIssue = null
      state.stream.runId = runId ?? state.stream.runId
      appendLocalRunTimelineItems(state, sessionId, message, attachments, runId)
      state.stream.streamingTimelineItemId = null
      state.stream.streaming = true
      this.syncFlatMaps(sessionId)
    },
    markPendingRequirementResolved(
      sessionId: string,
      requirement: AgentPendingRequirement,
      feedbackSelections: AgentFeedbackSelection[] = [],
    ): void {
      if (!sessionId) return
      const state = this.ensureSession(sessionId)
      state.pendingRequirement = null
      state.stream.runId = requirement.run_id || state.stream.runId
      markPendingRequirementResolvedInTimeline(state, sessionId, requirement, feedbackSelections)
      state.stream.streaming = true
      this.syncFlatMaps(sessionId)
    },
    syncFlatMaps(sessionId: string): void {
      const state = this.ensureSession(sessionId)
      this.timelineItemsBySession[sessionId] = state.timelineItems
      this.memberRunsBySession[sessionId] = state.memberRuns
      this.pendingRequirementBySession[sessionId] = state.pendingRequirement
      this.pendingImageAttachmentsBySession[sessionId] = state.pendingImageAttachments
      this.activeRunBySession[sessionId] = state.activeRun
      this.streamingBySession[sessionId] = state.stream.streaming
      this.currentRunIdBySession[sessionId] = state.stream.runId
      this.streamingTimelineItemIdBySession[sessionId] = state.stream.streamingTimelineItemId
      this.lastRunIssueBySession[sessionId] = state.lastIssue
      this.contextStatusBySession[sessionId] = state.contextStatus as AgentContextStatusItem | null
    },
    hydrateSessionFromFlatMaps(sessionId: string): void {
      const state = this.ensureSession(sessionId)
      if (hasSessionValue(this.timelineItemsBySession, sessionId)) {
        state.timelineItems = this.timelineItemsBySession[sessionId]
      }
      if (hasSessionValue(this.memberRunsBySession, sessionId)) {
        state.memberRuns = this.memberRunsBySession[sessionId]
      }
      if (hasSessionValue(this.pendingRequirementBySession, sessionId)) {
        state.pendingRequirement = this.pendingRequirementBySession[sessionId]
      }
      if (hasSessionValue(this.pendingImageAttachmentsBySession, sessionId)) {
        state.pendingImageAttachments = this.pendingImageAttachmentsBySession[sessionId]
      }
      if (hasSessionValue(this.activeRunBySession, sessionId)) {
        state.activeRun = this.activeRunBySession[sessionId]
      }
      if (hasSessionValue(this.streamingBySession, sessionId)) {
        state.stream.streaming = this.streamingBySession[sessionId]
      }
      if (hasSessionValue(this.currentRunIdBySession, sessionId)) {
        state.stream.runId = this.currentRunIdBySession[sessionId]
      }
      if (hasSessionValue(this.streamingTimelineItemIdBySession, sessionId)) {
        state.stream.streamingTimelineItemId = this.streamingTimelineItemIdBySession[sessionId]
      }
      if (hasSessionValue(this.lastRunIssueBySession, sessionId)) {
        state.lastIssue = this.lastRunIssueBySession[sessionId]
      }
      if (hasSessionValue(this.contextStatusBySession, sessionId)) {
        state.contextStatus = this.contextStatusBySession[sessionId]
      }
    },
  },
})

/**
 * 判断扁平会话缓存中是否存在该 key；显式 null 也必须能清空嵌套状态。
 */
function hasSessionValue<T>(source: Record<string, T>, sessionId: string): boolean {
  return Object.prototype.hasOwnProperty.call(source, sessionId)
}

/**
 * 归一化 active run，确保非 paused 状态不会携带旧 HITL requirement。
 */
function normalizeActiveRun(run: AgentActiveRunItem | null): AgentActiveRunItem | null {
  if (!run || run.status === 'paused' || run.pending_requirement === null) {
    return run
  }
  return { ...run, pending_requirement: null }
}
