/** 文件用途：根据真实容器内容边界和同高度相邻对象限制文本扩宽，保留原有位置及越界，不挤占其他内容。 */
import { getComputedStyle, isTextNode } from '../dom/PPTXDomEnvironment'
import type { ElementBox } from '../PPTXDomConverter.types'
import type { PPTXDomConverterLayout } from '../PPTXDomConverterLayout'

export interface TextExpansionBounds { left: number; right: number }
const EPSILON = 0.0001

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
        const siblingBox = this.measureObstacle(sibling)
        if (siblingBox) this.limitByObstacle(bounds, box, siblingBox)
      }
    }
    return bounds
  }

  /** 内容驱动的透明 inline/横向 Flex 子项可使用外层空白；网格单元、显式尺寸和可见卡片则限制边界。 */
  private isBoundedContainer(element: HTMLElement): boolean {
    const style = getComputedStyle(element)
    const explicitWidth = ['width', 'min-width', 'max-width', 'flex-basis'].some(name => element.style.getPropertyValue(name)) ||
      Array.from(element.classList).some(name => /^(?:min-|max-)?w-(?!auto$)|^basis-/.test(name.split(':').pop() || ''))
    if (explicitWidth || this.hasBoxVisual(element, style)) return true
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
    const background = this.layout.parseCssColor(this.layout.resolveBackgroundColorValue(element, style), element)
    const padding = this.layout.resolveElementPaddingPixels(element, style)
    return Boolean(background && background.alpha > 0) ||
      Boolean(style.backgroundImage && style.backgroundImage !== 'none') ||
      this.layout.getBorderInfos(element, style).length > 0 ||
      padding.left > 0 || padding.right > 0
  }

  /** 兄弟元素只采用真实布局矩形；无布局环境的零坐标不作为重叠证据，直属文字用 Range 测量。 */
  private measureObstacle(node: Node): ElementBox | null {
    if (isTextNode(node)) return this.layout.getPptxTextNodeBox(node)
    if (node.nodeType !== 1) return null
    const element = node as Element
    const style = getComputedStyle(element)
    if (style.display === 'none' || ['hidden', 'collapse'].includes(style.visibility) || Number.parseFloat(style.opacity) === 0) return null
    if (this.isTransparentDecorator(element as HTMLElement, style)) return null
    const rect = element.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) return null
    return this.layout.getPptxBox(element)
  }

  /** 判断元素是否为纯事件穿透或覆盖整页的透明装饰图层，避免将其整块矩形当作阻碍文本扩宽的实体障碍。 */
  private isTransparentDecorator(element: HTMLElement, style: CSSStyleDeclaration): boolean {
    if (this.hasBoxVisual(element, style)) return false
    if (style.pointerEvents === 'none') return true
    if (['absolute', 'fixed'].includes(style.position)) {
      const rect = element.getBoundingClientRect()
      const root = this.layout.rootElement()
      const rootRect = root?.getBoundingClientRect()
      if (rootRect && rect.width >= rootRect.width * 0.95 && rect.height >= rootRect.height * 0.95) {
        return true
      }
    }
    return false
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
