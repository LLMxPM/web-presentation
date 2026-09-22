/**
 * 文件用途：验证 SVG 比例解析工具在 viewBox、width/height 和 DOM 测量兜底下的行为。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  extractSvgMeasureBoxes,
  formatAspectRatio,
  resolveMathJaxStackedSvgAspectRatio,
  resolveSingleSvgAspectRatio,
  resolveStackedSvgAspectRatio,
  resolveSvgBBoxAspectRatio,
} from './svg-aspect-ratio'

describe('svg-aspect-ratio', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('应优先从 viewBox 解析单个 SVG 比例', () => {
    const source = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-8 -8 216 116"></svg>'

    expect(extractSvgMeasureBoxes(source)).toEqual([{ width: 216, height: 116 }])
    expect(resolveSingleSvgAspectRatio(source)).toBeCloseTo(216 / 116)
  })

  it('缺少 viewBox 时应回退解析 width 和 height', () => {
    const source = '<svg xmlns="http://www.w3.org/2000/svg" width="400px" height="300px"></svg>'

    expect(extractSvgMeasureBoxes(source)).toEqual([{ width: 400, height: 300 }])
    expect(resolveSingleSvgAspectRatio(source)).toBeCloseTo(4 / 3)
  })

  it('多公式 SVG 应按最大宽度除以累计高度聚合', () => {
    const source = `
      <svg viewBox="0 0 200 50"></svg>
      <svg viewBox="0 0 100 50"></svg>
    `

    expect(resolveStackedSvgAspectRatio(source)).toBeCloseTo(2)
  })

  it('MathJax 多段公式应按 LatexViewer 段间距聚合', () => {
    const source = `
      <mjx-container display="true">
        <svg width="10ex" height="2ex" viewBox="0 0 1000 200"></svg>
      </mjx-container>
      <mjx-container display="true">
        <svg width="6ex" height="3ex" viewBox="0 0 600 300"></svg>
      </mjx-container>
    `

    expect(resolveMathJaxStackedSvgAspectRatio(source)).toBeCloseTo(10 / (2 + 3 + 1.75))
  })

  it('无法从 SVG 属性解析时应尝试 getBBox 兜底', () => {
    const source = '<svg><path d="M0 0h120v60H0z"></path></svg>'
    const prototype = SVGElement.prototype as SVGElement & {
      getBBox?: () => { width: number; height: number }
    }
    const descriptor = Object.getOwnPropertyDescriptor(prototype, 'getBBox')
    const getBBoxMock = vi.fn(() => ({ width: 120, height: 60 }))
    Object.defineProperty(prototype, 'getBBox', {
      configurable: true,
      value: getBBoxMock,
    })

    try {
      expect(resolveSvgBBoxAspectRatio(source)).toBe(2)
      expect(resolveSingleSvgAspectRatio(source)).toBe(2)
      expect(getBBoxMock).toHaveBeenCalledTimes(2)
    } finally {
      if (descriptor) {
        Object.defineProperty(prototype, 'getBBox', descriptor)
      } else {
        delete prototype.getBBox
      }
    }
  })

  it('应把数值比例格式化为稳定比例字符串和值', () => {
    expect(formatAspectRatio(16 / 9)).toEqual({
      aspectRatio: '16:9',
      aspectRatioValue: 1.7778,
    })
  })
})
