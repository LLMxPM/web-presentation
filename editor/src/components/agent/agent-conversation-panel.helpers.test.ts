/**
 * 文件功能：验证内容助手消息展示辅助逻辑，确保历史工具调用在刷新后归位稳定。
 */
import { describe, expect, it } from 'vitest'

import {
  buildRunIssueState,
  buildConversationDisplayItems,
  extractHistoryToolCallDetails,
  mergeToolCallDetails,
  type ToolCallDetail,
} from '@/components/agent/agent-conversation-panel'
import type { AgentMessageItem } from '@/types/api'

/**
 * 构造最小会话消息，便于覆盖不同历史顺序。
 */
function message(
  id: string,
  role: AgentMessageItem['role'],
  content: string,
  overrides: Partial<AgentMessageItem> = {},
): AgentMessageItem {
  return {
    id,
    role,
    content,
    created_at: null,
    tool_name: null,
    tool_call_id: null,
    tool_args: null,
    tool_call_error: null,
    ...overrides,
  }
}

describe('agent-conversation-panel helpers', () => {
  it('assistant.tool_calls 后续 tool 结果应挂在调用发生的助手消息上', () => {
    const messages = [
      message('user-1', 'user', '检查资源', { run_id: 'run-1' }),
      message('assistant-call', 'assistant', '我先读取资源。', {
        run_id: 'run-1',
        tool_calls: [
          {
            id: 'tool-assets',
            type: 'function',
            function: {
              name: 'list_workspace_render_assets',
              arguments: '{"workspace_id":11,"limit":20}',
            },
          },
        ],
      }),
      message('tool-assets-result', 'tool', '{"total":2}', {
        run_id: 'run-1',
        tool_name: 'list_workspace_render_assets',
        tool_call_id: 'tool-assets',
        tool_args: { workspace_id: 11, limit: 20 },
      }),
      message('assistant-final', 'assistant', '资源检查完成。', { run_id: 'run-1' }),
    ]

    const items = buildConversationDisplayItems(messages, extractHistoryToolCallDetails(messages))
    const callAssistant = items.find(item => item.message.id === 'assistant-call')
    const finalAssistant = items.find(item => item.message.id === 'assistant-final')

    expect(callAssistant?.embeddedTools).toHaveLength(1)
    expect(callAssistant?.embeddedTools[0]).toEqual(expect.objectContaining({
      id: 'tool-assets',
      toolCallId: 'tool-assets',
      toolName: 'list_workspace_render_assets',
      assistantMessageId: 'assistant-call',
      inputPayload: { workspace_id: 11, limit: 20 },
      outputPayload: { total: 2 },
      status: 'completed',
    }))
    expect(finalAssistant?.embeddedTools).toHaveLength(0)
  })

  it('历史工具消息位于 assistant 前后时应挂到同一轮助手消息', () => {
    const beforeAssistantMessages = [
      message('user-1', 'user', '检查组件'),
      message('tool-1', 'tool', '{"success":true}', {
        tool_name: 'preview_component_edits',
        tool_call_id: 'tool-call-before',
      }),
      message('assistant-1', 'assistant', '组件检查完成。'),
    ]
    const afterAssistantMessages = [
      message('user-1', 'user', '检查组件'),
      message('assistant-1', 'assistant', '组件检查完成。'),
      message('tool-1', 'tool', '{"success":true}', {
        tool_name: 'preview_component_edits',
        tool_call_id: 'tool-call-after',
      }),
    ]

    const beforeItems = buildConversationDisplayItems(
      beforeAssistantMessages,
      extractHistoryToolCallDetails(beforeAssistantMessages),
    )
    const afterItems = buildConversationDisplayItems(
      afterAssistantMessages,
      extractHistoryToolCallDetails(afterAssistantMessages),
    )

    const beforeAssistant = beforeItems.find(item => item.message.id === 'assistant-1')
    const afterAssistant = afterItems.find(item => item.message.id === 'assistant-1')
    expect(beforeAssistant?.embeddedTools.map(tool => tool.toolName)).toEqual(['preview_component_edits'])
    expect(afterAssistant?.embeddedTools.map(tool => tool.toolName)).toEqual(['preview_component_edits'])
  })

  it('历史工具消息缺少 tool_call_id 时仍应保留输入输出并挂回助手消息', () => {
    const messages = [
      message('user-1', 'user', '检查资源'),
      message('assistant-1', 'assistant', '资源检查完成。'),
      message('tool-without-call-id', 'tool', '{"total":2}', {
        tool_name: 'list_workspace_render_assets',
        tool_call_id: null,
        tool_args: { workspace_id: 11 },
      }),
    ]

    const items = buildConversationDisplayItems(messages, extractHistoryToolCallDetails(messages))
    const assistantItem = items.find(item => item.message.id === 'assistant-1')

    expect(assistantItem?.embeddedTools).toHaveLength(1)
    expect(assistantItem?.embeddedTools[0]).toEqual(expect.objectContaining({
      id: 'history-tool-without-call-id',
      toolCallId: null,
      toolName: 'list_workspace_render_assets',
      inputPayload: { workspace_id: 11 },
      outputPayload: { total: 2 },
    }))
  })

  it('实时工具详情缺少 assistantMessageId 时应按 run_id 挂到同 run 最后一条助手消息', () => {
    const messages = [
      message('user-1', 'user', '检查资源', { run_id: 'run-1' }),
      message('assistant-1', 'assistant', '资源检查完成。', { run_id: 'run-1' }),
      message('assistant-2', 'assistant', '另一个运行的回复。', { run_id: 'run-2' }),
    ]
    const tools: ToolCallDetail[] = [{
      id: 'tool-event-1',
      runId: 'run-1',
      toolCallId: null,
      toolName: 'list_workspace_render_assets',
      memberAgentId: null,
      memberAgentName: null,
      memberRunId: null,
      status: 'completed',
      assistantMessageId: null,
      inputPayload: null,
      outputPayload: { total: 1 },
      message: '',
      source: 'event',
      createdAt: null,
    }]

    const items = buildConversationDisplayItems(messages, tools)
    const firstAssistant = items.find(item => item.message.id === 'assistant-1')
    const secondAssistant = items.find(item => item.message.id === 'assistant-2')

    expect(firstAssistant?.embeddedTools.map(tool => tool.id)).toEqual(['tool-event-1'])
    expect(secondAssistant?.embeddedTools).toHaveLength(0)
  })

  it('历史工具详情缓存不应覆盖 Agno 消息历史中的工具锚点', () => {
    const messages = [
      message('user-1', 'user', '检查资源', { run_id: 'run-1' }),
      message('assistant-call', 'assistant', '我先读取资源。', {
        run_id: 'run-1',
        tool_calls: [
          {
            id: 'tool-assets',
            type: 'function',
            function: {
              name: 'list_workspace_render_assets',
              arguments: '{"workspace_id":11}',
            },
          },
        ],
      }),
      message('tool-assets-result', 'tool', '{"total":2}', {
        run_id: 'run-1',
        tool_name: 'list_workspace_render_assets',
        tool_call_id: 'tool-assets',
        tool_args: { workspace_id: 11 },
      }),
      message('assistant-final', 'assistant', '资源检查完成。', { run_id: 'run-1' }),
    ]
    const historyTools = extractHistoryToolCallDetails(messages)
    const cachedTools: ToolCallDetail[] = [{
      id: 'tool-assets-cache',
      runId: 'run-1',
      toolCallId: 'tool-assets',
      toolName: 'list_workspace_render_assets',
      memberAgentId: null,
      memberAgentName: null,
      memberRunId: null,
      status: 'completed',
      assistantMessageId: 'assistant-final',
      inputPayload: { workspace_id: 11 },
      outputPayload: { total: 2 },
      message: '{"total":2}',
      source: 'history',
      createdAt: null,
    }]

    const items = buildConversationDisplayItems(messages, mergeToolCallDetails(historyTools, cachedTools))
    const callAssistant = items.find(item => item.message.id === 'assistant-call')
    const finalAssistant = items.find(item => item.message.id === 'assistant-final')

    expect(callAssistant?.embeddedTools.map(tool => tool.assistantMessageId)).toEqual(['assistant-call'])
    expect(finalAssistant?.embeddedTools).toHaveLength(0)
  })

  it('未匹配到 Agno 消息锚点的历史工具缓存不参与回放定位', () => {
    const messages = [
      message('user-1', 'user', '检查资源', { run_id: 'run-1' }),
      message('assistant-1', 'assistant', '资源检查完成。', { run_id: 'run-1' }),
    ]
    const cachedTools: ToolCallDetail[] = [{
      id: 'tool-history-cache',
      runId: 'run-1',
      toolCallId: 'tool-cache',
      toolName: 'list_workspace_render_assets',
      memberAgentId: null,
      memberAgentName: null,
      memberRunId: null,
      status: 'completed',
      assistantMessageId: null,
      inputPayload: { workspace_id: 11 },
      outputPayload: { total: 1 },
      message: '{"total":1}',
      source: 'history',
      createdAt: null,
    }]

    const items = buildConversationDisplayItems(messages, mergeToolCallDetails([], cachedTools))
    const assistantItem = items.find(item => item.message.id === 'assistant-1')

    expect(assistantItem?.embeddedTools).toHaveLength(0)
  })

  it('运行失败标题应使用当前智能体名称', () => {
    expect(buildRunIssueState('模型协议错误', '组件助手').title).toBe('组件助手执行失败')
  })
})
