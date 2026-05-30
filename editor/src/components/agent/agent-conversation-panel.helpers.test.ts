/**
 * 文件功能：验证内容助手 run-first 时间线展示辅助逻辑，确保刷新后工具调用独立回放。
 */
import { describe, expect, it } from 'vitest'

import {
  buildRunIssueState,
  buildTimelineDisplayItems,
  extractTimelineToolDetails,
} from '@/components/agent/agent-conversation-panel'
import type { AgentPendingRequirement, AgentTimelineItem } from '@/types/api'

/**
 * 构造最小时间线项，便于覆盖 run-first 展示顺序。
 */
function timelineItem(overrides: Partial<AgentTimelineItem>): AgentTimelineItem {
  return {
    id: overrides.id ?? `item-${overrides.order_index ?? 0}`,
    session_id: 'session-1',
    run_id: 'run-1',
    kind: 'message',
    role: 'assistant',
    event_index: null,
    order_index: 0,
    content: null,
    status: null,
    tool: null,
    source: 'event',
    created_at: null,
    ...overrides,
  }
}

describe('agent-conversation-panel timeline helpers', () => {
  it('应按 order_index 渲染 user、reasoning、assistant、tool 与状态项', () => {
    const items = buildTimelineDisplayItems([
      timelineItem({ id: 'tool-1', kind: 'tool', role: null, order_index: 3, status: 'completed', tool: {
        tool_call_id: 'call-1',
        tool_name: 'list_workspace_render_assets',
        status: 'completed',
        input_payload: { workspace_id: 11 },
        output_payload: { total: 2 },
        message: '',
      } }),
      timelineItem({ id: 'user-1', kind: 'message', role: 'user', order_index: 0, content: '检查资源' }),
      timelineItem({ id: 'assistant-1', kind: 'message', role: 'assistant', order_index: 2, content: '资源检查完成。' }),
      timelineItem({ id: 'reasoning-1', kind: 'reasoning', role: null, order_index: 1, content: '先读取资源。' }),
      timelineItem({ id: 'status-1', kind: 'run_status', role: null, order_index: 4, status: 'completed', content: '运行已完成。' }),
    ])

    expect(items.map(item => item.kind)).toEqual(['message', 'reasoning', 'message', 'tool_group', 'run_status'])
    expect(items[0].kind === 'message' ? items[0].message.role : '').toBe('user')
    expect(items[3].kind === 'tool_group' ? items[3].tools[0].toolName : '').toBe('list_workspace_render_assets')
  })

  it('连续工具调用应折叠为独立工具组，不依赖 assistant 消息', () => {
    const items = buildTimelineDisplayItems([
      timelineItem({ id: 'user-1', kind: 'message', role: 'user', order_index: 0, content: '检查资源' }),
      timelineItem({ id: 'tool-1', kind: 'tool', role: null, order_index: 1, status: 'running', tool: {
        tool_call_id: null,
        tool_name: 'list_workspace_render_assets',
        status: 'running',
        input_payload: { workspace_id: 11 },
        output_payload: null,
        message: '',
      } }),
      timelineItem({ id: 'tool-2', kind: 'tool', role: null, order_index: 2, status: 'completed', tool: {
        tool_call_id: null,
        tool_name: 'read_workspace_render_asset',
        status: 'completed',
        input_payload: { name: 'hero.png' },
        output_payload: { name: 'hero.png' },
        message: '',
      } }),
    ])

    const toolGroup = items.find(item => item.kind === 'tool_group')
    expect(toolGroup?.kind).toBe('tool_group')
    expect(toolGroup?.kind === 'tool_group' ? toolGroup.tools.map(tool => tool.toolName) : []).toEqual([
      'list_workspace_render_assets',
      'read_workspace_render_asset',
    ])
  })

  it('ask_user 工具和 requirement 应合并为等待回复卡片', () => {
    const pendingRequirement: AgentPendingRequirement = {
      id: 'req-ask-1',
      kind: 'user_feedback',
      run_id: 'run-1',
      session_id: 'session-1',
      tool_name: 'ask_user',
      tool_execution: { tool_name: 'ask_user', tool_call_id: 'tool-ask-1' },
      suggested_patch: null,
      user_feedback_schema: [
        {
          question: '是否继续整理资源？',
          header: '继续',
          multi_select: false,
          selected_options: null,
          options: [
            { label: '继续', description: '继续整理资源。' },
            { label: '停止', description: '停止当前任务。' },
          ],
        },
      ],
      note: null,
    }
    const items = buildTimelineDisplayItems([
      timelineItem({ id: 'tool-ask', kind: 'tool', role: null, order_index: 1, status: 'running', tool: {
        tool_call_id: 'tool-ask-1',
        tool_name: 'ask_user',
        status: 'running',
        input_payload: { questions: pendingRequirement.user_feedback_schema },
        output_payload: null,
        message: '',
      } }),
      timelineItem({ id: 'requirement-ask', kind: 'requirement', role: null, order_index: 2, status: 'pending', content: '是否继续整理资源？' }),
    ], { pendingRequirement })

    expect(items.map(item => item.kind)).toEqual(['feedback_request'])
    const feedbackItem = items[0]
    expect(feedbackItem.kind).toBe('feedback_request')
    expect(feedbackItem.kind === 'feedback_request' ? feedbackItem.title : '').toBe('是否继续整理资源？')
    expect(feedbackItem.kind === 'feedback_request' ? feedbackItem.tool?.toolName : '').toBe('ask_user')
  })

  it('已回答 ask_user 应显示完成态和答案摘要', () => {
    const items = buildTimelineDisplayItems([
      timelineItem({ id: 'tool-ask', kind: 'tool', role: null, order_index: 1, status: 'completed', tool: {
        tool_call_id: 'tool-ask-1',
        tool_name: 'ask_user',
        status: 'completed',
        input_payload: {
          questions: [
            {
              question: '请为这个甘特图组件指定一个中文名称？',
              header: '组件名称',
              multi_select: false,
              options: [{ label: '任务甘特图', description: '适用于任务排期。' }],
            },
          ],
        },
        output_payload: 'User feedback received: [{"question": "请为这个甘特图组件指定一个中文名称？", "selected": ["任务甘特图"]}]',
        message: '',
      } }),
    ])

    expect(items.map(item => item.kind)).toEqual(['feedback_request'])
    const feedbackItem = items[0]
    expect(feedbackItem.kind === 'feedback_request' ? feedbackItem.pending : true).toBe(false)
    expect(feedbackItem.kind === 'feedback_request' ? feedbackItem.subtitle : '').toBe('已回复')
    expect(feedbackItem.kind === 'feedback_request' ? feedbackItem.answerSummary : '').toContain('任务甘特图')
  })

  it('工具详情应直接从 timeline tool item 提取', () => {
    const details = extractTimelineToolDetails([
      timelineItem({ id: 'tool-1', kind: 'tool', role: null, order_index: 0, status: 'completed', source: 'event', tool: {
        tool_call_id: 'call-1',
        tool_name: 'list_workspace_render_assets',
        member_agent_id: 'resource-manager',
        member_agent_name: '资源助手',
        member_run_id: 'member-run-1',
        status: 'completed',
        input_payload: { workspace_id: 11 },
        output_payload: { total: 2 },
        message: '完成',
      } }),
    ])

    expect(details).toEqual([expect.objectContaining({
      id: 'tool-1',
      runId: 'run-1',
      toolCallId: 'call-1',
      toolName: 'list_workspace_render_assets',
      memberAgentName: '资源助手',
      inputPayload: { workspace_id: 11 },
      outputPayload: { total: 2 },
      source: 'event',
    })])
  })

  it('运行失败标题应使用当前智能体名称', () => {
    expect(buildRunIssueState('模型协议错误', '组件助手').title).toBe('组件助手执行失败')
  })
})
