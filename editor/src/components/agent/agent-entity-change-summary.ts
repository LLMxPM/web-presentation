/**
 * 文件功能：从智能体 run 时间线聚合本轮新增/修改的项目与页面，供对话内快捷卡片展示。
 */
import type { AgentTimelineItem } from '@/types/api'

/** 实体变更效果：创建、更新或归档。 */
export type AgentEntityChangeEffect = 'create' | 'update' | 'archive'

/** 单条可打开的项目或页面变更摘要。 */
export interface AgentEntityChangeItem {
  resourceType: 'project' | 'page'
  id: number
  projectId: number | null
  workspaceId: number | null
  name: string | null
  effect: AgentEntityChangeEffect
  runId: string
  sourceToolName: string
}

const ENTITY_RESOURCE_TYPES = new Set(['project', 'page'])
const PAGE_CREATE_TOOLS = new Set(['create_project_page'])
const PAGE_UPDATE_TOOLS = new Set(['apply_page_edits', 'update_page_metadata'])
const PROJECT_UPDATE_TOOLS = new Set([
  'update_project_route_tree',
  'update_project_metadata',
  'update_project_configuration',
  'apply_project_style',
  'update_project_build_assets',
])

/**
 * 从父 Run 时间线中，按 run 聚合成功写入的项目/页面变更。
 * @param timelineItems 会话主时间线
 * @param workspaceId 当前工作空间 ID，用于卡片导航兜底
 */
export function collectEntityChangesByRun(
  timelineItems: AgentTimelineItem[],
  workspaceId: number | null = null,
): Map<string, AgentEntityChangeItem[]> {
  const byRun = new Map<string, AgentEntityChangeItem[]>()
  const runContextWorkspace = new Map<string, number | null>()
  const runContextProject = new Map<string, number | null>()

  for (const item of timelineItems) {
    if (item.kind === 'run_context' && item.run_context) {
      runContextWorkspace.set(item.run_id, item.run_context.focus.workspace_id ?? workspaceId)
      runContextProject.set(item.run_id, item.run_context.focus.project_id ?? null)
    }
  }

  const appendFromTools = (items: AgentTimelineItem[]) => {
    for (const item of items) {
      if (item.kind !== 'tool' || !item.tool || item.tool.status !== 'completed') {
        continue
      }
      const runId = item.run_id
      if (!runId) {
        continue
      }
      const resolvedWorkspace = runContextWorkspace.get(runId) ?? workspaceId
      const resolvedProject = runContextProject.get(runId) ?? null
      const changes = extractEntityChangesFromTool(
        item.tool.tool_name || '',
        item.tool.input_payload,
        item.tool.output_payload,
        {
          runId,
          workspaceId: resolvedWorkspace,
          projectId: resolvedProject,
        },
      )
      if (!changes.length) {
        continue
      }
      const bucket = byRun.get(runId) ?? []
      bucket.push(...changes)
      byRun.set(runId, bucket)
    }
  }

  appendFromTools(timelineItems)
  const merged = new Map<string, AgentEntityChangeItem[]>()
  for (const [runId, changes] of byRun) {
    const deduped = mergeEntityChanges(changes)
    if (deduped.length) {
      merged.set(runId, deduped)
    }
  }
  return merged
}

/**
 * 从单个已完成工具调用的输入输出中提取项目/页面变更。
 */
export function extractEntityChangesFromTool(
  toolName: string,
  inputPayload: unknown,
  outputPayload: unknown,
  context: { runId: string, workspaceId: number | null, projectId: number | null },
): AgentEntityChangeItem[] {
  const resultRecord = normalizeToolResultRecord(outputPayload)
  if (!resultRecord || resultRecord.success === false) {
    return []
  }

  const fromEnvelope = extractFromMutationEnvelope(resultRecord, toolName, inputPayload, context)
  if (fromEnvelope.length) {
    return fromEnvelope
  }
  return extractFromLegacyTool(toolName, resultRecord, inputPayload, context)
}

/**
 * 合并同一实体的多次变更：归档优先；否则创建保留 create 语义；名称与 projectId 取最新非空值。
 */
