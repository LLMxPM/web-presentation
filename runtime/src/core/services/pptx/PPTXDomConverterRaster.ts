/**
 * 文件用途：封装 PPTX DOM 转换中需要降级截图的 3D CSS 视觉识别。
 */

import { MEDIA_SELECTORS } from '@/core/services/pptx/PPTXDomConverter.types'
import type { PPTXDomConverterLayout } from '@/core/services/pptx/PPTXDomConverterLayout'
import type { MeasuredElementBox } from '@/core/services/pptx/PPTXDomConverter.types'

export const PPTX_3D_SCREENSHOT_REASON = '3D CSS 视觉降级为局部截图'

const PAGE_AREA_SCREENSHOT_THRESHOLD = 0.82

/**
 * 负责识别 PPTX 难以原生表达的 3D CSS 子树，并选择稳定截图宿主。
 */
export class PPTXDomConverterRaster {
  constructor(private readonly layout: PPTXDomConverterLayout) {}

  /**
   * 解析当前元素是否应因 3D CSS 视觉降级截图。
   * @param element 当前访问元素
   * @param pageElement 页面根元素
   * @returns 需要截图的 HTML 元素；不命中时返回 null
   */
  resolve3dScreenshotTarget(element: Element, pageElement: HTMLElement): HTMLElement | null {
    if (element === pageElement) {
      return null
    }

    if (element instanceof HTMLElement) {
      const groupTarget = this.resolve3dGroupTarget(element, pageElement)
      if (groupTarget) {
        return groupTarget
      }
    }

    if (this.hasOwn3dVisual(element)) {
      return this.resolveOwn3dTarget(element, pageElement)
    }

    if (this.isTerminalMediaElement(element) && this.contains3dVisual(element)) {
      return this.resolveMediaDescendantTarget(element, pageElement)
    }

    return null
  }

  /**
   * 判断元素自身是否启用了会产生 3D 视觉的 CSS。
   * @param element 候选元素
   */
  hasOwn3dVisual(element: Element): boolean {
    const style = window.getComputedStyle(element)
    if (this.has3dTransform(style.transform)) {
      return true
    }

    return (this.hasPreserve3d(style) || this.hasCssPerspective(style)) &&
      !this.shouldDefer3dContextContainer(element)
  }

  /**
   * 判断元素或其后代是否包含 3D CSS 触发点。
   * @param element 候选元素
   */
  contains3dVisual(element: Element): boolean {
    if (this.hasOwn3dTrigger(element)) {
      return true
    }

    return Array.from(element.children).some(child => this.contains3dVisual(child))
  }

  /**
   * 当多个直接子分支都包含 3D 视觉时，优先截图共同父容器。
   * @param element 候选父容器
   * @param pageElement 页面根元素
   */
  private resolve3dGroupTarget(element: HTMLElement, pageElement: HTMLElement): HTMLElement | null {
    if (element === pageElement || this.isNearPageArea(element, pageElement)) {
      return null
    }

    const branches = this.collectDirect3dBranches(element)
    if (
      branches.length < 2 ||
      branches.some(branch => this.hasMeaningfulTextOutside3dIsland(branch)) ||
      this.hasMeaningfulTextOutsideBranches(element, branches)
    ) {
      return null
    }

    return element
  }

  /**
   * 收集当前容器下直接包含 3D 视觉的可见子分支。
   * @param element 候选父容器
   */
  private collectDirect3dBranches(element: HTMLElement): Element[] {
    return Array.from(element.children).filter(child => {
      return this.layout.isVisibleElement(child) && this.contains3dVisual(child)
    })
  }

  /**
   * 识别所有 3D 相关 CSS 触发点，包含只作为子级上下文的 perspective。
   * @param element 候选元素
   */
  private hasOwn3dTrigger(element: Element): boolean {
    const style = window.getComputedStyle(element)
    return this.has3dTransform(style.transform) ||
      this.hasPreserve3d(style) ||
      this.hasCssPerspective(style)
  }

