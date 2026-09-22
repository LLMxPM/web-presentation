/**
 * 文件用途：验证组件预览占位配置归一化与样式构造逻辑。
 */

import { describe, expect, it } from 'vitest'

import {
  buildPlacementContainerStyle,
  buildPlacementFrameStyle,
  normalizeComponentPreviewPlacement,
} from './placement'

describe('component preview placement helpers', () => {
  it('should normalize incomplete placement options', () => {
    expect(normalizeComponentPreviewPlacement({
      width_mode: 'fixed',
      width_value: 640,
      height_mode: 'percent',
      height_value: 50,
      horizontal_align: 'end',
      padding: 24,
    })).toEqual({
      width_mode: 'fixed',
      width_value: 640,
      height_mode: 'percent',
      height_value: 50,
      horizontal_align: 'end',
      vertical_align: 'center',
      padding: 24,
    })
  })

  it('should build placement styles', () => {
    const placement = normalizeComponentPreviewPlacement({
      width_mode: 'percent',
      width_value: 75,
      height_mode: 'auto',
      horizontal_align: 'start',
      vertical_align: 'end',
      padding: 12,
    })

    expect(buildPlacementContainerStyle(placement)).toMatchObject({
      padding: '12px',
      justifyContent: 'flex-start',
      alignItems: 'flex-end',
    })
    expect(buildPlacementFrameStyle(placement)).toMatchObject({
      width: '75%',
      height: 'auto',
    })
  })
})
