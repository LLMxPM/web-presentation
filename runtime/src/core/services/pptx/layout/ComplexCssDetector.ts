/**
 * 文件用途：检测元素是否包含超出 PPT 原生可编辑映射范围的复杂 CSS 特效（滤镜、遮罩、混合模式、复杂变换等）。
 */

import type { MeasuredElementBox } from '@/core/services/pptx/PPTXDomConverter.types'

/**
 * 复杂 CSS 视觉检测器。
 */
export class ComplexCssDetector {
  /**
   * 判断是否应将元素作为复杂 CSS 截图降级。
   * @param element 候选元素
   * @param elementBox 元素测量盒
   * @param rootBox 页面根盒
   * @returns 是否需要局部截图
   */
  shouldScreenshotComplexElement(
    element: HTMLElement,
    elementBox: MeasuredElementBox,
    rootBox: MeasuredElementBox,
  ): boolean {
    const style = window.getComputedStyle(element)
    const pageArea = rootBox.width * rootBox.height
    const elementArea = elementBox.width * elementBox.height
    if (pageArea > 0 && elementArea / pageArea > 0.82) {
      return false
    }

    return this.isComplexImageValue(style.backgroundImage) ||
      this.isEnabledCssEffect(style.filter) ||
      this.isEnabledCssEffect((style as CSSStyleDeclaration & { backdropFilter?: string }).backdropFilter) ||
      this.isEnabledCssEffect(style.clipPath) ||
      this.isEnabledCssEffect(style.maskImage) ||
      this.isEnabledCssEffect((style as CSSStyleDeclaration & { webkitMaskImage?: string }).webkitMaskImage) ||
      this.isComplexTransform(style.transform) ||
      Boolean(style.mixBlendMode && style.mixBlendMode !== 'normal')
  }

  /**
   * 判断背景图片值是否复杂（含渐变、URL 或多层背景）。
   * @param value CSS background-image
   */
  isComplexImageValue(value: string): boolean {
    if (!value || value === 'none') {
      return false
    }
    return value.includes('gradient(') || value.includes('url(') || value.includes(',')
  }

  /**
   * 判断 CSS 特效属性是否启用。
   * @param value CSS 属性值
   */
  isEnabledCssEffect(value?: string): boolean {
    return Boolean(value && value !== 'none' && value !== 'normal')
  }

  /**
   * 判断 transform 是否超出纯位移范围。
   * @param value transform 值
   */
  isComplexTransform(value: string): boolean {
    const normalizedValue = String(value || '').trim()
    if (!normalizedValue || normalizedValue === 'none') {
      return false
    }

    if (this.isPureTranslateMatrix(normalizedValue) || this.isPureTranslateFunctionList(normalizedValue)) {
      return false
    }

    return true
  }

  /**
   * 判断 CSS matrix/matrix3d 是否只包含位移，纯位移已经体现在浏览器测量坐标里。
   */
  private isPureTranslateMatrix(value: string): boolean {
    const matrix = /^matrix\(([^)]+)\)$/.exec(value)
    if (matrix) {
      const values = this.parseTransformNumberList(matrix[1])
      return values.length === 6 &&
        this.isNearlyEqual(values[0], 1) &&
        this.isNearlyEqual(values[1], 0) &&
        this.isNearlyEqual(values[2], 0) &&
        this.isNearlyEqual(values[3], 1)
    }

    const matrix3d = /^matrix3d\(([^)]+)\)$/.exec(value)
    if (!matrix3d) {
      return false
    }

    const values = this.parseTransformNumberList(matrix3d[1])
    if (values.length !== 16) {
      return false
    }

    return values.every((item, index) => {
      if ([12, 13, 14].includes(index)) {
        return true
      }
      return this.isNearlyEqual(item, [0, 5, 10, 15].includes(index) ? 1 : 0)
    })
  }

  /**
   * 判断原始 transform 函数列表是否只由 translate 系列组成。
   */
  private isPureTranslateFunctionList(value: string): boolean {
    const functions = Array.from(value.matchAll(/([a-zA-Z0-9-]+)\(([^)]*)\)/g))
    if (functions.length === 0) {
      return false
    }

    return functions.every(match => {
      const name = match[1].toLowerCase()
      return ['translate', 'translate3d', 'translatex', 'translatey', 'translatez'].includes(name)
    })
  }

  /**
   * 解析 transform 矩阵数字列表。
   */
  private parseTransformNumberList(value: string): number[] {
    return value
      .split(/[,\s]+/)
      .map(item => Number.parseFloat(item))
      .filter(item => Number.isFinite(item))
  }

  /**
   * 浮点近似比较，避免浏览器矩阵小数误差导致误判。
   */
  private isNearlyEqual(actual: number, expected: number): boolean {
    return Math.abs(actual - expected) <= 0.0001
  }
}
