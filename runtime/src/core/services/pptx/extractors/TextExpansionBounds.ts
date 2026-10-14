/** 文件用途：根据真实容器内容边界和同高度相邻对象限制文本扩宽，保留原有位置及越界，不挤占其他内容。 */
import { getComputedStyle, isSVGElement, isTextNode } from '../dom/PPTXDomEnvironment'
import type { ElementBox } from '../PPTXDomConverter.types'
import type { PPTXDomConverterLayout } from '../PPTXDomConverterLayout'
import { hasExplicitTextWidthConstraint } from './TextWidthConstraints'

export interface TextExpansionBounds { left: number; right: number }
const EPSILON = 0.0001

/** 判断原框是否已经超出可用边界；允许测量取整误差，已有越界不通过扩宽或借位修正。 */
export function isOutsideTextExpansionBounds(box: ElementBox, bounds: TextExpansionBounds): boolean {
  return box.x < bounds.left - EPSILON || box.x + box.w > bounds.right + EPSILON
}

/** 从页面内的实际布局提取左右扩宽边界，不依赖固定模板或作者提供的换行意图。 */
export class TextExpansionBoundsResolver {
  constructor(private readonly layout: PPTXDomConverterLayout) {}

  /** 扫描祖先内容区及直接兄弟；已有越界或重叠不修正，只约束本轮新增宽度。 */
  resolve(anchor: Node, box: ElementBox, slideWidthIn = Infinity): TextExpansionBounds {
    const bounds = { left: 0, right: slideWidthIn }
    const root = this.layout.rootElement()
    for (let branch = anchor; branch !== root && branch.parentElement; branch = branch.parentElement) {
      const parent = branch.parentElement
      if (parent === root || this.isBoundedContainer(parent)) {
        const parentBox = this.layout.getPptxBox(parent)
        if (parentBox) {
          const style = getComputedStyle(parent)
          const padding = this.layout.resolveElementPaddingPixels(parent, style)
          const leftInset = padding.left + this.layout.parseCssPixel(style.borderLeftWidth)
          const rightInset = padding.right + this.layout.parseCssPixel(style.borderRightWidth)
          const toInch = (value: number) => this.layout.cssPxToMeasuredPx(value) * this.layout.inchPerPxX()
          bounds.left = Math.max(bounds.left, parentBox.x + toInch(leftInset))
          bounds.right = Math.min(bounds.right, parentBox.x + parentBox.w - toInch(rightInset))
        }
      }
      for (const sibling of parent.childNodes) {
        if (sibling === branch) continue
        for (const siblingBox of this.measureObstacles(sibling)) this.limitByObstacle(bounds, box, siblingBox)
      }
    }
    return bounds
  }

  /** 内容驱动的透明 inline/横向 Flex 子项可使用外层空白；网格单元、显式尺寸和可见卡片则限制边界。 */
  private isBoundedContainer(element: HTMLElement): boolean {
    const style = getComputedStyle(element)
    const clipsHorizontalContent = ['hidden', 'clip', 'auto', 'scroll'].includes(style.overflowX || style.overflow)
    if (hasExplicitTextWidthConstraint(element) || this.hasBoxVisual(element, style) || clipsHorizontalContent) return true
    if (style.display === 'contents') return false
    if (style.display.includes('inline')) return false
    const parent = element.parentElement
    if (parent) {
      const parentStyle = getComputedStyle(parent)
      const layout = this.layout.resolveLayoutDisplay(parent, parentStyle)
      if (layout === 'grid') return true
      if (layout === 'flex' && !this.layout.resolveFlexDirection(parent, parentStyle).startsWith('column') &&
        !(Number.parseFloat(style.flexGrow) > 0) && (!style.flexBasis || style.flexBasis === 'auto')) return false
    }
    return true
  }

  /** 可见背景、边框或 padding 的容器承载独立视觉范围，文字扩宽不得侵入其边缘。 */
  private hasBoxVisual(element: HTMLElement, style: CSSStyleDeclaration): boolean {
    const padding = this.layout.resolveElementPaddingPixels(element, style)
    return this.hasBoxPaint(element, style) || padding.left > 0 || padding.right > 0
  }

