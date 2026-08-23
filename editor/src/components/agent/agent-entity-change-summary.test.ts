/**
 * 文件功能：验证从工具结果聚合本轮项目/页面变更摘要的规则。
 */
import { describe, expect, it } from 'vitest'

import {
  collectEntityChangesByRun,
  extractEntityChangesFromTool,
  isRunTerminalForEntitySummary,
  mergeEntityChanges,
} from '@/components/agent/agent-entity-change-summary'
import type { AgentTimelineItem } from '@/types/api'

/**
 * 构造最小时间线项。
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

describe('agent-entity-change-summary', () => {
  it('统一 mutation envelope 应提取新建页面', () => {
    const changes = extractEntityChangesFromTool(
      'create_entity',
      { resource_type: 'page', mode: 'new', project_id: 21, title: '封面' },
      {
        success: true,
        resource_type: 'page',
        operation: 'create',
        target: { id: 42, resource_type: 'page' },
        mutation: { resource_type: 'page', operation: 'create', target: { id: 42, resource_type: 'page' } },
        data: { page_id: 42, project_id: 21, title: '封面' },
      },
      { runId: 'run-1', workspaceId: 11, projectId: 21 },
    )

    expect(changes).toEqual([expect.objectContaining({
      resourceType: 'page',
      id: 42,
      projectId: 21,
      workspaceId: 11,
      name: '封面',
      effect: 'create',
    })])
  })

  it('apply_page_edits 旧结构应提取页面更新并可回落 run focus 的 projectId', () => {
    const changes = extractEntityChangesFromTool(
      'apply_page_edits',
      { page_id: 31 },
      { success: true, page_id: 31 },
      { runId: 'run-1', workspaceId: 11, projectId: 21 },
    )

    expect(changes).toEqual([expect.objectContaining({
      resourceType: 'page',
      id: 31,
      projectId: 21,
      effect: 'update',
      name: null,
    })])
  })

  it('success=false 与非项目页面 mutation 应忽略', () => {
    expect(extractEntityChangesFromTool(
      'update_entity',
      { resource_type: 'page' },
      { success: false, mutation: { resource_type: 'page', operation: 'update' }, target: { id: 1 } },
      { runId: 'run-1', workspaceId: 11, projectId: 21 },
    )).toEqual([])

    expect(extractEntityChangesFromTool(
      'update_entity',
      { resource_type: 'theme' },
      {
        success: true,
        mutation: { resource_type: 'theme', operation: 'update' },
        target: { id: 7, resource_type: 'theme' },
      },
      { runId: 'run-1', workspaceId: 11, projectId: null },
    )).toEqual([])
  })

  it('同一实体多次变更应去重并合并 effect', () => {
    const merged = mergeEntityChanges([
      {
        resourceType: 'page',
        id: 31,
        projectId: 21,
        workspaceId: 11,
        name: null,
        effect: 'create',
        runId: 'run-1',
        sourceToolName: 'create_entity',
      },
      {
        resourceType: 'page',
        id: 31,
        projectId: 21,
        workspaceId: 11,
        name: '经营概览',
        effect: 'update',
        runId: 'run-1',
        sourceToolName: 'update_entity',
      },
    ])

    expect(merged).toEqual([expect.objectContaining({
      id: 31,
      name: '经营概览',
      effect: 'create',
    })])
  })

  it('批量归档应生成多条 archive 变更', () => {
    const changes = extractEntityChangesFromTool(
      'archive_entity',
      { resource_type: 'page', target_ids: [1, 2] },
      {
        success: true,
        resource_type: 'page',
        operation: 'archive',
        mutation: { resource_type: 'page', operation: 'archive' },
        targets: [
          { id: 1, resource_type: 'page', project_id: 21, title: 'A' },
          { id: 2, resource_type: 'page', project_id: 21, title: 'B' },
        ],
      },
      { runId: 'run-1', workspaceId: 11, projectId: 21 },
    )

    expect(changes).toHaveLength(2)
    expect(changes.every(item => item.effect === 'archive')).toBe(true)
  })
})
