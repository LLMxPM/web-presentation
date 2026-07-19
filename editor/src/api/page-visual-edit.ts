/**
 * 文件功能：封装页面可视化编辑态 artifact 创建与结构化操作批量保存请求。
 */

import { http } from '@/api/http'
import {
  PAGE_VISUAL_EDIT_PROTOCOL_VERSION,
  type ApplyPageVisualEditPayload,
  type CreatePageVisualEditPreviewArtifactPayload,
  type PageVisualEditApplyResponse,
  type PageVisualEditOperation,
  type PageVisualEditJsonValue,
  type PageVisualEditInstancePathSegment,
  type PageVisualEditPreviewArtifactResponse,
  type PageVisualEditTailwindTokenChange,
} from '@/types/page-visual-edit'

interface PageVisualEditWireInstancePathSegment {
  loop_node_id: string
  key?: string | number
  index?: number
}

type PageVisualEditWireOperation =
  | {
    type: 'set_json'
    source_id: string
    value: PageVisualEditJsonValue
  }
  | {
    type: 'set_value'
    node_id: string
    binding_id: string
    instance_path: PageVisualEditWireInstancePathSegment[]
    value: string | number | boolean | null
  }
  | {
    type: 'set_rich_text'
    node_id: string
    binding_id: string
    instance_path: PageVisualEditWireInstancePathSegment[]
    html: string
  }
  | {
    type: 'set_tailwind_tokens'
    node_id: string
    binding_id: string
    instance_path: PageVisualEditWireInstancePathSegment[]
    changes: Array<{
      group: string
      class_name: string | null
    }>
  }
  | {
    type: 'duplicate_node' | 'delete_node'
    node_id: string
    instance_path: PageVisualEditWireInstancePathSegment[]
  }

/**
 * 基于页面当前规范版本创建短期可视化编辑 artifact。
 * @param pageId 页面 ID
 * @param payload 当前页面版本锚点
 * @returns 标准预览信息及静态分析上下文
 */
export async function createPageVisualEditPreviewArtifact(
  pageId: number,
  payload: CreatePageVisualEditPreviewArtifactPayload,
): Promise<PageVisualEditPreviewArtifactResponse> {
  const { data } = await http.post<PageVisualEditPreviewArtifactResponse>(
    `/pages/${pageId}/visual-edit/preview-artifacts`,
    {
      protocol_version: PAGE_VISUAL_EDIT_PROTOCOL_VERSION,
      base_version_no: payload.base_version_no,
    },
  )
  return data
}

/**
 * 批量提交可视化编辑操作；Backend 必须整批成功或整批失败。
 * @param pageId 页面 ID
 * @param payload artifact、版本锚点和 Editor 领域操作
 * @returns 保存后生成的新页面版本
 */
export async function applyPageVisualEditOperations(
  pageId: number,
  payload: ApplyPageVisualEditPayload,
): Promise<PageVisualEditApplyResponse> {
  const { data } = await http.post<PageVisualEditApplyResponse>(`/pages/${pageId}/visual-edit/apply`, {
    protocol_version: PAGE_VISUAL_EDIT_PROTOCOL_VERSION,
    artifact_id: payload.artifact_id,
    base_version_no: payload.base_version_no,
    source_hash: payload.source_hash,
    operations: payload.operations.map(serializePageVisualEditOperation),
    change_note: payload.change_note,
  })
  return data
}

/**
 * 将 Editor/Runtime 使用的 camelCase 操作转换为 Backend 的 snake_case 请求结构。
 * @param operation Editor 领域操作
 * @returns Backend 可直接校验的 wire operation
 */
function serializePageVisualEditOperation(operation: PageVisualEditOperation): PageVisualEditWireOperation {
  if (operation.type === 'set_json') {
    return {
      type: operation.type,
      source_id: operation.sourceId,
      value: operation.value,
    }
  }
  if (operation.type === 'duplicate_node' || operation.type === 'delete_node') {
    return {
      type: operation.type,
      node_id: operation.nodeId,
      instance_path: operation.instancePath.map(serializeInstancePathSegment),
    }
  }
  const target = {
    node_id: operation.nodeId,
    binding_id: operation.bindingId,
    instance_path: operation.instancePath.map(serializeInstancePathSegment),
  }

  if (operation.type === 'set_value') {
    return {
      type: operation.type,
      ...target,
      value: operation.value,
    }
  }

  if (operation.type === 'set_rich_text') {
    return {
      type: operation.type,
      ...target,
      html: operation.html,
    }
  }

  return {
    type: operation.type,
    ...target,
    changes: operation.changes.map(serializeTailwindTokenChange),
  }
}

/**
 * 将 Tailwind 冲突组变更转换为 Backend 字段，并把缺省 class 明确表示为移除。
 * @param change Editor 领域中的 Tailwind 变更
 * @returns Backend wire change
 */
function serializeTailwindTokenChange(change: PageVisualEditTailwindTokenChange): {
  group: string
  class_name: string | null
} {
  return {
    group: change.group,
    class_name: change.className ?? null,
  }
}

/**
 * 序列化单层或未来嵌套循环实例路径，并保留 key/index 的缺省语义。
 * @param segment Runtime 协议中的实例路径段
 * @returns Backend 请求中的实例路径段
 */
function serializeInstancePathSegment(
  segment: PageVisualEditInstancePathSegment,
): PageVisualEditWireInstancePathSegment {
  return {
    loop_node_id: segment.loopNodeId,
    ...('key' in segment ? { key: segment.key } : {}),
    ...('index' in segment ? { index: segment.index } : {}),
  }
}
