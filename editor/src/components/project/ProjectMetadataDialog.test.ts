/**
 * 文件功能：验证项目元数据弹窗在新建项目时要求选择主题。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/components/theme/ThemeSelectorField.vue', () => ({
  default: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: `
      <div data-testid="theme-selector">
        <button type="button" @click="$emit('update:modelValue', 'default')">选择默认主题</button>
        <span>{{ modelValue || '未选择主题' }}</span>
      </div>
    `,
  },
}))

vi.mock('@/components/preview-size/PreviewSizePresetSelect.vue', () => ({
  default: {
    template: '<div data-testid="preview-size-preset-select"></div>',
  },
}))

vi.mock('@/components/project/WorkspaceStyleApplyField.vue', () => ({
  default: {
    emits: ['apply'],
    template: `
      <div data-testid="workspace-style-apply-field">
        <button
          type="button"
          @click="$emit('apply', {
            page_width: 1600,
            page_height: 900,
            base_font_size: '18px',
            icon_default_stroke_width: 2,
            show_pdf_export_button: false,
            menu_mode: 'bottom-preview',
            theme_key: 'style-theme',
            style_spec_markdown: '## 示例样式'
          })"
        >
          应用示例样式
        </button>
      </div>
    `,
  },
}))

import ProjectMetadataDialog from './ProjectMetadataDialog.vue'

describe('ProjectMetadataDialog', () => {
  it('未选择主题时应阻止新建项目提交', async () => {
    const { emitted } = renderDialog()

    await fireEvent.update(screen.getByPlaceholderText('起一个具有辨识度的名称'), '客户路演')
    await fireEvent.click(screen.getByRole('button', { name: '立即创建' }))

    expect(screen.getByText('请选择项目主题')).toBeInTheDocument()
    expect(emitted('submit')).toBeUndefined()
  })

  it('选择主题后应把主题 key 写入新建项目提交参数', async () => {
    const { emitted } = renderDialog()

    await fireEvent.update(screen.getByPlaceholderText('起一个具有辨识度的名称'), '客户路演')
    await fireEvent.click(screen.getByRole('button', { name: '选择默认主题' }))
    await fireEvent.click(screen.getByRole('button', { name: '立即创建' }))

    const submitEvents = emitted('submit') as Array<[Record<string, unknown>]> | undefined
    expect(submitEvents?.[0]?.[0]).toMatchObject({
      name: '客户路演',
      theme_key: 'default',
    })
  })

  it('应用工作空间样式时应同步填充项目主题', async () => {
    const { emitted } = renderDialog()

    await fireEvent.update(screen.getByPlaceholderText('起一个具有辨识度的名称'), '客户路演')
    await fireEvent.click(screen.getByRole('button', { name: '应用示例样式' }))
    await fireEvent.click(screen.getByRole('button', { name: '立即创建' }))

    const submitEvents = emitted('submit') as Array<[Record<string, unknown>]> | undefined
    expect(submitEvents?.[0]?.[0]).toMatchObject({
      name: '客户路演',
      page_width: 1600,
      page_height: 900,
      theme_key: 'style-theme',
      style_spec_markdown: '## 示例样式',
    })
  })
})

function renderDialog() {
  return render(ProjectMetadataDialog, {
    props: {
      modelValue: true,
      workspaceId: 1,
    },
  })
}