export function mergeEntityChanges(changes: AgentEntityChangeItem[]): AgentEntityChangeItem[] {
  const map = new Map<string, AgentEntityChangeItem>()
  for (const change of changes) {
    const key = `${change.resourceType}:${change.id}`
    const existing = map.get(key)
    if (!existing) {
      map.set(key, { ...change })
      continue
    }
    map.set(key, {
      ...existing,
      ...change,
      name: change.name?.trim() || existing.name,
      projectId: change.projectId ?? existing.projectId,
      workspaceId: change.workspaceId ?? existing.workspaceId,
      effect: mergeEffects(existing.effect, change.effect),
      sourceToolName: change.sourceToolName || existing.sourceToolName,
    })
  }
  return [...map.values()].sort((left, right) => {
    if (left.resourceType !== right.resourceType) {
      return left.resourceType === 'project' ? -1 : 1
    }
    return left.id - right.id
  })
}

/**
 * 判断 run 是否应展示实体摘要卡。
 * 后端主 run 快照通常不带 run_status；终态以「该 run 不是当前 activeRun」判定。
 * 仍在进行中的 run（含 waiting_external / paused）通过 activeRunId 排除，避免闪烁。
 */
export function isRunTerminalForEntitySummary(
  runId: string,
  activeRunId: string | null = null,
): boolean {
  if (!runId) {
    return false
  }
  // 当前仍在执行的 run 不展示；历史 run 与刚完成的 lastRun 均可展示。
  return activeRunId !== runId
}

/**
 * 解析 mutation envelope 中的 project/page 目标。
 */
function extractFromMutationEnvelope(
  resultRecord: Record<string, unknown>,
  toolName: string,
  inputPayload: unknown,
  context: { runId: string, workspaceId: number | null, projectId: number | null },
): AgentEntityChangeItem[] {
  const mutation = isRecord(resultRecord.mutation) ? resultRecord.mutation : null
  if (!mutation) {
    return []
  }
  const resourceType = String(mutation.resource_type || resultRecord.resource_type || '')
  if (!ENTITY_RESOURCE_TYPES.has(resourceType)) {
    return []
  }
  const effect = resolveEffect(
    String(mutation.operation || resultRecord.operation || ''),
    String(mutation.effect || resultRecord.effect || ''),
  )
  const data = isRecord(resultRecord.data) ? resultRecord.data : null
  const nestedData = data && isRecord(data.data) ? data.data : data
  const input = isRecord(inputPayload) ? inputPayload : null
  const target = isRecord(resultRecord.target)
    ? resultRecord.target
    : (isRecord(mutation.target) ? mutation.target : null)
  const targets = Array.isArray(resultRecord.targets)
    ? resultRecord.targets.filter(isRecord)
    : []

  const targetRecords: Record<string, unknown>[] = targets.length
    ? targets
    : (target ? [target] : [])

  if (!targetRecords.length && nestedData) {
    const fallbackId = resourceType === 'page'
      ? resolveNumberField(nestedData, ['page_id', 'id'])
      : resolveNumberField(nestedData, ['project_id', 'id'])
    if (fallbackId !== null) {
      targetRecords.push({
        id: fallbackId,
        resource_type: resourceType,
        ...(resourceType === 'page'
          ? {
              project_id: resolveNumberField(nestedData, ['project_id']) ?? context.projectId,
              title: resolveStringField(nestedData, ['title', 'name']),
            }
          : {
              name: resolveStringField(nestedData, ['name', 'title']),
            }),
      })
    }
  }

  return targetRecords.flatMap((record) => {
    const id = resolveNumberField(record, ['id', resourceType === 'page' ? 'page_id' : 'project_id'])
    if (id === null) {
      return []
    }
    const projectId = resourceType === 'project'
      ? id
      : (
          resolveNumberField(record, ['project_id'])
          ?? resolveNumberField(nestedData, ['project_id'])
          ?? resolveNumberField(input, ['project_id'])
          ?? context.projectId
        )
    const name = resourceType === 'page'
      ? (
          resolveStringField(record, ['title', 'name'])
          ?? resolveStringField(nestedData, ['title', 'name'])
          ?? resolveStringField(input, ['title', 'name'])
        )
      : (
          resolveStringField(record, ['name', 'title'])
          ?? resolveStringField(nestedData, ['name', 'title'])
          ?? resolveStringField(input, ['name', 'title'])
        )
    return [{
      resourceType: resourceType as 'project' | 'page',
      id,
      projectId,
      workspaceId: resolveNumberField(record, ['workspace_id'])
        ?? resolveNumberField(nestedData, ['workspace_id'])
        ?? context.workspaceId,
      name,
      effect,
      runId: context.runId,
      sourceToolName: toolName,
    }]
  })
}

