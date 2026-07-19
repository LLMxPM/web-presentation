/**
 * 文件功能：验证三栏可视化面板的非实时草稿保存，以及父页面版本同步时不重复创建 artifact。
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PageVisualEditPreviewArtifactResponse } from '@/types/page-visual-edit'

const { applyMock, confirmMock, createMock } = vi.hoisted(() => ({
  applyMock: vi.fn(),
  confirmMock: vi.fn().mockResolvedValue(true),
  createMock: vi.fn(),
}))

vi.mock('@/api/page-visual-edit', () => ({
  applyPageVisualEditOperations: (...args: unknown[]) => applyMock(...args),
  createPageVisualEditPreviewArtifact: (...args: unknown[]) => createMock(...args),
}))

vi.mock('@/utils/message', () => ({
  createConfirm: (...args: unknown[]) => confirmMock(...args),
  Message: {
    info: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

import PageVisualEditPanel from '@/components/page-detail/visual-edit/PageVisualEditPanel.vue'

describe('PageVisualEditPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('属性草稿不改 iframe，保存后刷新一次且父版本更新不重复分析', async () => {
    createMock
      .mockResolvedValueOnce(createArtifact('artifact-1', 1, '原标题'))
      .mockResolvedValueOnce(createArtifact('artifact-2', 2, '新标题'))
    applyMock.mockResolvedValue({
      protocol_version: 1,
      success: true,
      page_id: 31,
      previous_version_no: 1,
      current_version_no: 2,
      source_hash: 'b'.repeat(64),
      operations_applied: 1,
      canonical_diff: 'diff',
      diagnostics: [],
      refresh_required: true,
    })
    const rendered = render(PageVisualEditPanel, {
      props: { pageId: 31, baseVersionNo: 1, pageTitle: '测试页面' },
    })

    const iframe = await screen.findByTitle('测试页面 可视化编辑画布')
    expect(createMock).toHaveBeenCalledTimes(1)
    await fireEvent.click(screen.getByRole('button', { name: /Card/ }))
    const textarea = await screen.findByRole('textbox')
    expect(iframe).toHaveAttribute('src', 'http://runtime.local/artifact-1')

    await fireEvent.update(textarea, '新标题')
    expect(screen.getByText('1 项待保存')).toBeInTheDocument()
    expect(iframe).toHaveAttribute('src', 'http://runtime.local/artifact-1')
    await fireEvent.click(screen.getByRole('button', { name: '保存并刷新' }))

    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(2))
    expect(applyMock).toHaveBeenCalledWith(31, expect.objectContaining({
      artifact_id: 'artifact-1',
      operations: [expect.objectContaining({ value: '新标题' })],
    }))
    expect(screen.getByTitle('测试页面 可视化编辑画布')).toHaveAttribute('src', 'http://runtime.local/artifact-2')

    await rendered.rerender({ pageId: 31, baseVersionNo: 2, pageTitle: '测试页面' })
    await Promise.resolve()
    expect(createMock).toHaveBeenCalledTimes(2)
  })

  it('删除结构应二次确认、清理内部草稿、禁用属性编辑并允许撤销', async () => {
    createMock.mockResolvedValue(createArtifact('artifact-delete', 1, '原标题'))
    render(PageVisualEditPanel, {
      props: { pageId: 31, baseVersionNo: 1, pageTitle: '测试页面' },
    })

    await screen.findByTitle('测试页面 可视化编辑画布')
    await fireEvent.click(screen.getByRole('button', { name: /Card/ }))
    const textarea = await screen.findByRole('textbox')
    await fireEvent.update(textarea, '待删除修改')
    await fireEvent.click(screen.getByRole('button', { name: '删除组件' }))

    await waitFor(() => expect(confirmMock).toHaveBeenCalledWith(
      '删除组件，并放弃其中 1 项待保存修改，是否继续？',
      '删除组件',
    ))
    expect(screen.getByText('1 项待保存')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).toBeNull()

    await fireEvent.click(screen.getByRole('button', { name: '撤销' }))
    expect(screen.queryByText('1 项待保存')).toBeNull()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })
})

/** 创建面板测试用可视化 artifact。 */
function createArtifact(artifactId: string, versionNo: number, title: string): PageVisualEditPreviewArtifactResponse {
  const sourceHash = versionNo === 1 ? 'a'.repeat(64) : 'b'.repeat(64)
  return {
    preview_url: `http://runtime.local/${artifactId}`,
    artifact_id: artifactId,
    preview_kind: 'page',
    entry_descriptor: { entry_type: 'module', module_path: 'src/views/Test.vue' },
    viewport_width: 1600,
    viewport_height: 900,
    visual_edit: {
      protocol_version: 1,
      page_id: 31,
      base_version_no: versionNo,
      source_hash: sourceHash,
      module_path: 'src/views/Test.vue',
      component_schemas: {},
      warnings: [],
      manifest: {
        protocol_version: 1,
        module_path: 'src/views/Test.vue',
        source_hash: sourceHash,
        diagnostics: [],
        tailwind_catalog: { version: 1, groups: [] },
        root: {
          node_id: 'root',
          kind: 'root',
          tag: 'template',
          source_range: { start: 0, end: 100 },
          template_actions: { can_duplicate: false, can_delete: false, readonly_reason: 'STRUCTURE_ROOT_UNSUPPORTED' },
          bindings: [],
          children: [{
            node_id: 'node-card',
            kind: 'component',
            tag: 'Card',
            source_range: { start: 10, end: 90 },
            template_actions: { can_duplicate: true, can_delete: true },
            bindings: [{
              binding_id: 'binding-title',
              node_id: 'node-card',
              kind: 'text',
              value_type: 'string',
              value: title,
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