  /**
   * 判断 transform 是否包含 PPTX 难以还原的 3D 函数。
   * @param value transform 计算值或声明值
   */
  private has3dTransform(value: string): boolean {
    const normalizedValue = String(value || '').trim()
    if (!normalizedValue || normalizedValue === 'none') {
      return false
    }

    if (/\b(?:perspective|rotatex|rotatey|rotate3d)\s*\(/i.test(normalizedValue)) {
      return true
    }

    const matrix3d = /\bmatrix3d\(([^)]+)\)/i.exec(normalizedValue)
    return Boolean(matrix3d && !this.isPureTranslateMatrix3d(matrix3d[1]))
  }

  /**
   * 判断 matrix3d 是否只表达位移，纯 translate3d 不需要截图。
   * @param value matrix3d 参数列表
   */
  private isPureTranslateMatrix3d(value: string): boolean {
    const values = this.parseTransformNumberList(value)
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
   * 解析 transform 矩阵参数为数字列表。
   * @param value 逗号或空格分隔参数
   */
  private parseTransformNumberList(value: string): number[] {
    return value
      .split(/[,\s]+/)
      .map(item => Number.parseFloat(item))
      .filter(item => Number.isFinite(item))
  }

  /**
   * 浮点近似比较，避免浏览器矩阵小数误差导致误判。
   * @param actual 实际值
   * @param expected 期望值
   */
  private isNearlyEqual(actual: number, expected: number): boolean {
    return Math.abs(actual - expected) <= 0.0001
  }

  /**
   * 判断 transform-style 是否保留 3D 子级空间。
   * @param style 计算样式
   */
  private hasPreserve3d(style: CSSStyleDeclaration): boolean {
    const style3d = style as CSSStyleDeclaration & { transformStyle?: string }
    return String(style3d.transformStyle || style.getPropertyValue('transform-style') || '').trim() === 'preserve-3d'
  }

  /**
   * 判断 CSS perspective 属性是否启用。
   * @param style 计算样式
   */
  private hasCssPerspective(style: CSSStyleDeclaration): boolean {
    const style3d = style as CSSStyleDeclaration & { perspective?: string }
    const value = String(style3d.perspective || style.getPropertyValue('perspective') || '').trim().toLowerCase()
    if (!value || value === 'none') {
      return false
    }

    const numeric = Number.parseFloat(value)
    return !Number.isFinite(numeric) || numeric > 0
  }

  /**
   * 3D 上下文只影响子级投影，普通容器先交给子树或分组规则处理。
   * @param element 候选元素
   */
  private shouldDefer3dContextContainer(element: Element): boolean {
    if (this.isTerminalMediaElement(element)) {
      return false
    }

    return element.children.length > 0
  }

  /**
   * 为自身带 3D 视觉的元素选择截图宿主。
   * @param element 当前元素
   * @param pageElement 页面根元素
   */
  private resolveOwn3dTarget(element: Element, pageElement: HTMLElement): HTMLElement | null {
    if (element instanceof HTMLElement) {
      if (this.isMediaLeafElement(element)) {
        const target = this.resolveMediaLeafWrapper(element, pageElement)
        return target ? this.expand3dIslandTargetForVisualOverflow(target, pageElement) : null
      }
      return this.resolve3dIslandTarget(element, pageElement)
    }

    return this.resolveNearestHtmlWrapper(element, pageElement)
  }

  /**
   * 将 3D transform 节点提升到包含 perspective 上下文的一层视觉岛宿主。
   * @param element 当前 3D 元素
   * @param pageElement 页面根元素
   */
  private resolve3dIslandTarget(element: HTMLElement, pageElement: HTMLElement): HTMLElement | null {
    if (element === pageElement) {
      return null
    }

    let target = element
    let current: HTMLElement = element
    let climbedThrough3dContext = false

    for (;;) {
      const parent = current.parentElement
      if (!parent || parent === pageElement || !this.isSingleElementWrapper(parent, current)) {
        break
      }

      if (this.hasOwn3dTrigger(parent)) {
        target = parent
        current = parent
        climbedThrough3dContext = true
        continue
      }

      if (climbedThrough3dContext) {
        target = parent
      }
      break
    }

    return this.expand3dIslandTargetForVisualOverflow(target, pageElement)
  }

  /**
   * 媒体终止节点包含 3D 后代时，截图媒体宿主本身。
   * @param element 当前媒体元素
   * @param pageElement 页面根元素
   */
  private resolveMediaDescendantTarget(element: Element, pageElement: HTMLElement): HTMLElement | null {
    if (element instanceof HTMLElement) {
      return element === pageElement ? null : this.expand3dIslandTargetForVisualOverflow(element, pageElement)
    }

    return this.resolveNearestHtmlWrapper(element, pageElement)
  }

  /**
   * 当 3D 后代视觉包围盒超出当前目标时，提升到不含额外文本的外层包裹，避免截图裁剪。
   * @param target 当前截图目标
   * @param pageElement 页面根元素
   */
  private expand3dIslandTargetForVisualOverflow(target: HTMLElement, pageElement: HTMLElement): HTMLElement {
    let current = target

    for (;;) {
      const visualBox = this.measureVisualSubtreeBox(current)
      if (!visualBox || this.isVisualBoxContained(current, visualBox) || this.hasClippingOverflow(current)) {
        return current
      }

      const parent = current.parentElement
      if (!parent || parent === pageElement || !this.isSingleElementWrapper(parent, current) || this.isNearPageArea(parent, pageElement)) {
        return current
      }

      current = parent
    }
  }

  /**
   * 计算当前截图目标及后代的视觉包围盒。
   * @param element 截图目标
   */
  private measureVisualSubtreeBox(element: HTMLElement): MeasuredElementBox | null {
    const boxes = [element, ...Array.from(element.querySelectorAll<HTMLElement>('*'))]
      .filter(item => this.layout.isVisibleElement(item))
      .map(item => this.measureRenderedElementBox(item))
      .filter((box): box is MeasuredElementBox => Boolean(box))
      .filter(box => box.width > 0 && box.height > 0)

    if (boxes.length === 0) {
      return null
    }

    const left = Math.min(...boxes.map(box => box.left))
    const top = Math.min(...boxes.map(box => box.top))
    const right = Math.max(...boxes.map(box => box.left + box.width))
    const bottom = Math.max(...boxes.map(box => box.top + box.height))
    return {
      left,
      top,
      width: Math.max(0, right - left),
      height: Math.max(0, bottom - top),
    }
  }

  /**
   * 判断视觉包围盒是否仍落在当前截图目标内。
   * @param element 截图目标
   * @param visualBox 子树视觉包围盒
   */
  private isVisualBoxContained(element: HTMLElement, visualBox: MeasuredElementBox): boolean {
    const box = this.measureRenderedElementBox(element)
    if (!box) {
      return true
    }

    const tolerancePx = 1
    return visualBox.left >= box.left - tolerancePx &&
      visualBox.top >= box.top - tolerancePx &&
      visualBox.left + visualBox.width <= box.left + box.width + tolerancePx &&
      visualBox.top + visualBox.height <= box.top + box.height + tolerancePx
  }

  /**
   * 读取浏览器真实渲染矩形；没有真实布局时不使用 CSS fallback，避免测试环境误判外溢。
   * @param element 目标元素
   */
  private measureRenderedElementBox(element: HTMLElement): MeasuredElementBox | null {
    const rect = element.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) {
      return null
    }

    return {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    }
  }

