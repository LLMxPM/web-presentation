/**
 * 文件功能：验证样式建议组件弹窗会加载、选择并保存已发布组件。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { SuggestedComponentItem, WorkspaceComponentItem, WorkspaceStyleItem } from '@/types/api'
import WorkspaceStyleSuggestedComponentsDialog from './WorkspaceStyleSuggestedComponentsDialog.vue'

const mocked = vi.hoisted(() => ({
  getWorkspaceStyleSuggestedComponents: vi.fn(),
  updateWorkspaceStyleSuggestedComponents: vi.fn(),
  listComponents: vi.fn(),
}))

vi.mock('@/api/styles', () => ({
  getWorkspaceStyleSuggestedComponents: (...args: unknown[]) => mocked.getWorkspaceStyleSuggestedComponents(...args),
  updateWorkspaceStyleSuggestedComponents: (...args: unknown[]) => mocked.updateWorkspaceStyleSuggestedComponents(...args),
}))

vi.mock('@/api/catalog', () => ({
  listComponents: (...args: unknown[]) => mocked.listComponents(...args),
}))

describe('WorkspaceStyleSuggestedComponentsDialog', () => {
  const savedComponent: SuggestedComponentItem = {
    id: 1,
    code: 'CMP001',
    name: '指标卡片',
    import_name: 'MetricCard',
    component_type: '内容区块',
    summary: '指标展示。',
    current_version_no: 1,
  }
  const availableComponent: WorkspaceComponentItem = {
    id: 2,
    workspace_id: 1,
    workspace_name: '演示空间',
    code: 'CMP002',
    content: '<template><section /></template>',
    preview_schema: null,
    current_version_no: 1,
    draft_base_version_no: 1,
    has_unpublished_changes: false,
    published_at: '2026-06-05T00:00:00Z',
    file_type: 'vue',
    name: '趋势图表',
    import_name: 'TrendChart',
    component_type: '数据展示',
    summary: '趋势展示。',
    status: 'active',
    created_at: '2026-06-05T00:00:00Z',
    updated_at: '2026-06-05T00:00:00Z',
    created_by: 1,
    updated_by: 1,
  }
  const style: WorkspaceStyleItem = {
    id: 9,
    workspace_id: 1,
    key: 'pitch',
    name: '路演样式',
    description: null,
    page_width: 1920,
    page_height: 1080,
    base_font_size: '20px',
    icon_default_stroke_width: 2,
    show_pdf_export_button: true,
    menu_mode: 'preview',
    theme_key: null,
    style_spec_markdown: '',
    created_at: '2026-06-05T00:00:00Z',
    updated_at: '2026-06-05T00:00:00Z',
    created_by: 1,
    updated_by: 1,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mocked.getWorkspaceStyleSuggestedComponents.mockResolvedValue({ items: [savedComponent] })
    mocked.listComponents.mockResolvedValue({
      items: [{ ...availableComponent, id: 1, code: 'CMP001', name: '指标卡片', import_name: 'MetricCard', component_type: '内容区块' }, availableComponent],
      total: 2,
      page: 1,
      page_size: 100,
    })
    mocked.updateWorkspaceStyleSuggestedComponents.mockResolvedValue({
      items: [savedComponent, toSuggestedComponent(availableComponent)],
    })
  })

  it('应保存用户新增选择的建议组件', async () => {
    const { emitted } = render(WorkspaceStyleSuggestedComponentsDialog, {
      props: {
        modelValue: true,
        workspaceId: 1,
        style,
      },
    })

    expect((await screen.findAllByText('指标卡片')).length).toBeGreaterThan(0)
    await fireEvent.click(screen.getByRole('button', { name: /^趋势图表/ }))
    await fireEvent.click(screen.getByRole('button', { name: '保存组件' }))

    await waitFor(() => {
      expect(mocked.updateWorkspaceStyleSuggestedComponents).toHaveBeenCalledWith(1, 9, [1, 2])
    })
    const savedEvents = emitted('saved') as Array<[SuggestedComponentItem[]]> | undefined
    expect(savedEvents?.[0]?.[0].map(item => item.id)).toEqual([1, 2])
  })
})

/**
 * 将完整组件转换为建议组件摘要。
 * @param component 工作空间组件
 */
function toSuggestedComponent(component: WorkspaceComponentItem): SuggestedComponentItem {
  return {
    id: component.id,
    code: component.code,
    name: component.name,
    import_name: component.import_name,
    component_type: component.component_type,
    summary: component.summary,
    current_version_no: component.current_version_no,
  }
}
