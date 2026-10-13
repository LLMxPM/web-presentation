/**
 * 文件用途：检测元素是否包含超出 PPT 原生可编辑映射范围的复杂 CSS 特效（滤镜、遮罩、混合模式、复杂变换、圆角裁切、复杂阴影等）。
 */

import type { MeasuredElementBox } from '@/core/services/pptx/PPTXDomConverter.types'
import { BoxShadowParser } from '@/core/services/pptx/style/BoxShadowParser'
import { CssColorParser } from '@/core/services/pptx/style/CssColorParser'

/**
 * 复杂 CSS 视觉检测器。
 */
export class ComplexCssDetector {
  private readonly boxShadowParser = new BoxShadowParser()
  private readonly colorParser = new CssColorParser()

  /**
   * 判断是否应将元素作为复杂 CSS 截图降级。
   * 移除历史 0.82 面积无报告豁免，严格按视觉能力决定降级。
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
    const style = element.ownerDocument.defaultView?.getComputedStyle(element) ?? window.getComputedStyle(element)

    return this.isComplexImageValue(style.backgroundImage) ||
      this.isEnabledCssEffect(style.filter) ||
      this.isEnabledCssEffect((style as CSSStyleDeclaration & { backdropFilter?: string }).backdropFilter) ||
      this.isEnabledCssEffect(style.clipPath) ||
      this.isEnabledCssEffect(style.maskImage) ||
      this.isEnabledCssEffect((style as CSSStyleDeclaration & { webkitMaskImage?: string }).webkitMaskImage) ||
      this.isComplexTransform(style.transform) ||
      Boolean(style.mixBlendMode && style.mixBlendMode !== 'normal') ||
      this.isComplexBoxShadow(style.boxShadow, element) ||
      this.isRoundedClipping(element, style)
  }

  /**
   * 判断背景图片值是否复杂（含非原生线性渐变、URL 或多层背景）。
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
   * 判断 box-shadow 是否属于多层、内阴影或带 spread 等无法原生映射为 PPT 单层外阴影的复杂阴影。
   * @param value CSS box-shadow
   * @param element 宿主元素
   */
  isComplexBoxShadow(value: string, element: HTMLElement): boolean {
    if (!value || value === 'none') {
      return false
    }
    const result = this.boxShadowParser.parse(value, element, this.colorParser, px => px * 0.75)
    return result.kind === 'complex'
  }

  /**
   * 判断元素是否拥有圆角遮罩裁切（overflow: hidden 且 borderRadius > 0）。
   * @param element 宿主元素
   * @param style 计算样式
   */
  isRoundedClipping(element: HTMLElement, style: CSSStyleDeclaration): boolean {
    const overflow = String(style.overflow || '').trim()
    const overflowX = String(style.overflowX || '').trim()
    const overflowY = String(style.overflowY || '').trim()
    const isClipping = ['hidden', 'clip'].includes(overflow) ||
      ['hidden', 'clip'].includes(overflowX) ||
      ['hidden', 'clip'].includes(overflowY)
    if (!isClipping) {
      return false
    }
    const borderRadius = Number.parseFloat(style.borderRadius || '0')
    return Number.isFinite(borderRadius) && borderRadius > 0 && element.children.length > 0
  }

  /**
   * 判断 transform 是否超出可原生表达的纯位移、正值等比缩放或 2D 刚性旋转范围。
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

    if (this.isSupportedScaleOrRotate(normalizedValue)) {
      return false
    }

    return true
  }

  /**
   * 判断 transform 是否为支持的正值等比缩放、2D 旋转或其简单组合。
   */
  private isSupportedScaleOrRotate(value: string): boolean {
    // 检查 matrix(a, b, c, d, tx, ty)
    const matrix = /^matrix\(([^)]+)\)$/i.exec(value)
    if (matrix) {
      const values = this.parseTransformNumberList(matrix[1])
      if (values.length !== 6) {
        return false
      }
      const [a, b, c, d] = values
      const scaleX = Math.hypot(a, b)
      const scaleY = Math.hypot(c, d)
      const dot = (a * c) + (b * d)
      const determinant = (a * d) - (b * c)
      const isPositiveUniform = scaleX > 0.001 && Math.abs(scaleX - scaleY) <= 0.002
      const isOrthogonal = Math.abs(dot) <= 0.002 && determinant > 0
      return isPositiveUniform && isOrthogonal
    }

    // 检查函数列表（只由 translate, rotate, 正值等比 scale 组成）
    const functions = Array.from(value.matchAll(/([a-zA-Z0-9-]+)\(([^)]*)\)/g))
    if (functions.length === 0) {
      return false
    }

    return functions.every(match => {
      const name = match[1].toLowerCase()
      const args = match[2].trim()
      if (['translate', 'translate3d', 'translatex', 'translatey', 'translatez'].includes(name)) {
        return true
      }
      if (['rotate', 'rotatez'].includes(name)) {
        return true
      }
      if (name === 'scale') {
        const parts = args.split(/[,\s]+/).map(item => Number.parseFloat(item)).filter(Number.isFinite)
        if (parts.length === 1) {
          return parts[0] > 0.001
        }
        if (parts.length >= 2) {
          return parts[0] > 0.001 && Math.abs(parts[0] - parts[1]) <= 0.001
        }
        return false
      }
      return false
    })
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
