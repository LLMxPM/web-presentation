/**
 * 文件功能：验证可视化编辑会话的 artifact 生命周期、受信任选区消息与失败保留草稿语义。
 */

import { defineComponent, h, nextTick } from 'vue'
import { render, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PageVisualEditPreviewArtifactResponse } from '@/types/page-visual-edit'

const { applyMock, createMock } = vi.hoisted(() => ({
  applyMock: vi.fn(),
  createMock: vi.fn(),
}))

vi.mock('@/api/page-visual-edit', () => ({
  applyPageVisualEditOperations: (...args: unknown[]) => applyMock(...args),
  createPageVisualEditPreviewArtifact: (...args: unknown[]) => createMock(...args),
}))

import { usePageVisualEditSession } from '@/composables/usePageVisualEditSession'

describe('usePageVisualEditSession', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('只接受同 iframe、origin、artifact 和协议的 payload 选择消息', async () => {
    createMock.mockResolvedValue(createArtifact('artifact-1', 3))
    let session: ReturnType<typeof usePageVisualEditSession> | undefined
    const Host = defineComponent({
      setup() {
        session = usePageVisualEditSession()
        return () => h('iframe', { ref: session.previewFrameRef, title: 'visual-frame' })
      },
    })
    render(Host)
    await session!.analyze(9, 3)
    await nextTick()
    const frameWindow = session!.previewFrameRef.value?.contentWindow
    expect(frameWindow).toBeTruthy()

    const validMessage = {
      type: 'page-visual-edit:selection',
      payload: {
        protocolVersion: 1,
        artifactId: 'artifact-1',
        nodeId: 'node-card',
        bindingId: 'binding-title',
        instancePath: [{ loopNodeId: 'node-card', key: 'second', index: 1 }],
      },
    }
    window.dispatchEvent(new MessageEvent('message', {
      data: { ...validMessage, payload: { ...validMessage.payload, artifactId: 'other' } },
      origin: 'http://runtime.local',
      source: frameWindow,
    }))
    expect(session!.selectedNodeId.value).toBe('root')

    for (const invalidKey of [Number.NaN, Number.POSITIVE_INFINITY, 1.5]) {
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          ...validMessage,
          payload: {
            ...validMessage.payload,
            instancePath: [{ loopNodeId: 'node-card', key: invalidKey, index: 1 }],
          },
        },
        origin: 'http://runtime.local',
        source: frameWindow,
      }))
      expect(session!.selectedNodeId.value).toBe('root')
    }

    window.dispatchEvent(new MessageEvent('message', {
      data: validMessage,
      origin: 'http://runtime.local',
      source: frameWindow,
    }))

    expect(session!.selectedNodeId.value).toBe('node-card')
    expect(session!.selectedBindingId.value).toBe('binding-title')
    expect(session!.selectedInstancePath.value).toEqual([
      { loopNodeId: 'node-card', key: 'second', index: 1 },
    ])
  })

  it('apply 失败保留草稿，成功后清空并按新版本重建 artifact', async () => {
    createMock
      .mockResolvedValueOnce(createArtifact('artifact-1', 3))
      .mockResolvedValueOnce(createArtifact('artifact-2', 4))
    applyMock
      .mockRejectedValueOnce(new Error('conflict'))
      .mockResolvedValueOnce({
        protocol_version: 1,
        success: true,
        page_id: 9,
        previous_version_no: 3,
        current_version_no: 4,
        source_hash: 'b'.repeat(64),
        operations_applied: 1,
        canonical_diff: 'diff',
        diagnostics: [],
        refresh_required: true,
      })
    let session: ReturnType<typeof usePageVisualEditSession> | undefined
    render(defineComponent({
      setup() {
        session = usePageVisualEditSession()
        return () => h('div')
      },
    }))
    await session!.analyze(9, 3)
    session!.setValue({ nodeId: 'node-card', bindingId: 'binding-title', instancePath: [] }, '新标题', '原标题')

    expect(await session!.save(9)).toBeNull()
    expect(session!.pendingCount.value).toBe(1)

    const result = await session!.save(9)

    expect(result?.current_version_no).toBe(4)
    expect(session!.pendingCount.value).toBe(0)
    expect(session!.artifact.value?.artifact_id).toBe('artifact-2')
    expect(createMock).toHaveBeenLastCalledWith(9, { base_version_no: 4 })
    expect(applyMock).toHaveBeenLastCalledWith(9, expect.objectContaining({
      artifact_id: 'artifact-1',
      operations: [expect.objectContaining({ type: 'set_value', value: '新标题' })],
    }))
  })
})

/** 创建包含静态文本与循环节点的严格 Manifest fixture。 */
function createArtifact(artifactId: string, baseVersionNo: number): PageVisualEditPreviewArtifactResponse {
  const sourceHash = artifactId === 'artifact-1' ? 'a'.repeat(64) : 'b'.repeat(64)
  return {
    preview_url: 'http://runtime.local/__preview/visual',
    artifact_id: artifactId,
    preview_kind: 'page',
    entry_descriptor: { entry_type: 'module', module_path: 'src/views/Page.vue' },
    viewport_width: 1600,
    viewport_height: 900,
    visual_edit: {
      protocol_version: 1,
      page_id: 9,
      base_version_no: baseVersionNo,
      source_hash: sourceHash,
      module_path: 'src/views/Page.vue',
      component_schemas: {},
      warnings: [],
      manifest: {
        protocol_version: 1,
        module_path: 'src/views/Page.vue',
        source_hash: sourceHash,
        diagnostics: [],
        tailwind_catalog: { version: 1, groups: [] },
        root: {
          node_id: 'root',
          kind: 'root',
          tag: 'template',
          source_range: { start: 0, end: 100 },
          bindings: [],
          children: [{
            node_id: 'node-card',
            kind: 'element',
            tag: 'article',
            source_range: { start: 10, end: 90 },
            loop_context: {
              loop_node_id: 'node-card',
              source_expression: 'items',
              source_binding: 'items',
              item_alias: 'item',
              key_expression: 'item.id',
              key_member: 'id',
              editable: true,
            },
            bindings: [{
              binding_id: 'binding-title',
              node_id: 'node-card',
              kind: 'text',
              value_type: 'string',
              value: '原标题',
              source_range: { start: 20, end: 30 },
              editable: true,
              source: { kind: 'template-literal' },
            }],
            children: [],
          }],
        },
      },
    },
  }
}