  /**
   * 判断元素是否显式裁剪溢出内容，存在裁剪时不应向外扩展截图目标。
   * @param element 候选元素
   */
  private hasClippingOverflow(element: HTMLElement): boolean {
    const style = window.getComputedStyle(element)
    return [style.overflow, style.overflowX, style.overflowY].some(value => {
      return ['hidden', 'clip', 'auto', 'scroll'].includes(String(value || '').trim())
    })
  }

  /**
   * 媒体叶子节点优先提升到只有它一个可见子元素的包裹层，保留圆角和阴影。
   * @param element 媒体叶子元素
   * @param pageElement 页面根元素
   */
  private resolveMediaLeafWrapper(element: HTMLElement, pageElement: HTMLElement): HTMLElement | null {
    const parent = element.parentElement
    if (
      parent &&
      parent !== pageElement &&
      this.collectVisibleChildren(parent).length === 1 &&
      !this.hasMeaningfulDirectText(parent)
    ) {
      return parent
    }

    return element === pageElement ? null : element
  }

  /**
   * 为非 HTML 元素查找最近 HTML 截图宿主。
   * @param element 当前元素
   * @param pageElement 页面根元素
   */
  private resolveNearestHtmlWrapper(element: Element, pageElement: HTMLElement): HTMLElement | null {
    const parent = element.parentElement
    if (!parent || parent === pageElement) {
      return null
    }

    return parent
  }

