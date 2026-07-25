/** 文件功能：验证项目展示配置共享表单的字段一致性与尺寸模板事件。 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/components/preview-size/PreviewSizePresetSelect.vue', () => ({
  default: {
    emits: ['apply'],
    template: `
      <button
        type="button"
        @click="$emit('apply', {
          name: '手机竖屏',
          width: 1080,
          height: 1920,
          base_font_size: '28px',
          icon_default_stroke_width: 3
        })"
      >
        应用手机模板
      </button>
    `,
  },
}))

import ProjectPresentationFields from './ProjectPresentationFields.vue'

describe('ProjectPresentationFields', () => {
  it('应展示统一字段并将尺寸模板同步为各字段更新事件', async () => {
    const { emitted } = render(ProjectPresentationFields, {
      props: {
        pageWidth: '1920',
        pageHeight: '1080',
        baseFontSize: '20px',
        iconDefaultStrokeWidth: '2',
        showPdfExportButton: true,
        menuMode: 'preview',
      },
    })

    expect(screen.getByLabelText('页面宽度')).toHaveValue('1920')
    expect(screen.getByLabelText('页面高度')).toHaveValue('1080')
    expect(screen.getByLabelText('基础字号')).toHaveValue('20')
    expect(screen.getByLabelText('默认图标描边')).toHaveValue('2')
    expect(screen.getByRole('radio', { name: '侧边缩略图' })).toBeChecked()

    await fireEvent.click(screen.getByRole('button', { name: '应用手机模板' }))

    expect(emitted('update:pageWidth')).toEqual([['1080']])
    expect(emitted('update:pageHeight')).toEqual([['1920']])
    expect(emitted('update:baseFontSize')).toEqual([['28px']])
    expect(emitted('update:iconDefaultStrokeWidth')).toEqual([['3']])
  })
})
