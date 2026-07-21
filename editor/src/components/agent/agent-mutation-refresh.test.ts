/**
 * 文件功能：验证智能体工具完成事件到业务刷新事件的映射规则。
 */
import { describe, expect, it } from 'vitest'

import { buildMutationRefreshEvents } from '@/components/agent/agent-mutation-refresh'
import type { AgentRunEvent } from '@/types/api'

const base = {
  workspaceId: 11,
  projectId: 21,
  pageId: 31,
  componentId: null,
}

describe('agent-mutation-refresh', () => {
  it('apply_page_edits 应同时触发页面和项目页面列表刷新', () => {
    const events = buildMutationRefreshEvents(buildToolCompletedEvent('apply_page_edits', {
      success: true,
      page_id: 32,
    }), base)

    expect(events).toEqual([
      expect.objectContaining({ kind: 'page', pageId: 32, toolName: 'apply_page_edits' }),
      expect.objectContaining({ kind: 'project-pages', pageId: 32, toolName: 'apply_page_edits' }),
    ])
  })

  it('update_project_style_config 应触发项目详情刷新', () => {
    const events = buildMutationRefreshEvents(buildToolCompletedEvent('update_project_style_config', {
      success: true,
      style_spec_markdown: '## 风格',
    }), base)

    expect(events).toEqual([
      expect.objectContaining({ kind: 'project', projectId: 21, toolName: 'update_project_style_config' }),
    ])
  })

  it('analyze_visuals 仅为实际刷新的页面截图触发页面和列表刷新', () => {
    const refreshedEvents = buildMutationRefreshEvents(buildToolCompletedEvent('analyze_visuals', {
      items: [{ source: { source_type: 'page_screenshot', page_id: 31, screenshot_refreshed: true } }],
    }), base)
    const cachedEvents = buildMutationRefreshEvents(buildToolCompletedEvent('analyze_visuals', {
      items: [{ source: { source_type: 'page_screenshot', page_id: 31, screenshot_refreshed: false } }],
    }), base)

    expect(refreshedEvents.map(event => event.kind)).toEqual(['page', 'project-pages'])
    expect(cachedEvents).toEqual([])
  })

  it('工具返回 success=false 时不触发刷新', () => {
    const events = buildMutationRefreshEvents(buildToolCompletedEvent('apply_page_edits', {
      success: false,
      page_id: 31,
    }), base)

    expect(events).toEqual([])
  })

  it('save_uploaded_image_as_resource 应触发资源刷新并提取资源 ID', () => {
    const events = buildMutationRefreshEvents(buildToolCompletedEvent('save_uploaded_image_as_resource', {
      success: true,
      created: true,
      attachment_id: 25,
      asset: { id: 91, name: 'uploaded_hero' },
    }), base)

    expect(events).toEqual([
      expect.objectContaining({
        kind: 'asset',
        assetId: 91,
        toolName: 'save_uploaded_image_as_resource',
      }),
    ])
  })
})

/**
 * 构造测试用工具完成事件。
 */
function buildToolCompletedEvent(toolName: string, result: unknown): AgentRunEvent {
  return {
    event: 'tool.completed',
    run_id: 'run-1',
    session_id: 'session-1',
    content: null,
    data: {
      tool_name: toolName,
      tool_call_id: `tool-${toolName}`,
      result,
    },
    sequence: 1,
  }
}
