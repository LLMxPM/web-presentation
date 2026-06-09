/**
 * 文件功能：验证工作空间样式编辑弹窗会提交展示配置与 Markdown 样式规范。
 */
import { render, screen, fireEvent } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { WorkspaceStylePayload } from '@/api/styles'
import type { SuggestedComponentItem, WorkspaceComponentItem, WorkspaceStyleItem } from '@/types/api'

const mocked = vi.hoisted(() => ({
  getWorkspaceStyleSuggestedComponents: vi.fn(),
  listComponents: vi.fn(),
}))

vi.mock('@/api/styles', () => ({
  getWorkspaceStyleSuggestedComponents: (...args: unknown[]) => mocked.getWorkspaceStyleSuggestedComponents(...args),
}))

vi.mock('@/api/catalog', () => ({
  listComponents: (...args: unknown[]) => mocked.listComponents(...args),
}))

vi.mock('@/components/theme/ThemeSelectorField.vue', () => ({
  default: {
    props: ['workspaceId', 'modelValue'],
    emits: ['update:modelValue'],
    template: '<div data-testid="theme-selector"></div>',
  },
}))

import WorkspaceStyleEditorDialog from './WorkspaceStyleEditorDialog.vue'

describe('WorkspaceStyleEditorDialog', () => {
  const savedComponent: SuggestedComponentItem = {
    id: 1,
    code: 'CMP001',
    name: '指标卡片',
    import_name: 'MetricCard',
    component_type: '内容组件',
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
    component_type: '原子组件',
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
    page_width: 1600,
    page_height: 900,
    base_font_size: '18px',
    icon_default_stroke_width: 3,
    show_pdf_export_button: false,
    menu_mode: 'bottom-preview',
    theme_key: null,
    style_spec_markdown: '## 版式\n- 使用强标题。',
    created_at: '2026-06-05T00:00:00Z',
    updated_at: '2026-06-05T00:00:00Z',
    created_by: 1,
    updated_by: 1,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mocked.getWorkspaceStyleSuggestedComponents.mockResolvedValue({ items: [] })
    mocked.listComponents.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    })
  })

  it('提交时应包含 Markdown 样式规范字段', async () => {
    const { emitted } = render(WorkspaceStyleEditorDialog, {
      props: {
        modelValue: true,
        workspaceId: 1,
        initialStyle: {
          key: 'pitch',
          name: '路演样式',
          page_width: 1600,
          page_height: 900,
          base_font_size: '18px',
          icon_default_stroke_width: 3,
          show_pdf_export_button: false,
          menu_mode: 'bottom-preview',
          theme_key: null,
          style_spec_markdown: '## 版式\n- 使用强标题。',
        },
      },
    })

    await fireEvent.click(screen.getByText('创建样式'))

    const saveEvents = emitted('save') as Array<[WorkspaceStylePayload]> | undefined
    const payload = saveEvents?.[0]?.[0]
    expect(payload).toMatchObject({
      key: 'pitch',
      name: '路演样式',
      page_width: 1600,
      page_height: 900,
      base_font_size: '18px',
      icon_default_stroke_width: 3,
      show_pdf_export_button: false,
      menu_mode: 'bottom-preview',
      theme_key: null,
      style_spec_markdown: '## 版式\n- 使用强标题。',
    })
    expect(payload).toHaveProperty('suggested_component_ids', [])
  })

  it('编辑样式时应加载并提交建议组件选择', async () => {
    mocked.getWorkspaceStyleSuggestedComponents.mockResolvedValue({ items: [savedComponent] })
    mocked.listComponents.mockResolvedValue({
      items: [{ ...availableComponent, id: 1, code: 'CMP001', name: '指标卡片', import_name: 'MetricCard', component_type: '内容组件' }, availableComponent],
      total: 2,
      page: 1,
      page_size: 100,
    })

    const { emitted } = render(WorkspaceStyleEditorDialog, {
      props: {
        modelValue: true,
        workspaceId: 1,
        style,
      },
    })

    await fireEvent.click(screen.getByRole('button', { name: /建议组件/ }))
    expect((await screen.findAllByText('指标卡片')).length).toBeGreaterThan(0)
    await fireEvent.click(screen.getByRole('button', { name: /^趋势图表/ }))
    await fireEvent.click(screen.getByText('保存样式'))

    expect(mocked.getWorkspaceStyleSuggestedComponents).toHaveBeenCalledWith(1, 9)
    const saveEvents = emitted('save') as Array<[WorkspaceStylePayload & { suggested_component_ids: number[] }]> | undefined
    expect(saveEvents?.[0]?.[0].suggested_component_ids).toEqual([1, 2])
  })
})
