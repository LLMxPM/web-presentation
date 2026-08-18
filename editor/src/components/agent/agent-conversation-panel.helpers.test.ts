/**
 * 文件功能：验证内容助手 run-first 时间线展示辅助逻辑，确保刷新后工具调用独立回放。
 */
import { describe, expect, it } from 'vitest'

import {
  buildRunIssueState,
  buildTimelineDisplayItems,
  extractTimelineToolDetails,
  resolveLogicalToolName,
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
  it('每轮焦点与工作范围应作为消息开头的独立展示项', () => {
    const items = buildTimelineDisplayItems([
      timelineItem({
        id: 'run-context-1',
        kind: 'run_context',
        role: null,
        order_index: 1,
        run_context: {
          focus: {
            scope_type: 'page',
            workspace_id: 11,
            workspace_name: '产品空间',
            project_id: 21,
            project_name: '年度汇报',
            page_id: 31,
            page_title: '经营概览',
            source: 'editor-page-detail',
          },
          work_scope_mode: 'selected_projects',
          allowed_projects: [{ id: 21, name: '年度汇报' }],
          focus_version: 2,
        },
      }),
      timelineItem({ id: 'user-1', kind: 'message', role: 'user', order_index: 0, content: '修改页面' }),
    ])

    expect(items.map(item => item.kind)).toEqual(['message', 'run_context'])
    expect(items[1].kind === 'run_context' ? items[1].context.focus.page_title : null).toBe('经营概览')
  })

  it('固定通用工具应显示真实逻辑操作名称', () => {
    expect(resolveLogicalToolName('list_entities', { resource_type: 'page' })).toBe('罗列页面')
    expect(resolveLogicalToolName('get_entity', { resource_type: 'page', view: 'content' })).toBe('读取页面')
    expect(resolveLogicalToolName('query_entities', { resource_type: 'page' })).toBe('查询页面')
    expect(resolveLogicalToolName('update_entity', { resource_type: 'theme' })).toBe('修改主题')
    expect(resolveLogicalToolName('create_entity', { resource_type: 'style', mode: 'copy' })).toBe('复制样式')
    expect(resolveLogicalToolName('create_entity', { resource_type: 'asset', mode: 'upload' })).toBe('从上传创建资源')
    expect(resolveLogicalToolName('validate_entity', { resource_type: 'asset', action: 'preview' })).toBe('预览资源改动')
    expect(resolveLogicalToolName('archive_entity', { resource_type: 'asset', target_ids: [1, 2] })).toBe('批量归档资源')
    expect(resolveLogicalToolName('execute_dangerous_action', { resource_type: 'project', action: 'replace_routes' })).toBe('覆盖项目路由')
    expect(resolveLogicalToolName('get_operation_guide', { operation_key: 'page.update.content' })).toBe('查看页面操作手册')
    expect(resolveLogicalToolName('get_operation_guide', {})).toBe('查看操作手册索引')
    expect(resolveLogicalToolName('execute_action', { resource_type: 'style', action: 'restore' })).toBe('恢复样式')
  })

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

  it('当前 pending ask_user 应只在输入区处理，不在时间线重复展示', () => {
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

    expect(items).toEqual([])
  })

  it('没有当前 pending 时不应展示历史工具确认 requirement', () => {
    const items = buildTimelineDisplayItems([
      timelineItem({
        id: 'requirement-requirement-tool-1',
        kind: 'requirement',
        role: null,
        order_index: 1,
        status: 'paused',
        content: '工具 apply_page_edits 需要确认后执行。',
      }),
    ])

    expect(items).toEqual([])
  })

  it('当前 pending 工具确认仍应展示为待处理状态', () => {
    const pendingRequirement: AgentPendingRequirement = {
      id: 'requirement-tool-1',
      kind: 'confirmation',
      run_id: 'run-1',
      session_id: 'session-1',
      tool_name: 'apply_page_edits',
      tool_execution: { tool_name: 'apply_page_edits', tool_call_id: 'tool-confirm-1' },
      suggested_patch: null,
      user_feedback_schema: [],
      note: '工具 apply_page_edits 需要确认后执行。',
    }
    const items = buildTimelineDisplayItems([
      timelineItem({
        id: 'requirement-requirement-tool-1',
        kind: 'requirement',
        role: null,
        order_index: 1,
        status: 'paused',
        content: '工具 apply_page_edits 需要确认后执行。',
      }),
    ], { pendingRequirement })

    expect(items.map(item => item.kind)).toEqual(['requirement'])
    expect(items[0].kind === 'requirement' ? items[0].content : '').toBe('工具 apply_page_edits 需要确认后执行。')
  })

  it('已回答 ask_user 应只提取选择答案', () => {
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
    expect(feedbackItem.kind === 'feedback_request' ? feedbackItem.entries : []).toEqual([
      { question: '请为这个甘特图组件指定一个中文名称？', answerText: '任务甘特图' },
    ])
  })

  it('已回答 ask_user 应只提取自定义输入内容', () => {
    const items = buildTimelineDisplayItems([
      timelineItem({ id: 'tool-ask-custom', kind: 'tool', role: null, order_index: 1, status: 'completed', tool: {
        tool_call_id: 'tool-ask-2',
        tool_name: 'ask_user',
        status: 'completed',
        input_payload: {
          questions: [
            {
              question: '视觉风格倾向是什么？',
              header: '风格',
              multi_select: false,
              options: [{ label: '极简', description: '减少装饰。' }],
            },
          ],
        },
        output_payload: 'User feedback received: [{"question": "视觉风格倾向是什么？", "selected": ["用户补充：保留当前图标风格"]}]',
        message: '',
      } }),
    ])

    const feedbackItem = items[0]
    expect(feedbackItem.kind === 'feedback_request' ? feedbackItem.entries : []).toEqual([
      { question: '视觉风格倾向是什么？', answerText: '保留当前图标风格' },
    ])
  })

  it('工具详情应直接从 timeline tool item 提取', () => {
    const details = extractTimelineToolDetails([
      timelineItem({ id: 'tool-1', kind: 'tool', role: null, order_index: 0, status: 'completed', source: 'event', tool: {
        tool_call_id: 'call-1',
        tool_name: 'list_workspace_render_assets',
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
      inputPayload: { workspace_id: 11 },
      outputPayload: { total: 2 },
      source: 'event',
    })])
  })

  it('Run 终态后应在助手消息与完成状态之间插入项目/页面实体摘要', () => {
    const items = buildTimelineDisplayItems([
      timelineItem({ id: 'user-1', kind: 'message', role: 'user', order_index: 0, content: '创建封面页' }),
      timelineItem({
        id: 'tool-1',
        kind: 'tool',
        role: null,
        order_index: 1,
        status: 'completed',
        tool: {
          tool_call_id: 'call-1',
          tool_name: 'create_entity',
          status: 'completed',
          input_payload: { resource_type: 'page', project_id: 21, title: '封面' },
          output_payload: {
            success: true,
            mutation: { resource_type: 'page', operation: 'create' },
            target: { id: 42, resource_type: 'page' },
            data: { page_id: 42, project_id: 21, title: '封面' },
          },
          message: '',
        },
      }),
      timelineItem({ id: 'assistant-1', kind: 'message', role: 'assistant', order_index: 2, content: '已创建封面页。' }),
      timelineItem({ id: 'status-1', kind: 'run_status', role: null, order_index: 3, status: 'completed', content: '运行已完成。' }),
    ], { workspaceId: 11 })

    expect(items.map(item => item.kind)).toEqual(['message', 'tool_group', 'message', 'entity_summary', 'run_status'])
    const summary = items.find(item => item.kind === 'entity_summary')
    expect(summary?.kind === 'entity_summary' ? summary.items : []).toEqual([
      expect.objectContaining({ resourceType: 'page', id: 42, projectId: 21, name: '封面', effect: 'create' }),
    ])
  })

  it('当前 activeRun 未结束时不应插入实体摘要', () => {
    const items = buildTimelineDisplayItems([
      timelineItem({
        id: 'tool-1',
        kind: 'tool',
        role: null,
        order_index: 0,
        status: 'completed',
        tool: {
          tool_call_id: 'call-1',
          tool_name: 'apply_page_edits',
          status: 'completed',
          input_payload: { page_id: 31 },
          output_payload: { success: true, page_id: 31 },
          message: '',
        },
      }),
      timelineItem({ id: 'status-1', kind: 'run_status', role: null, order_index: 1, status: 'waiting_external', content: '页面变更正在后台处理。' }),
    ], { workspaceId: 11, activeRunId: 'run-1' })

    expect(items.map(item => item.kind)).toEqual(['tool_group', 'run_status'])
  })

  it('历史快照无 run_status 时仍应展示实体摘要', () => {
    const items = buildTimelineDisplayItems([
      timelineItem({ id: 'user-1', kind: 'message', role: 'user', order_index: 0, content: '创建封面页' }),
      timelineItem({
        id: 'tool-1',
        kind: 'tool',
        role: null,
        order_index: 1,
        status: 'completed',
        tool: {
          tool_call_id: 'call-1',
          tool_name: 'create_entity',
          status: 'completed',
          input_payload: { resource_type: 'page', project_id: 21, title: '封面' },
          output_payload: {
            success: true,
            mutation: { resource_type: 'page', operation: 'create' },
            target: { id: 42, resource_type: 'page' },
            data: { page_id: 42, project_id: 21, title: '封面' },
          },
          message: '',
        },
      }),
      timelineItem({ id: 'assistant-1', kind: 'message', role: 'assistant', order_index: 2, content: '已创建封面页。' }),
    ], { workspaceId: 11, activeRunId: null })

    expect(items.map(item => item.kind)).toEqual(['message', 'tool_group', 'message', 'entity_summary'])
  })

  it('摘要卡应插在助手消息与工具组二者的最后位置之后', () => {
    const items = buildTimelineDisplayItems([
      timelineItem({ id: 'assistant-1', kind: 'message', role: 'assistant', order_index: 0, content: '先说明，再改页面。' }),
      timelineItem({
        id: 'tool-1',
        kind: 'tool',
        role: null,
        order_index: 1,
        status: 'completed',
        tool: {
          tool_call_id: 'call-1',
          tool_name: 'apply_page_edits',
          status: 'completed',
          input_payload: { page_id: 31 },
          output_payload: {
            success: true,
            mutation: { resource_type: 'page', operation: 'update' },
            target: { id: 31, resource_type: 'page' },
            data: { page_id: 31, project_id: 21, title: '经营概览' },
          },
          message: '',
        },
      }),
      timelineItem({ id: 'status-1', kind: 'run_status', role: null, order_index: 2, status: 'completed', content: '运行已完成。' }),
    ], { workspaceId: 11, activeRunId: null })

    expect(items.map(item => item.kind)).toEqual(['message', 'tool_group', 'entity_summary', 'run_status'])
  })

  it('运行失败标题应使用当前智能体名称', () => {
    expect(buildRunIssueState('模型协议错误', '组件助手').title).toBe('组件助手执行失败')
  })

  it('底层流式连接中断应转成可操作提示', () => {
    const issue = buildRunIssueState(
      'peer closed connection without sending complete message body (incomplete chunked read)',
      '内容助手',
    )

    expect(issue.title).toBe('模型连接中断')
    expect(issue.detail).toContain('可以直接重试')
    expect(issue.detail).not.toContain('incomplete chunked read')
  })
})
