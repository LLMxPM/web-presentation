/**
 * 文件用途：验证资源预览背景查询参数的归一化与渲染器颜色映射。
 */
import { describe, expect, it } from 'vitest'

import {
  normalizeAssetPreviewBackground,
  resolveAssetPreviewRendererBackground,
} from './asset-preview-background'

describe('asset preview background', () => {
  it('应识别浅色、深色和棋盘格，并对非法值回退到浅色', () => {
    expect(normalizeAssetPreviewBackground('light')).toBe('light')
    expect(normalizeAssetPreviewBackground('dark')).toBe('dark')
    expect(normalizeAssetPreviewBackground(['checker'])).toBe('checker')
    expect(normalizeAssetPreviewBackground('unknown')).toBe('light')
  })

  it('棋盘格应让渲染器透明，纯色模式应返回对应颜色', () => {
    expect(resolveAssetPreviewRendererBackground('light')).toBe('#ffffff')
    expect(resolveAssetPreviewRendererBackground('dark')).toBe('#0f172a')
    expect(resolveAssetPreviewRendererBackground('checker')).toBe('transparent')
  })
})
