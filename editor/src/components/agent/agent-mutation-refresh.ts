/**
 * 文件功能：把智能体工具写入事件归一为页面、项目、页面列表、组件或资源刷新通知。
 */
import type { AgentRunEvent } from '@/types/api'
import type { AgentMutationRefreshEvent } from '@/components/agent/agent-conversation-panel'

export interface AgentMutationRefreshBase {
  workspaceId: number | null
  projectId: number | null
  pageId: number | null
  componentId: number | null
  assetId?: number | null
}

/**
 * 根据工具名和工具结果，把后端写入归一成业务刷新事件。
 */
export function buildMutationRefreshEvents(
  event: AgentRunEvent,
  base: AgentMutationRefreshBase,
): AgentMutationRefreshEvent[] {
  const toolName = String(event.data.tool_name || '')
  const result = event.data.result
  const resultRecord = normalizeToolResultRecord(result)
  if (resultRecord && resultRecord.success === false) {
    return []
  }

  const baseEvent = {
    ...base,
    toolName,
    result,
  }

  if (toolName === 'apply_page_edits') {
    const pageId = resolveNumberField(resultRecord, ['page_id']) ?? baseEvent.pageId
    return [
      { ...baseEvent, kind: 'page', pageId },
      { ...baseEvent, kind: 'project-pages', pageId },
    ]
  }

  if (toolName === 'get_page_screenshot') {
    if (resultRecord?.screenshot_refreshed !== true) {
      return []
    }
    const pageId = resolveNumberField(resultRecord, ['page_id']) ?? baseEvent.pageId
    return [
      { ...baseEvent, kind: 'page', pageId },
      { ...baseEvent, kind: 'project-pages', pageId },
    ]
  }

  if (toolName === 'update_project_style_config') {
    return [{
      ...baseEvent,
      kind: 'project',
      projectId: resolveNumberField(resultRecord, ['project_id']) ?? baseEvent.projectId,
    }]
  }

  if (toolName === 'update_page_metadata') {
    const pageId = resolveNumberField(resultRecord, ['page_id']) ?? baseEvent.pageId
    return [
      { ...baseEvent, kind: 'page', pageId },
      { ...baseEvent, kind: 'project-pages', pageId },
    ]
  }

  if (toolName === 'create_project_page') {
    return [{
      ...baseEvent,
      kind: 'project-pages',
      pageId: resolveNumberField(resultRecord, ['page_id']) ?? null,
      projectId: resolveNumberField(resultRecord, ['project_id']) ?? baseEvent.projectId,
    }]
  }

  if (toolName === 'update_project_route_tree') {
    return [{ ...baseEvent, kind: 'project-pages' }]
  }

  if (
    toolName === 'create_component'
    || toolName === 'apply_component_edits'
    || toolName === 'update_component_metadata'
    || toolName === 'publish_component'
    || toolName === 'delete_component'
  ) {
    return [{
      ...baseEvent,
      kind: 'component',
      componentId: resolveComponentIdFromResult(resultRecord) ?? baseEvent.componentId,
    }]
  }

  if (
    toolName === 'create_resource_asset'
    || toolName === 'apply_resource_content_diff'
    || toolName === 'update_resource_asset_metadata'
    || toolName === 'copy_resource_asset'
    || toolName === 'archive_resource_asset'
  ) {
    return [{
      ...baseEvent,
      kind: 'asset',
      assetId: resolveAssetIdFromResult(resultRecord) ?? baseEvent.assetId ?? null,
    }]
  }

  return []
}

/**
 * 去重刷新事件，避免同一轮连续工具调用对同一目标重复刷新。
 */
export function compactMutationRefreshEvents(events: AgentMutationRefreshEvent[]): AgentMutationRefreshEvent[] {
  const eventMap = new Map<string, AgentMutationRefreshEvent>()
  for (const event of events) {
    eventMap.set([
      event.kind,
      event.workspaceId ?? '',
      event.projectId ?? '',
      event.pageId ?? '',
      event.componentId ?? '',
      event.assetId ?? '',
    ].join(':'), event)
  }
  return [...eventMap.values()]
}

/**
 * 从工具结果中的 asset 或 asset_id 提取资源 ID。
 */
function resolveAssetIdFromResult(resultRecord: Record<string, unknown> | null): number | null {
  const directId = resolveNumberField(resultRecord, ['asset_id', 'id'])
  if (directId !== null) {
    return directId
  }
  const asset = resultRecord && isRecord(resultRecord.asset) ? resultRecord.asset : null
  return resolveNumberField(asset, ['id', 'asset_id'])
}

/**
 * 工具结果可能是 JSON 字符串或对象；这里只在对象结构下提取字段。
 */
function normalizeToolResultRecord(result: unknown): Record<string, unknown> | null {
  if (typeof result === 'string') {
    const trimmed = result.trim()
    if (!trimmed.startsWith('{')) {
      return null
    }
    try {
      const parsed = JSON.parse(trimmed) as unknown
      return isRecord(parsed) ? parsed : null
    } catch {
      return null
    }
  }
  return isRecord(result) ? result : null
}

/**
 * 从工具结果中的 component 或 component_id 提取组件 ID。
 */
function resolveComponentIdFromResult(resultRecord: Record<string, unknown> | null): number | null {
  const directId = resolveNumberField(resultRecord, ['component_id'])
  if (directId !== null) {
    return directId
  }
  const component = resultRecord && isRecord(resultRecord.component) ? resultRecord.component : null
  return resolveNumberField(component, ['id'])
}

/**
 * 从对象的多个候选字段中读取正整数 ID。
 */
function resolveNumberField(record: Record<string, unknown> | null, fieldNames: string[]): number | null {
  if (!record) {
    return null
  }
  for (const fieldName of fieldNames) {
    const value = Number(record[fieldName])
    if (Number.isFinite(value) && value > 0) {
      return value
    }
  }
  return null
}

/**
 * 判断未知值是否为普通对象。
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
