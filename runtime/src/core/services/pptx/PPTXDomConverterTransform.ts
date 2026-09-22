/**
 * 文件用途：识别并准备可原生映射的 CSS 2D 旋转，在导出期间冻结动画并恢复 DOM 样式。
 */

import type { ElementBox, PptxRotationStep, VisitContext } from './PPTXDomConverter.types'
import type { PPTXDomConverterLayout } from './PPTXDomConverterLayout'

const MATRIX_EPSILON = 0.001
const ROTATION_EPSILON_DEGREES = 0.01

interface ParsedRigidTransform {
  angle: number
  translateX: number
  translateY: number
}

export interface PreparedDomTransform {
  kind: 'none' | 'rotation' | 'unsupported'
  context: VisitContext
  restore: () => void
}

interface InlinePropertySnapshot {
  value: string
  priority: string
}

/**
 * DOM 2D transform 到 PPT 原生旋转的适配器。
 */
export class PPTXDomConverterTransform {
  constructor(private readonly layout: PPTXDomConverterLayout) {}

  /**
   * 冻结当前元素动画并准备静态 transform。
   * 支持纯位移和保持单位缩放的 2D 旋转；其余 transform 交给截图兜底。
   */
  prepare(element: HTMLElement, context: VisitContext): PreparedDomTransform {
    const snapshots = new Map<string, InlinePropertySnapshot>()
    const initialStyle = window.getComputedStyle(element)
    const hasAnimation = String(initialStyle.animationName || '').trim() !== '' && initialStyle.animationName !== 'none'
    const elementAnimations = typeof element.getAnimations === 'function' ? element.getAnimations() : null
    const shouldDisableAnimation = hasAnimation && (
      elementAnimations === null || elementAnimations.some(animation => !this.isFiniteAnimation(animation))
    )
    const hasTransition = String(initialStyle.transitionDuration || '')
      .split(',')
      .some(value => this.parseTimeMilliseconds(value) > 0)

    if (shouldDisableAnimation) {
      this.overrideInlineProperty(element, snapshots, 'animation', 'none')
    }
    if (hasTransition) {
      this.overrideInlineProperty(element, snapshots, 'transition', 'none')
    }

    const staticStyle = window.getComputedStyle(element)
    const transformValue = String(staticStyle.transform || '').trim()
    const restore = (): void => this.restoreInlineProperties(element, snapshots)
    if (!transformValue || transformValue === 'none' || this.isPureTranslate(transformValue)) {
      return { kind: 'none', context, restore }
    }

    const parsed = this.parseRigidTransform(transformValue)
    if (!parsed || element.matches('table') || Boolean(element.querySelector('table'))) {
      return { kind: 'unsupported', context, restore }
    }

    this.overrideInlineProperty(element, snapshots, 'transform', 'none')
    const box = this.layout.measureElementPixels(element)
    const origin = this.parseTransformOrigin(staticStyle.transformOrigin, box.width, box.height)
    const step: PptxRotationStep = {
      angle: parsed.angle,
      originX: this.layout.roundInch((box.left - this.layout.rootLeft() + origin.x) * this.layout.inchPerPxX()),
      originY: this.layout.roundInch((box.top - this.layout.rootTop() + origin.y) * this.layout.inchPerPxY()),
      translateX: this.layout.roundInch(parsed.translateX * this.layout.inchPerPxX()),
      translateY: this.layout.roundInch(parsed.translateY * this.layout.inchPerPxY()),
    }

    return {
      kind: 'rotation',
      context: {
        ...context,
        rotationSteps: [...(context.rotationSteps || []), step],
      },
      restore,
    }
  }

  /**
   * 将未旋转 PPT 盒模型映射到所有祖先旋转后的中心位置，并返回 PPT rotate 参数。
   */
  applyToBox(box: ElementBox, context: VisitContext): ElementBox & { rotate?: number } {
    const steps = context.rotationSteps || []
    if (steps.length === 0) {
      return box
    }

    let centerX = box.x + box.w / 2
    let centerY = box.y + box.h / 2
    for (const step of [...steps].reverse()) {
      const radians = step.angle * Math.PI / 180
      const dx = centerX - step.originX
      const dy = centerY - step.originY
      centerX = step.originX + (Math.cos(radians) * dx) - (Math.sin(radians) * dy) + step.translateX
      centerY = step.originY + (Math.sin(radians) * dx) + (Math.cos(radians) * dy) + step.translateY
    }

    const angle = steps.reduce((sum, step) => sum + step.angle, 0)
    return {
      x: this.layout.roundInch(centerX - box.w / 2),
      y: this.layout.roundInch(centerY - box.h / 2),
      w: box.w,
      h: box.h,
      ...(Math.abs(angle) >= ROTATION_EPSILON_DEGREES ? { rotate: this.normalizeAngle(angle) } : {}),
    }
  }

  /**
   * 判断 transform 是否只有位移，位移已经包含在浏览器测量位置中。
   */
  private isPureTranslate(value: string): boolean {
    const matrix = /^matrix\(([^)]+)\)$/i.exec(value)
    if (matrix) {
      const values = this.parseNumberList(matrix[1])
      return values.length === 6 &&
        this.nearlyEqual(values[0], 1) && this.nearlyEqual(values[1], 0) &&
        this.nearlyEqual(values[2], 0) && this.nearlyEqual(values[3], 1)
    }

