/**
 * 文件功能：校验页面可视化编辑协议版本、公开 API 路径和循环实例定位字段在三端保持一致。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const backendSchemaSource = readFileSync(
  resolve(process.cwd(), 'backend/app/schemas/page_visual_edit.py'),
  'utf-8',
)
const backendManifestSchemaSource = readFileSync(
  resolve(process.cwd(), 'backend/app/schemas/page_visual_edit_manifest.py'),
  'utf-8',
)
const backendRouteSource = readFileSync(
  resolve(process.cwd(), 'backend/app/api/routes/page_visual_edit.py'),
  'utf-8',
)
const editorApiSource = readFileSync(resolve(process.cwd(), 'editor/src/api/page-visual-edit.ts'), 'utf-8')
const editorTypeSource = readFileSync(resolve(process.cwd(), 'editor/src/types/page-visual-edit.ts'), 'utf-8')
const runtimeProtocolSource = readFileSync(
  resolve(process.cwd(), 'runtime/src/core/visual-edit/protocol.ts'),
  'utf-8',
)
const runtimePluginSource = readFileSync(
  resolve(process.cwd(), 'runtime/src/core/plugins/runtime-visual-edit.ts'),
  'utf-8',
)
const runtimeSelectionBridgeSource = readFileSync(
  resolve(process.cwd(), 'runtime/src/core/visual-edit/browser/selection-bridge.ts'),
  'utf-8',
)
const runtimePreviewContractSource = readFileSync(
  resolve(process.cwd(), 'runtime/src/core/shared/runtime-preview.ts'),
  'utf-8',
)
const contractDoc = readFileSync(
  resolve(process.cwd(), 'docs/developer/runtime-integration/page-visual-edit.md'),
  'utf-8',
)

describe('page visual edit protocol contract', () => {
  it('Backend、Editor 与 Runtime 应共同使用首发协议 v1', () => {
    expect(backendManifestSchemaSource).toContain('PAGE_VISUAL_EDIT_PROTOCOL_VERSION = 1')
    expect(editorTypeSource).toContain('PAGE_VISUAL_EDIT_PROTOCOL_VERSION = 1 as const')
    expect(runtimeProtocolSource).toContain('PAGE_VISUAL_EDIT_PROTOCOL_VERSION = 1 as const')
  })

  it('Editor 与开发契约应使用固定的 artifact 创建和批量保存路径', () => {
    expect(editorApiSource).toContain('/visual-edit/preview-artifacts')
    expect(editorApiSource).toContain('/visual-edit/apply')
    expect(backendRouteSource).toContain('/{page_id}/visual-edit/preview-artifacts')
    expect(backendRouteSource).toContain('/{page_id}/visual-edit/apply')
    expect(runtimePluginSource).toContain('/__runtime_internal/v1/visual-edit/analyze')
    expect(runtimePluginSource).toContain('/__runtime_internal/v1/visual-edit/apply')
    expect(contractDoc).toContain('POST /pages/{page_id}/visual-edit/preview-artifacts')
    expect(contractDoc).toContain('POST /pages/{page_id}/visual-edit/apply')
    expect(contractDoc).toContain('PAGE_VISUAL_EDIT_RICH_TEXT_STYLE_LOCKED')
  })

  it('循环实例定位应统一使用 loopNodeId/loop_node_id，并限制为稳定 key 或 index', () => {
    expect(runtimeProtocolSource).toContain('loopNodeId: string')
    expect(editorTypeSource).toContain('loopNodeId: string')
    expect(editorApiSource).toContain('loop_node_id: segment.loopNodeId')
    expect(backendSchemaSource).toContain('loop_node_id: VisualEditIdentifier')
    expect(contractDoc).toContain('"loop_node_id": "for_items"')
  })

  it('操作类型应包含绑定写入与节点复制删除', () => {
    for (const source of [backendSchemaSource, editorTypeSource, runtimeProtocolSource]) {
      expect(source).toContain('set_value')
      expect(source).toContain('set_json')
      expect(source).toContain('set_tailwind_tokens')
      expect(source).toContain('set_rich_text')
      expect(source).toContain('duplicate_node')
      expect(source).toContain('delete_node')
    }
    expect(editorTypeSource).toContain('changes: PageVisualEditTailwindTokenChange[]')
    expect(runtimeProtocolSource).toContain('changes: VisualEditTailwindTokenChange[]')
    expect(backendManifestSchemaSource).toContain('PageVisualEditTemplateActions')
    expect(editorTypeSource).toContain('loop_item_actions')
    expect(runtimeProtocolSource).toContain('loopItemActions')
    expect(backendManifestSchemaSource).toContain('json_sources')
    expect(editorTypeSource).toContain('json_sources')
    expect(runtimeProtocolSource).toContain('jsonSources')
    expect(editorApiSource).toContain('source_id: operation.sourceId')
  })

  it('Tailwind 目录应由 Runtime 以整数版本 1 下发，Editor 不提供任意 class 协议', () => {
    expect(backendManifestSchemaSource).toContain('version: Literal[1]')
    expect(editorTypeSource).toContain('version: PageVisualEditProtocolVersion')
    expect(runtimeProtocolSource).toContain('version: 1')
    expect(contractDoc).toContain('"tailwind_catalog"')
    expect(contractDoc).toContain('Editor 不提供任意 class 文本框')
  })

  it('编辑态 artifact 应使用独立类型并携带真实组件版本 schema', () => {
    expect(runtimePreviewContractSource).toContain("'page_visual_edit_preview'")
    expect(backendSchemaSource).toContain('component_schemas: dict[')
    expect(editorTypeSource).toContain('component_schemas: Record<string, PageVisualEditComponentSchema>')
    expect(contractDoc).toContain('`component_schemas`')
  })

  it('Runtime 与 Editor 双向选区消息应使用固定外壳，且不下发实时属性覆盖', () => {
    for (const source of [editorTypeSource, runtimeProtocolSource]) {
      expect(source).toContain("'page-visual-edit:selection'")
      expect(source).toContain("'page-visual-edit:select-node'")
      expect(source).toContain('protocolVersion')
      expect(source).toContain('artifactId')
      expect(source).toContain('instancePath')
    }
    expect(runtimeSelectionBridgeSource).toContain('context.postMessageTarget.postMessage(selection, context.parentOrigin)')
    expect(contractDoc).toContain('编辑态 iframe 上报画布点击选择，同时接收 Editor 图层树的节点定位')
  })
})
