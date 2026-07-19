/**
 * 文件功能：验证页面可视化编辑 API 的固定路径、协议版本和 camelCase 到 snake_case 序列化。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

const { postMock } = vi.hoisted(() => ({
  postMock: vi.fn(),
}))

vi.mock('@/api/http', () => ({
  http: {
    post: postMock,
  },
}))

import {
  applyPageVisualEditOperations,
  createPageVisualEditPreviewArtifact,
} from '@/api/page-visual-edit'

describe('page visual edit api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('应按页面版本创建可视化编辑态 artifact', async () => {
    const response = { artifact_id: 'artifact-1', visual_edit: { protocol_version: 1 } }
    postMock.mockResolvedValueOnce({ data: response })

    const result = await createPageVisualEditPreviewArtifact(42, { base_version_no: 7 })

    expect(postMock).toHaveBeenCalledWith('/pages/42/visual-edit/preview-artifacts', {
      protocol_version: 1,
      base_version_no: 7,
    })
    expect(result).toBe(response)
  })

  it('应批量序列化绑定与结构操作为 Backend snake_case 协议', async () => {
    const response = { page_id: 42, current_version_no: 8 }
    postMock.mockResolvedValueOnce({ data: response })
    const operations = [
      {
        type: 'set_value' as const,
        nodeId: 'node-title',
        bindingId: 'binding-title',
        instancePath: [{ loopNodeId: 'loop-items', key: 'b', index: 1 }],
        value: '新标题',
      },
      {
        type: 'set_rich_text' as const,
        nodeId: 'node-paragraph',
        bindingId: 'binding-rich',
        instancePath: [],
        html: '正文<br><strong>重点</strong>',
      },
      {
        type: 'set_tailwind_tokens' as const,
        nodeId: 'node-card',
        bindingId: 'binding-class',
        instancePath: [],
        changes: [
          { group: 'radius', className: 'rounded-lg' },
          { group: 'padding', className: 'p-8' },
          { group: 'background' },
        ],
      },
      {
        type: 'duplicate_node' as const,
        nodeId: 'node-card',
        instancePath: [{ loopNodeId: 'loop-items', key: 'b', index: 1 }],
      },
      {
        type: 'delete_node' as const,
        nodeId: 'node-section',
        instancePath: [],
      },
    ]

    const result = await applyPageVisualEditOperations(42, {
      artifact_id: 'artifact-1',
      base_version_no: 7,
      source_hash: 'a'.repeat(64),
      operations,
      change_note: '可视化编辑',
    })

    expect(postMock).toHaveBeenCalledWith('/pages/42/visual-edit/apply', {
      protocol_version: 1,
      artifact_id: 'artifact-1',
      base_version_no: 7,
      source_hash: 'a'.repeat(64),
      operations: [
        {
          type: 'set_value',
          node_id: 'node-title',
          binding_id: 'binding-title',
          instance_path: [{ loop_node_id: 'loop-items', key: 'b', index: 1 }],
          value: '新标题',
        },
        {
          type: 'set_rich_text',
          node_id: 'node-paragraph',
          binding_id: 'binding-rich',
          instance_path: [],
          html: '正文<br><strong>重点</strong>',
        },
        {
          type: 'set_tailwind_tokens',
          node_id: 'node-card',
          binding_id: 'binding-class',
          instance_path: [],
          changes: [
            { group: 'radius', class_name: 'rounded-lg' },
            { group: 'padding', class_name: 'p-8' },
            { group: 'background', class_name: null },
          ],
        },
        {
          type: 'duplicate_node',
          node_id: 'node-card',
          instance_path: [{ loop_node_id: 'loop-items', key: 'b', index: 1 }],
        },
        {
          type: 'delete_node',
          node_id: 'node-section',
          instance_path: [],
        },
      ],
      change_note: '可视化编辑',
    })
    expect(result).toBe(response)
    expect(operations[2]?.changes).toEqual([
      { group: 'radius', className: 'rounded-lg' },
      { group: 'padding', className: 'p-8' },
      { group: 'background' },
    ])
  })

  it('仅使用 index 定位实例时应保留 index 且不补入 key', async () => {
    postMock.mockResolvedValueOnce({ data: {} })

    await applyPageVisualEditOperations(9, {
      artifact_id: 'artifact-2',
      base_version_no: 3,
      source_hash: 'a'.repeat(64),
      operations: [{
        type: 'set_value',
        nodeId: 'node-static',
        bindingId: 'binding-static',
        instancePath: [{ loopNodeId: 'loop-items', index: 2 }],
        value: 12,
      }],
      change_note: null,
    })

    expect(postMock.mock.calls[0]?.[1].operations[0].instance_path).toEqual([
      { loop_node_id: 'loop-items', index: 2 },
    ])
  })

  it('应把 set_json 的 sourceId 转成 Backend snake_case 并保留结构化值', async () => {
    postMock.mockResolvedValueOnce({ data: {} })

    await applyPageVisualEditOperations(9, {
      artifact_id: 'artifact-json',
      base_version_no: 3,
      source_hash: 'a'.repeat(64),
      operations: [{ type: 'set_json', sourceId: 'source_benefits', value: ['甲', { label: '乙' }] }],
      change_note: '编辑数据',
    })

    expect(postMock.mock.calls[0]?.[1].operations).toEqual([{
      type: 'set_json',
      source_id: 'source_benefits',
      value: ['甲', { label: '乙' }],
    }])
  })
})
