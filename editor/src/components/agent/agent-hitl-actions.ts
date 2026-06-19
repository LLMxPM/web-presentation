/**
 * 文件功能：集中封装智能体 HITL 暂停态的确认、回答、取消与强制释放动作。
 */
import {
  AgentStreamInterruptedError,
  cancelAgentSessionActiveRun,
  continueAgentSessionActiveRun,
} from '@/api/ai'
import { getErrorMessage } from '@/api/http'
import type {
  AgentActiveRunItem,
  AgentFeedbackSelection,
  AgentPendingRequirement,
  AgentRunEvent,
  AgentScopeContext,
} from '@/types/api'
import { logClientWarning } from '@/utils/client-logger'
import { createConfirm, Message } from '@/utils/message'

interface HitlActionContext {
  getActiveSessionId: () => string
  getPendingRequirement: () => AgentPendingRequirement | null
  getActiveRun: () => AgentActiveRunItem | null
  getScope: () => AgentScopeContext
  getAgentId: () => string
  isDisposed: () => boolean
  setHitlActionInFlight: (sessionId: string, value: boolean) => void
  setSessionStreaming: (sessionId: string, value: boolean) => void
  syncActiveRun: (sessionId: string, run: AgentActiveRunItem | null) => void
  setPendingRequirementForSession: (sessionId: string, requirement: AgentPendingRequirement | null) => void
  createStreamAbortController: (runId: string) => AbortController
  clearStreamAbortController: (runId: string, controller: AbortController) => void
  handleRunEvent: (event: AgentRunEvent, fallbackSessionId: string) => void
  finalizeRun: (sessionId: string, options?: { preserveLocalCancelled?: boolean }) => Promise<void>
  refreshAfterStreamInterrupted: (sessionId: string) => void | Promise<void>
}

/**
 * 生成 HITL 交互动作；调用方负责提供当前会话状态读写和流式事件回调。
 */
