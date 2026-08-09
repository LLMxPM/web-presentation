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

  it('update_entity 的项目变更应触发项目详情刷新', () => {
    const events = buildMutationRefreshEvents(buildToolCompletedEvent('update_entity', {
      success: true,
      mutation: { resource_type: 'project', operation: 'update' },
      target: { id: 21, resource_type: 'project' },
    }), base)

    expect(events).toEqual([
      expect.objectContaining({ kind: 'project', projectId: 21, toolName: 'update_entity' }),
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

  it('统一 mutation envelope 应按逻辑对象刷新主题和样式', () => {
    const themeEvents = buildMutationRefreshEvents(buildToolCompletedEvent('update_entity', {
      success: true,
      resource_type: 'theme',
      operation: 'update',
      target: { id: 7, resource_type: 'theme' },
      mutation: { kind: 'theme', resource_type: 'theme', operation: 'update' },
      data: { id: 7, name: '海洋主题' },
    }), base)
    const styleEvents = buildMutationRefreshEvents(buildToolCompletedEvent('archive_entity', {
      success: true,
      resource_type: 'style',
      operation: 'archive',
      mutation: { kind: 'style', resource_type: 'style', operation: 'archive' },
      data: { archived_count: 2, target_ids: [8, 9] },
    }), base)

    expect(themeEvents).toEqual([
      expect.objectContaining({ kind: 'theme', themeId: 7, toolName: 'update_entity' }),
    ])
    expect(styleEvents).toEqual([
      expect.objectContaining({ kind: 'style', styleId: null, toolName: 'archive_entity' }),
    ])
  })

  it('统一页面 mutation 应同时刷新页面详情和项目页面列表', () => {
    const events = buildMutationRefreshEvents(buildToolCompletedEvent('update_entity', {
      success: true,
      resource_type: 'page',
      operation: 'update',
      target: { id: 42, resource_type: 'page' },
      mutation: { kind: 'project-pages', resource_type: 'page', operation: 'update' },
      data: { page_id: 42, project_id: 21 },
    }), base)

    expect(events.map(event => event.kind)).toEqual(['page', 'project-pages'])
    expect(events.every(event => event.pageId === 42)).toBe(true)
  })

  it('批量组件归档应为每个目标生成刷新事件', () => {
    const events = buildMutationRefreshEvents(buildToolCompletedEvent('archive_entity', {
      success: true,
      resource_type: 'component',
      operation: 'archive',
      mutation: { resource_type: 'component', operation: 'archive' },
      targets: [{ id: 3 }, { id: 5 }],
    }), base)

    expect(events).toEqual([
      expect.objectContaining({ kind: 'component', componentId: 3 }),
      expect.objectContaining({ kind: 'component', componentId: 5 }),
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
