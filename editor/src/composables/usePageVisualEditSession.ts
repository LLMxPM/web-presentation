/**
 * 文件功能：管理页面可视化编辑 artifact、受信任 Runtime 选区、待提交草稿与批量保存刷新流程。
 */

import { computed, onMounted, onUnmounted, ref } from 'vue'

import {
  applyPageVisualEditOperations,
  createPageVisualEditPreviewArtifact,
} from '@/api/page-visual-edit'
import { getErrorMessage } from '@/api/http'
import { usePageVisualEditDraft } from '@/composables/usePageVisualEditDraft'
import {
  PAGE_VISUAL_EDIT_PROTOCOL_VERSION,
  PAGE_VISUAL_EDIT_SELECTION_EVENT,
  type PageVisualEditApplyResponse,
  type PageVisualEditInstancePathSegment,
  type PageVisualEditNode,
  type PageVisualEditPreviewArtifactResponse,
  type PageVisualEditSelectionMessage,
} from '@/types/page-visual-edit'

/**
 * 创建页面可视化编辑会话；该会话只接收 Runtime 选择消息，不向 iframe 下发属性覆盖。
 */
export function usePageVisualEditSession() {
  const draft = usePageVisualEditDraft()
  const artifact = ref<PageVisualEditPreviewArtifactResponse | null>(null)
  const previewFrameRef = ref<HTMLIFrameElement | null>(null)
  const selectedNodeId = ref('')
  const selectedBindingId = ref('')
  const selectedInstancePath = ref<PageVisualEditInstancePathSegment[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const stale = ref(false)
  const errorMessage = ref('')
  const lastRefreshSucceeded = ref(true)
  let requestSequence = 0

  const manifest = computed(() => artifact.value?.visual_edit.manifest ?? null)
  const previewOrigin = computed(() => resolveUrlOrigin(artifact.value?.preview_url ?? ''))
  const selectedNode = computed(() => (
    manifest.value ? findVisualEditNode(manifest.value.root, selectedNodeId.value) : null
  ))
  const selectedBinding = computed(() => (
    selectedNode.value?.bindings.find(item => item.binding_id === selectedBindingId.value) ?? null
  ))

  /**
   * 基于 Backend 当前页面版本创建新的编辑态 artifact。
   * @param pageId 页面 ID
   * @param baseVersionNo 当前规范版本号
   * @returns 成功响应；失败或被新请求覆盖时返回 null
   */
  async function analyze(pageId: number, baseVersionNo: number): Promise<PageVisualEditPreviewArtifactResponse | null> {
    const sequence = ++requestSequence
    loading.value = true
    errorMessage.value = ''
    try {
      const response = await createPageVisualEditPreviewArtifact(pageId, {
        base_version_no: baseVersionNo,
      })
      if (sequence !== requestSequence) return null
      artifact.value = response
      stale.value = false
      lastRefreshSucceeded.value = true
      selectNode(response.visual_edit.manifest.root.node_id)
      return response
    } catch (error) {
      if (sequence !== requestSequence) return null
      lastRefreshSucceeded.value = false
      errorMessage.value = getErrorMessage(error, '创建可视化编辑预览失败。')
      return null
    } finally {
      if (sequence === requestSequence) {
        loading.value = false
      }
    }
  }

  /**
   * 保存全部草稿操作；apply 成功后立即清空已落库草稿，再按新版本重新分析。
   * @param pageId 页面 ID
   * @param changeNote 页面版本说明
   * @returns apply 成功响应；保存失败或没有可提交操作时返回 null
   */
  async function save(pageId: number, changeNote = '可视化编辑'): Promise<PageVisualEditApplyResponse | null> {
    const currentArtifact = artifact.value
    if (!currentArtifact || !draft.hasPendingChanges.value || saving.value || stale.value) return null

    saving.value = true
    errorMessage.value = ''
    let result: PageVisualEditApplyResponse
    try {
      result = await applyPageVisualEditOperations(pageId, {
        artifact_id: currentArtifact.artifact_id,
        base_version_no: currentArtifact.visual_edit.base_version_no,
        source_hash: currentArtifact.visual_edit.source_hash,
        operations: draft.pendingOperations.value,
        change_note: changeNote,
      })
    } catch (error) {
      errorMessage.value = getErrorMessage(error, '保存可视化编辑失败。')
      return null
    } finally {
      saving.value = false
    }

    draft.clearOperations()
    artifact.value = null
    selectedNodeId.value = ''
    selectedBindingId.value = ''
    selectedInstancePath.value = []
    await analyze(pageId, result.current_version_no)
    return result
  }

  /**
   * 从图层树或可信 Runtime 消息切换当前选择。
   * @param nodeId Manifest 节点 ID
   * @param bindingId 可选绑定 ID
   * @param instancePath 可选循环实例路径
   */
  function selectNode(
    nodeId: string,
    bindingId = '',
    instancePath: PageVisualEditInstancePathSegment[] = [],
  ): void {
    const root = manifest.value?.root
    const node = root ? findVisualEditNode(root, nodeId) : null
    if (!node) return
    const binding = bindingId ? node.bindings.find(item => item.binding_id === bindingId) : null
    selectedNodeId.value = node.node_id
    selectedBindingId.value = binding?.binding_id ?? ''
    selectedInstancePath.value = cloneInstancePath(instancePath)
  }

  /** 将当前会话标记为过期，阻止旧节点 ID 被继续保存。 */
  function markStale(): void {
    stale.value = true
    errorMessage.value = '页面版本已在其他位置更新，请放弃当前草稿后重新分析。'
  }

  /** 放弃本地操作，保留当前 artifact 供重新选择。 */
  function discardChanges(): void {
    draft.clearOperations()
  }

  /** 清空 artifact、选择和草稿，用于页面切换或组件卸载。 */
  function reset(): void {
    requestSequence += 1
    artifact.value = null
    selectedNodeId.value = ''
    selectedBindingId.value = ''
    selectedInstancePath.value = []
    errorMessage.value = ''
    loading.value = false
    saving.value = false
    stale.value = false
    draft.clearOperations()
  }

  /**
   * 接收 Runtime iframe 选择消息，并执行 source、origin、artifact 与协议四重校验。
   * @param event 浏览器 message 事件
   */
  function handleWindowMessage(event: MessageEvent<unknown>): void {
    const frameWindow = previewFrameRef.value?.contentWindow
    if (!frameWindow || event.source !== frameWindow || !previewOrigin.value || event.origin !== previewOrigin.value) {
      return
    }
    if (!isSelectionMessage(event.data)) return
    const payload = event.data.payload
    if (
      payload.protocolVersion !== PAGE_VISUAL_EDIT_PROTOCOL_VERSION
      || payload.artifactId !== artifact.value?.artifact_id
    ) {
      return
    }
    const node = manifest.value ? findVisualEditNode(manifest.value.root, payload.nodeId) : null
    if (!node || (payload.bindingId && !node.bindings.some(item => item.binding_id === payload.bindingId))) {
      return
    }
    selectNode(payload.nodeId, payload.bindingId, payload.instancePath)
  }

  onMounted(() => window.addEventListener('message', handleWindowMessage))
  onUnmounted(() => {
    window.removeEventListener('message', handleWindowMessage)
    requestSequence += 1
  })

  return {
    ...draft,
    artifact,
    manifest,
    previewFrameRef,
    selectedNode,
    selectedBinding,
    selectedNodeId,
    selectedBindingId,
    selectedInstancePath,
    loading,
    saving,
    stale,
    errorMessage,
    lastRefreshSucceeded,
    analyze,
    save,
    selectNode,
    markStale,
    discardChanges,
    reset,
  }
}

/**
 * 在递归 Manifest 中查找节点。
 * @param root 当前子树根节点
 * @param nodeId 目标节点 ID
 * @returns 命中的节点或 null
 */
export function findVisualEditNode(root: PageVisualEditNode, nodeId: string): PageVisualEditNode | null {
  if (root.node_id === nodeId) return root
  for (const child of root.children) {
    const found = findVisualEditNode(child, nodeId)
    if (found) return found
  }
  return null
}

/**
 * 判断未知消息是否为最小合法选择消息。
 * @param value 未受信任的 message data
 */
function isSelectionMessage(value: unknown): value is PageVisualEditSelectionMessage {
  if (!isRecord(value) || value.type !== PAGE_VISUAL_EDIT_SELECTION_EVENT || !isRecord(value.payload)) return false
  const payload = value.payload
  return typeof payload.protocolVersion === 'number'
    && typeof payload.artifactId === 'string'
    && typeof payload.nodeId === 'string'
    && (payload.bindingId === undefined || typeof payload.bindingId === 'string')
    && Array.isArray(payload.instancePath)
    && payload.instancePath.every(isInstancePathSegment)
}

/** 判断未知对象是否为带 key 或 index 的循环实例路径段。 */
function isInstancePathSegment(value: unknown): value is PageVisualEditInstancePathSegment {
  if (!isRecord(value) || typeof value.loopNodeId !== 'string') return false
  const hasKey = Object.prototype.hasOwnProperty.call(value, 'key')
  const hasIndex = Object.prototype.hasOwnProperty.call(value, 'index')
  const validKey = typeof value.key === 'string'
    || (typeof value.key === 'number' && Number.isFinite(value.key) && Number.isInteger(value.key))
  const validIndex = Number.isInteger(value.index) && Number(value.index) >= 0
  if (hasKey && !validKey) return false
  if (hasIndex && !validIndex) return false
  return (hasKey && validKey) || (hasIndex && validIndex)
}

/** 复制实例路径，避免消息对象在外部被继续修改。 */
function cloneInstancePath(path: PageVisualEditInstancePathSegment[]): PageVisualEditInstancePathSegment[] {
  return path.map((segment) => {
    if (segment.key !== undefined) {
      return {
        loopNodeId: segment.loopNodeId,
        key: segment.key,
        ...(segment.index !== undefined ? { index: segment.index } : {}),
      }
    }
    return { loopNodeId: segment.loopNodeId, index: segment.index }
  })
}

/** 从预览地址读取可信 origin，非法地址返回空字符串。 */
function resolveUrlOrigin(url: string): string {
  if (!url) return ''
  try {
    return new URL(url, window.location.href).origin
  } catch {
    return ''
  }
}

/** 判断未知值是否为普通对象。 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