/**
 * 兼容旧物理工具名返回结构。
 */
function extractFromLegacyTool(
  toolName: string,
  resultRecord: Record<string, unknown>,
  inputPayload: unknown,
  context: { runId: string, workspaceId: number | null, projectId: number | null },
): AgentEntityChangeItem[] {
  const input = isRecord(inputPayload) ? inputPayload : null
  if (PAGE_CREATE_TOOLS.has(toolName)) {
    const pageId = resolveNumberField(resultRecord, ['page_id', 'id'])
    if (pageId === null) {
      return []
    }
    return [{
      resourceType: 'page',
      id: pageId,
      projectId: resolveNumberField(resultRecord, ['project_id']) ?? resolveNumberField(input, ['project_id']) ?? context.projectId,
      workspaceId: context.workspaceId,
      name: resolveStringField(resultRecord, ['title', 'name']) ?? resolveStringField(input, ['title', 'name']),
      effect: 'create',
      runId: context.runId,
      sourceToolName: toolName,
    }]
  }
  if (PAGE_UPDATE_TOOLS.has(toolName)) {
    const pageId = resolveNumberField(resultRecord, ['page_id', 'id'])
      ?? resolveNumberField(input, ['page_id'])
    if (pageId === null) {
      return []
    }
    return [{
      resourceType: 'page',
      id: pageId,
      projectId: resolveNumberField(resultRecord, ['project_id'])
        ?? resolveNumberField(input, ['project_id'])
        ?? context.projectId,
      workspaceId: context.workspaceId,
      name: resolveStringField(resultRecord, ['title', 'name']) ?? resolveStringField(input, ['title', 'name']),
      effect: 'update',
      runId: context.runId,
      sourceToolName: toolName,
    }]
  }
  if (PROJECT_UPDATE_TOOLS.has(toolName)) {
    const projectId = resolveNumberField(resultRecord, ['project_id', 'id'])
      ?? resolveNumberField(input, ['project_id'])
      ?? context.projectId
    if (projectId === null) {
      return []
    }
    return [{
      resourceType: 'project',
      id: projectId,
      projectId,
      workspaceId: context.workspaceId,
      name: resolveStringField(resultRecord, ['name', 'title']) ?? resolveStringField(input, ['name', 'title']),
      effect: 'update',
      runId: context.runId,
      sourceToolName: toolName,
    }]
  }
  return []
}

/** 合并两次 effect：归档优先，其次创建，否则更新。 */
function mergeEffects(
  left: AgentEntityChangeEffect,
  right: AgentEntityChangeEffect,
): AgentEntityChangeEffect {
  if (left === 'archive' || right === 'archive') {
    return 'archive'
  }
  if (left === 'create' || right === 'create') {
    return 'create'
  }
  return 'update'
}

/** 由 operation/effect 字段推导展示用 effect。 */
function resolveEffect(operation: string, effect: string): AgentEntityChangeEffect {
  const token = `${operation} ${effect}`.toLowerCase()
  if (token.includes('archive')) {
    return 'archive'
  }
  if (token.includes('create') || token.includes('copy')) {
    return 'create'
  }
  return 'update'
}

/** 工具结果可能是 JSON 字符串或对象。 */
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

/** 从候选字段读取正整数。 */
function resolveNumberField(record: Record<string, unknown> | null | undefined, fieldNames: string[]): number | null {
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

/** 从候选字段读取非空字符串。 */
function resolveStringField(record: Record<string, unknown> | null | undefined, fieldNames: string[]): string | null {
  if (!record) {
    return null
  }
  for (const fieldName of fieldNames) {
    const value = record[fieldName]
    if (typeof value === 'string' && value.trim()) {
      return value.trim()
    }
  }
  return null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