  /** 判断 HTML 盒自身是否绘制可见内容；padding 只约束自身布局，不代表整块区域有像素。 */
  private hasBoxPaint(element: HTMLElement, style: CSSStyleDeclaration): boolean {
    const background = this.layout.parseCssColor(this.layout.resolveBackgroundColorValue(element, style), element)
    return Boolean(background && background.alpha > 0) ||
      Boolean(style.backgroundImage && style.backgroundImage !== 'none') ||
      Boolean(style.boxShadow && style.boxShadow !== 'none') ||
      this.layout.getBorderInfos(element, style).length > 0
  }

  /**
   * 提取实际可见障碍；透明容器递归测量后代及文字，事件穿透不影响可见性。
   * SVG 与图片等固有绘制对象保留实测边界；无布局环境的零矩形不作为碰撞证据。
   */
  private measureObstacles(node: Node): ElementBox[] {
    if (isTextNode(node)) {
      if (!node.textContent?.trim()) return []
      const parent = node.parentElement
      if (parent && ['hidden', 'collapse'].includes(getComputedStyle(parent).visibility)) return []
      const box = this.layout.getPptxTextNodeBox(node)
      if (box) return [box]
      // Range 不可用时，仅采用有真实尺寸的叶子文字元素，不回退成透明祖先的大矩形。
      if (parent && parent.children.length === 0) {
        const rect = parent.getBoundingClientRect()
        const fallback = rect.width > 0 && rect.height > 0 ? this.layout.getPptxBox(parent) : null
        if (fallback) return [fallback]
      }
      return []
    }
    if (node.nodeType !== 1) return []
    const element = node as Element
    const style = getComputedStyle(element)
    if (style.display === 'none' || Number.parseFloat(style.opacity) === 0) return []
    const boxes: ElementBox[] = []
    const hasIntrinsicPaint = isSVGElement(element) || ['img', 'canvas', 'video', 'iframe', 'object', 'embed'].includes(element.localName)
    if (!['hidden', 'collapse'].includes(style.visibility) &&
      (hasIntrinsicPaint || this.hasBoxPaint(element as HTMLElement, style))) {
      const rect = element.getBoundingClientRect()
      if (rect.width > 0 && rect.height > 0) {
        const box = this.layout.getPptxBox(element)
        if (box) boxes.push(box)
      }
    }
    if (!hasIntrinsicPaint) {
      for (const child of element.childNodes) boxes.push(...this.measureObstacles(child))
    }
    return boxes
  }

  /** 仅限制同高度对象所在方向，避免把上下排列的段落或原有越界当作新增碰撞。 */
  private limitByObstacle(bounds: TextExpansionBounds, box: ElementBox, obstacle: ElementBox): void {
    if (Math.min(box.y + box.h, obstacle.y + obstacle.h) <= Math.max(box.y, obstacle.y) + EPSILON) return
    const right = box.x + box.w
    const obstacleRight = obstacle.x + obstacle.w
    // 若障碍物在水平轴上完全跨越或包含当前 box，属于分层或背景覆盖，绝不把可用边界双向压死为 0
    if (obstacle.x <= box.x + EPSILON && obstacleRight >= right - EPSILON) return

    // 障碍物在右侧：相邻兄弟共享中间的间隙，保留安全间距，避免双方各自扩宽相撞重叠
    if (obstacle.x >= right - EPSILON) {
      const freeGap = Math.max(0, obstacle.x - right)
      const minVisualGap = Math.min(freeGap * 0.25, this.layout.cssPxToMeasuredPx(2) * this.layout.inchPerPxX())
      const usableGap = Math.max(0, (freeGap - minVisualGap) * 0.5)
      bounds.right = Math.min(bounds.right, right + usableGap)
    } else if (obstacleRight > right + EPSILON && obstacle.x > box.x + EPSILON) {
      bounds.right = Math.min(bounds.right, obstacle.x)
    }

    // 障碍物在左侧：同理共享间隙
    if (obstacleRight <= box.x + EPSILON) {
      const freeGap = Math.max(0, box.x - obstacleRight)
      const minVisualGap = Math.min(freeGap * 0.25, this.layout.cssPxToMeasuredPx(2) * this.layout.inchPerPxX())
      const usableGap = Math.max(0, (freeGap - minVisualGap) * 0.5)
      bounds.left = Math.max(bounds.left, box.x - usableGap)
    } else if (obstacle.x < box.x - EPSILON && obstacleRight < right - EPSILON) {
      bounds.left = Math.max(bounds.left, obstacleRight)
    }
  }
}