  /**
   * 判断当前元素是否属于转换器不会继续深入的媒体节点。
   * @param element 候选元素
   */
  private isTerminalMediaElement(element: Element): boolean {
    const tagName = element.tagName.toLowerCase()
    return element.matches(MEDIA_SELECTORS) || ['img', 'svg', 'canvas', 'video'].includes(tagName)
  }

  /**
   * 判断当前元素是否为普通媒体叶子节点。
   * @param element 候选元素
   */
  private isMediaLeafElement(element: HTMLElement): boolean {
    return ['img', 'canvas', 'video'].includes(element.tagName.toLowerCase())
  }

  /**
   * 判断候选容器是否接近整页，避免误把页面大布局整块栅格化。
   * @param element 候选容器
   * @param pageElement 页面根元素
   */
  private isNearPageArea(element: HTMLElement, pageElement: HTMLElement): boolean {
    const elementBox = this.layout.measureElementPixels(element)
    const pageBox = this.layout.measureElementPixels(pageElement)
    const pageArea = pageBox.width * pageBox.height
    const elementArea = elementBox.width * elementBox.height
    return pageArea > 0 && elementArea / pageArea > PAGE_AREA_SCREENSHOT_THRESHOLD
  }

  /**
   * 判断 3D 分支之外是否存在应保留可编辑的文本。
   * @param element 候选父容器
   * @param branches 直接 3D 子分支
   */
  private hasMeaningfulTextOutsideBranches(element: HTMLElement, branches: Element[]): boolean {
    if (this.hasMeaningfulDirectText(element)) {
      return true
    }

    const branchSet = new Set(branches)
    return Array.from(element.children).some(child => {
      return !branchSet.has(child) && this.subtreeHasMeaningfulText(child)
    })
  }

  /**
   * 判断分支里是否存在不属于 3D 视觉岛的有效文本。
   * @param element 候选分支
   */
  private hasMeaningfulTextOutside3dIsland(element: Element): boolean {
    if (this.hasOwn3dTrigger(element) || (this.isTerminalMediaElement(element) && this.contains3dVisual(element))) {
      return false
    }

    if (this.hasMeaningfulDirectText(element)) {
      return true
    }

    return Array.from(element.children).some(child => this.hasMeaningfulTextOutside3dIsland(child))
  }

  /**
   * 判断元素的直属文本节点是否包含有效文本。
   * @param element 候选元素
   */
  private hasMeaningfulDirectText(element: Element): boolean {
    return Array.from(element.childNodes).some(node => {
      return node instanceof Text && Boolean(this.layout.normalizeText(node.textContent || ''))
    })
  }

  /**
   * 判断子树中是否包含有效文本。
   * @param element 候选元素
   */
  private subtreeHasMeaningfulText(element: Element): boolean {
    return Boolean(this.layout.normalizeText(element.textContent || ''))
  }

  /**
   * 收集可见直接子元素。
   * @param element 候选父元素
   */
  private collectVisibleChildren(element: HTMLElement): Element[] {
    return Array.from(element.children).filter(child => this.layout.isVisibleElement(child))
  }

  /**
   * 判断父级是否只是当前元素的一层结构包裹。
   * @param parent 候选父元素
   * @param child 当前子元素
   */
  private isSingleElementWrapper(parent: HTMLElement, child: HTMLElement): boolean {
    return parent.children.length === 1 &&
      parent.firstElementChild === child &&
      !this.hasMeaningfulDirectText(parent)
  }
}