    const matrix3d = /^matrix3d\(([^)]+)\)$/i.exec(value)
    if (matrix3d) {
      const values = this.parseNumberList(matrix3d[1])
      return values.length === 16 && values.every((item, index) => {
        if ([12, 13, 14].includes(index)) {
          return true
        }
        return this.nearlyEqual(item, [0, 5, 10, 15].includes(index) ? 1 : 0)
      })
    }

    const functions = Array.from(value.matchAll(/([a-zA-Z0-9-]+)\(([^)]*)\)/g))
    return functions.length > 0 && functions.every(match => {
      return ['translate', 'translatex', 'translatey', 'translate3d', 'translatez'].includes(match[1].toLowerCase())
    })
  }

  /**
   * 解析单位缩放、无倾斜的二维矩阵或单一 rotate 声明。
   */
  private parseRigidTransform(value: string): ParsedRigidTransform | null {
    const matrix = /^matrix\(([^)]+)\)$/i.exec(value)
    if (matrix) {
      const values = this.parseNumberList(matrix[1])
      if (values.length !== 6) {
        return null
      }
      const [a, b, c, d, translateX, translateY] = values
      const scaleX = Math.hypot(a, b)
      const scaleY = Math.hypot(c, d)
      const dot = (a * c) + (b * d)
      const determinant = (a * d) - (b * c)
      if (
        !this.nearlyEqual(scaleX, 1) ||
        !this.nearlyEqual(scaleY, 1) ||
        Math.abs(dot) > MATRIX_EPSILON ||
        determinant <= 0 ||
        !this.nearlyEqual(a, d) ||
        !this.nearlyEqual(b, -c)
      ) {
        return null
      }
      return {
        angle: Math.atan2(b, a) * 180 / Math.PI,
        translateX,
        translateY,
      }
    }

    const rotate = /^rotate(?:z)?\(\s*(-?[\d.]+)(deg|rad|turn)?\s*\)$/i.exec(value)
    if (!rotate) {
      return null
    }
    const numeric = Number.parseFloat(rotate[1])
    const unit = (rotate[2] || 'deg').toLowerCase()
    const angle = unit === 'rad' ? numeric * 180 / Math.PI : unit === 'turn' ? numeric * 360 : numeric
    return Number.isFinite(angle) ? { angle, translateX: 0, translateY: 0 } : null
  }

  /**
   * 解析 transform-origin，计算样式通常会给出 px，仍兼容百分比和关键字。
   */
  private parseTransformOrigin(value: string, width: number, height: number): { x: number, y: number } {
    const parts = String(value || '').trim().split(/\s+/)
    return {
      x: this.parseOriginPart(parts[0] || '50%', width),
      y: this.parseOriginPart(parts[1] || '50%', height),
    }
  }

  /** 解析单轴旋转原点。 */
  private parseOriginPart(value: string, size: number): number {
    const normalized = value.toLowerCase()
    if (normalized.endsWith('%')) {
      return size * Number.parseFloat(normalized) / 100
    }
    if (normalized === 'center') {
      return size / 2
    }
    if (normalized === 'left' || normalized === 'top') {
      return 0
    }
    if (normalized === 'right' || normalized === 'bottom') {
      return size
    }
    const pixels = Number.parseFloat(normalized)
    return Number.isFinite(pixels) ? this.layout.cssPxToMeasuredPx(pixels) : size / 2
  }

  /** 保存并覆盖内联属性，使用 important 确保压过动画类。 */
  private overrideInlineProperty(
    element: HTMLElement,
    snapshots: Map<string, InlinePropertySnapshot>,
    property: string,
    value: string,
  ): void {
    if (!snapshots.has(property)) {
      snapshots.set(property, {
        value: element.style.getPropertyValue(property),
        priority: element.style.getPropertyPriority(property),
      })
    }
    element.style.setProperty(property, value, 'important')
  }

  /** 恢复导出前的内联样式。 */
  private restoreInlineProperties(element: HTMLElement, snapshots: Map<string, InlinePropertySnapshot>): void {
    snapshots.forEach((snapshot, property) => {
      if (snapshot.value) {
        element.style.setProperty(property, snapshot.value, snapshot.priority)
      }
      else {
        element.style.removeProperty(property)
      }
    })
  }

  /** 解析矩阵数字列表。 */
  private parseNumberList(value: string): number[] {
    return value.split(/[,\s]+/).map(item => Number.parseFloat(item)).filter(Number.isFinite)
  }

  /** 将 CSS 秒或毫秒时间转换为毫秒。 */
  private parseTimeMilliseconds(value: string): number {
    const normalized = value.trim().toLowerCase()
    const numeric = Number.parseFloat(normalized)
    if (!Number.isFinite(numeric)) {
      return 0
    }
    return normalized.endsWith('ms') ? numeric : numeric * 1000
  }

  /** 判断 Web Animation 是否会在有限次数后结束。 */
  private isFiniteAnimation(animation: Animation): boolean {
    const timing = animation.effect?.getTiming()
    return Boolean(timing && Number.isFinite(Number(timing.iterations ?? 1)))
  }

  /** 浮点近似比较。 */
  private nearlyEqual(actual: number, expected: number): boolean {
    return Math.abs(actual - expected) <= MATRIX_EPSILON
  }

  /** 将累计角度压缩到 PPT 接受的常规范围。 */
  private normalizeAngle(value: number): number {
    const normalized = ((value % 360) + 360) % 360
    return Math.round((normalized > 180 ? normalized - 360 : normalized) * 1000) / 1000
  }
}
