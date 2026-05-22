/**
 * 文件功能：验证组件预览页面与占位选项工具的归一化逻辑。
 */

import { describe, expect, it } from 'vitest'

import {
  buildDefaultComponentPreviewOptions,
  isSamePreviewPageOptions,
  normalizeComponentPreviewOptions,
} from './preview-config'

describe('component preview options helpers', () => {
  it('should normalize incomplete values back to full preview options', () => {
    expect(normalizeComponentPreviewOptions({
      page: {
        width: 1280,
        theme_key: 'ocean',
      },
      placement: {
        width_mode: 'fixed',
        width_value: 640,
        height_mode: 'percent',
        height_value: 50,
      },
    })).toEqual({
      page: {
        width: 1280,
        height: 1080,
        base_font_size: '20px',
        icon_default_stroke_width: 2,
        theme_key: 'ocean',
        theme_config_yaml: null,
      },
      placement: {
        width_mode: 'fixed',
        width_value: 640,
        height_mode: 'percent',
        height_value: 50,
        horizontal_align: 'center',
        vertical_align: 'center',
        padding: 48,
      },
    })
  })

  it('should compare page options only', () => {
    const left = buildDefaultComponentPreviewOptions('lightblue')
    const right = buildDefaultComponentPreviewOptions('lightblue')
    right.placement.padding = 24

    expect(isSamePreviewPageOptions(left.page, right.page)).toBe(true)
    right.page.width = 1440
    expect(isSamePreviewPageOptions(left.page, right.page)).toBe(false)
  })
})
