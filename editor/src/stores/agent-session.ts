/**
 * 文件功能：集中管理智能体会话运行时状态，承接后端 runtime snapshot 与 run 事件流。
 */
import { defineStore } from 'pinia'

import {
  applyAgentRunEvent,
  applyAgentRuntimeSnapshot,
  buildAgentLocalMessage,
  createAgentSessionRuntimeState,
  type AgentSessionRuntimeState,
} from '@/components/agent/agent-run-state'
import type { AgentActiveRunItem, AgentContextStatusItem, AgentImageAttachmentItem, AgentMessageItem, AgentPendingRequirement, AgentRunEvent, AgentSessionRuntimeSnapshot } from '@/types/api'
import type { AgentMutationRefreshEvent, ToolCallDetail } from '@/components/agent/agent-conversation-panel'

export const useAgentSessionStore = defineStore('agent-session', {
  state: () => ({
    sessions: {} as Record<string, AgentSessionRuntimeState>,
    conversationMessagesBySession: {} as Record<string, AgentMessageItem[]>,
    toolCallDetailsBySession: {} as Record<string, ToolCallDetail[]>,
    pendingRequirementBySession: {} as Record<string, AgentPendingRequirement | null>,
    pendingImageAttachmentsBySession: {} as Record<string, AgentImageAttachmentItem[]>,
    activeRunBySession: {} as Record<string, AgentActiveRunItem | null>,
    streamingBySession: {} as Record<string, boolean>,
    currentRunIdBySession: {} as Record<string, string | null>,
    streamingAssistantMessageIdBySession: {} as Record<string, string | null>,
    assistantSegmentClosedByToolBySession: {} as Record<string, boolean>,
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
        messages: snapshot.messages,
        activeRun: snapshot.active_run,
        lastRun: snapshot.last_run,
        pendingRequirement: snapshot.pending_requirement,
        pendingImageAttachments: snapshot.pending_attachments,
        contextStatus: snapshot.context_status,
        eventIndex: snapshot.event_index,
        toolDetails: snapshot.tool_details,
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
    setMessages(sessionId: string, messages: AgentMessageItem[]): void {
      if (!sessionId) return
      this.ensureSession(sessionId).messages = messages
      this.syncFlatMaps(sessionId)
    },
    setToolCallDetails(sessionId: string, details: ToolCallDetail[]): void {
      if (!sessionId) return
      this.ensureSession(sessionId).toolCallDetails = details
      this.syncFlatMaps(sessionId)
    },
    setActiveRun(sessionId: string, run: AgentActiveRunItem | null): void {
      if (!sessionId) return
      const state = this.ensureSession(sessionId)
      state.activeRun = run
      state.stream.runId = run?.run_id ?? state.stream.runId
      state.stream.streaming = Boolean(run && ['pending', 'running', 'cancelling'].includes(run.status))
      if (run?.status === 'paused') {
        state.pendingRequirement = run.pending_requirement
      } else if (run?.status !== 'pending' && run?.status !== 'running') {
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
    setStreamingAssistantMessageId(sessionId: string, messageId: string | null): void {
      if (!sessionId) return
      this.ensureSession(sessionId).stream.streamingAssistantMessageId = messageId
      this.syncFlatMaps(sessionId)
    },
    setAssistantSegmentClosedByTool(sessionId: string, value: boolean): void {
      if (!sessionId) return
      this.ensureSession(sessionId).stream.assistantSegmentClosedByTool = value
      this.syncFlatMaps(sessionId)
    },
    getLastSequence(sessionId: string, runId: string): number {
      if (!sessionId) return -1
      return this.ensureSession(sessionId).stream.lastSequenceByRun[runId] ?? -1
    },
    beginLocalRun(sessionId: string, message: string, attachments: AgentImageAttachmentItem[]): void {
      if (!sessionId) return
      const state = this.ensureSession(sessionId)
      state.pendingImageAttachments = []
      state.pendingRequirement = null
      state.lastIssue = null
      state.messages = [
        ...state.messages,
        buildAgentLocalMessage('user', message || '（已发送图片）', attachments),
        buildAgentLocalMessage('assistant', ''),
      ]
      state.stream.streamingAssistantMessageId = state.messages[state.messages.length - 1]?.id ?? null
      state.stream.assistantSegmentClosedByTool = false
      state.stream.streaming = true
      this.syncFlatMaps(sessionId)
    },
    syncFlatMaps(sessionId: string): void {
      const state = this.ensureSession(sessionId)
      this.conversationMessagesBySession[sessionId] = state.messages
      this.toolCallDetailsBySession[sessionId] = state.toolCallDetails
      this.pendingRequirementBySession[sessionId] = state.pendingRequirement
      this.pendingImageAttachmentsBySession[sessionId] = state.pendingImageAttachments
      this.activeRunBySession[sessionId] = state.activeRun
      this.streamingBySession[sessionId] = state.stream.streaming
      this.currentRunIdBySession[sessionId] = state.stream.runId
      this.streamingAssistantMessageIdBySession[sessionId] = state.stream.streamingAssistantMessageId
      this.assistantSegmentClosedByToolBySession[sessionId] = state.stream.assistantSegmentClosedByTool
      this.lastRunIssueBySession[sessionId] = state.lastIssue
      this.contextStatusBySession[sessionId] = state.contextStatus as AgentContextStatusItem | null
    },
    hydrateSessionFromFlatMaps(sessionId: string): void {
      const state = this.ensureSession(sessionId)
      if (hasSessionValue(this.conversationMessagesBySession, sessionId)) {
        state.messages = this.conversationMessagesBySession[sessionId]
      }
      if (hasSessionValue(this.toolCallDetailsBySession, sessionId)) {
        state.toolCallDetails = this.toolCallDetailsBySession[sessionId]
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
      if (hasSessionValue(this.streamingAssistantMessageIdBySession, sessionId)) {
        state.stream.streamingAssistantMessageId = this.streamingAssistantMessageIdBySession[sessionId]
      }
      if (hasSessionValue(this.assistantSegmentClosedByToolBySession, sessionId)) {
        state.stream.assistantSegmentClosedByTool = this.assistantSegmentClosedByToolBySession[sessionId]
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