export function useAgentHitlActions(context: HitlActionContext) {
  /**
   * 继续当前暂停中的 run。
   */
  async function handleContinueRun(decision: 'confirm' | 'reject') {
    await continuePausedRun({
      decision,
      feedbackSelections: [],
    })
  }

  /**
   * 提交结构化提问的全部答案，并一次性恢复当前 paused run。
   */
  async function handleSubmitFeedbackRun(selections: AgentFeedbackSelection[]) {
    await continuePausedRun({
      decision: null,
      feedbackSelections: selections,
    })
  }

  /**
   * 忽略结构化提问时取消当前 paused run，不向模型返回空答案。
   */
  async function handleCancelPausedRun() {
    const sessionId = context.getActiveSessionId()
    const requirement = context.getPendingRequirement()
    const pausedRun = context.getActiveRun()
    if (!sessionId || !requirement || pausedRun?.status !== 'paused') {
      return
    }

    context.setHitlActionInFlight(sessionId, true)
    try {
      context.setPendingRequirementForSession(sessionId, null)
      const response = await cancelAgentSessionActiveRun(sessionId, context.getScope(), {
        agent_id: context.getAgentId(),
      })
      Message.info('已停止。')
      await context.finalizeRun(response.session_id, { preserveLocalCancelled: true })
    } catch (error) {
      await recoverHitlStateAfterFailedAction(sessionId, pausedRun, requirement)
      Message.error(getErrorMessage(error, '忽略失败，请稍后再试。'))
    } finally {
      context.setHitlActionInFlight(sessionId, false)
    }
  }

  /**
   * 强制释放卡住的 HITL 暂停态，只清理当前待确认/待回答动作，不提交任何答案。
   */
  async function handleForceReleaseHitl() {
    const sessionId = context.getActiveSessionId()
    const requirement = context.getPendingRequirement()
    const pausedRun = context.getActiveRun()
    if (!sessionId || !requirement || pausedRun?.status !== 'paused') {
      return
    }

    const confirmed = await createConfirm(
      '强制释放只会结束当前待确认/待回答动作，不会执行工具，也不会提交回答。确定继续吗？',
      '强制释放 HITL',
    )
    if (!confirmed) {
      return
    }

    context.setHitlActionInFlight(sessionId, true)
    try {
      const response = await cancelAgentSessionActiveRun(sessionId, context.getScope(), {
        agent_id: context.getAgentId(),
        force: true,
        tool_call_id: resolveRequirementToolCallId(requirement),
      })
      context.setPendingRequirementForSession(sessionId, null)
      context.syncActiveRun(sessionId, {
        ...pausedRun,
        status: 'cancelled',
        pending_requirement: null,
        updated_at: new Date().toISOString(),
      })
      Message.info('已释放当前待处理动作。')
      await context.finalizeRun(response.session_id, { preserveLocalCancelled: true })
    } catch (error) {
      await recoverHitlStateAfterFailedAction(sessionId, pausedRun, requirement)
      Message.error(getErrorMessage(error, '强制释放失败，请稍后再试。'))
    } finally {
      context.setHitlActionInFlight(sessionId, false)
    }
  }

  /**
   * 按确认或结构化回答继续 paused run，并统一处理乐观状态、流中断和失败回滚。
   */
  async function continuePausedRun(payload: {
    decision: 'confirm' | 'reject' | null
    feedbackSelections: AgentFeedbackSelection[]
  }) {
    const sessionId = context.getActiveSessionId()
    const requirement = context.getPendingRequirement()
    const pausedRun = context.getActiveRun()
    if (!sessionId || !requirement || pausedRun?.status !== 'paused') {
      return
    }

    context.setHitlActionInFlight(sessionId, true)
    context.setPendingRequirementForSession(sessionId, null)
    context.setSessionStreaming(sessionId, true)
    context.syncActiveRun(sessionId, { ...pausedRun, status: 'running', pending_requirement: null })

    const runId = requirement.run_id || pausedRun.run_id || ''
    let streamAbortController: AbortController | null = null
    try {
      streamAbortController = context.createStreamAbortController(runId)
      await continueAgentSessionActiveRun(sessionId, context.getScope(), {
        agent_id: context.getAgentId(),
        decision: payload.decision,
        tool_execution: requirement.tool_execution,
        feedback_selections: payload.feedbackSelections,
      }, {
        onEvent: event => context.handleRunEvent(event, sessionId),
        signal: streamAbortController.signal,
      })
      await context.finalizeRun(sessionId)
    } catch (error) {
      if (error instanceof AgentStreamInterruptedError) {
        if (!context.isDisposed()) {
          void context.refreshAfterStreamInterrupted(sessionId)
        }
        return
      }
      await recoverHitlStateAfterFailedAction(sessionId, pausedRun, requirement)
      Message.error(getErrorMessage(error, '继续智能体执行失败。'))
    } finally {
      if (streamAbortController) {
        context.clearStreamAbortController(runId, streamAbortController)
      }
      context.setHitlActionInFlight(sessionId, false)
      context.setSessionStreaming(sessionId, false)
    }
  }

  /**
   * HITL 操作失败后恢复本地暂停态，并尽快用后端快照覆盖到权威状态。
   */
  async function recoverHitlStateAfterFailedAction(
    sessionId: string,
    pausedRun: AgentActiveRunItem,
    requirement: AgentPendingRequirement,
  ) {
    context.syncActiveRun(sessionId, pausedRun)
    context.setPendingRequirementForSession(sessionId, requirement)
    try {
      await context.finalizeRun(sessionId)
    } catch (error) {
      logClientWarning('Failed to refresh after HITL action failure', error)
    }
  }

  return {
    handleContinueRun,
    handleSubmitFeedbackRun,
    handleCancelPausedRun,
    handleForceReleaseHitl,
  }
}

/**
 * 从待处理动作中读取稳定 tool_call_id，供强制释放时做后端 stale 校验。
 */
function resolveRequirementToolCallId(requirement: AgentPendingRequirement) {
  const toolCallId = requirement.tool_execution?.tool_call_id
  return typeof toolCallId === 'string' && toolCallId ? toolCallId : null
}
