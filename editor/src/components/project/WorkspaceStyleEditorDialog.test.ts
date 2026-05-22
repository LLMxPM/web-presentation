/**
 * 文件功能：验证工作空间样式编辑弹窗会提交展示配置与 Markdown 样式规范。
 */
import { render, screen, fireEvent } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

import type { WorkspaceStylePayload } from '@/api/styles'

vi.mock('@/components/theme/ThemeSelectorField.vue', () => ({
  default: {
    props: ['workspaceId', 'modelValue'],
    emits: ['update:modelValue'],
    template: '<div data-testid="theme-selector"></div>',
  },
}))

import WorkspaceStyleEditorDialog from './WorkspaceStyleEditorDialog.vue'

describe('WorkspaceStyleEditorDialog', () => {
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
  })
})
