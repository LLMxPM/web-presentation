/**
 * 文件用途：提供 PPTX DOM 转换跨窗口与跨 Realm 页面环境适配器，统一处理 iframe 与主文档的 DOM 读取、计算样式及类型判定。
 */

/**
 * 获取节点所属的宿主 Window 对象，跨 iframe 时返回对应 iframe 的 contentWindow。
 * @param node 目标 DOM 节点
 * @returns 所属 Window，回退到全局 window
 */
export function getOwnerWindow(node: Node | null | undefined): Window {
  if (!node) {
    return typeof window !== 'undefined' ? window : ({} as Window)
  }
  return node.ownerDocument?.defaultView || (node as unknown as Document).defaultView || window
}

/**
 * 获取节点所属的 Document 对象。
 * @param node 目标 DOM 节点
 * @returns 所属 Document，回退到全局 document
 */
export function getOwnerDocument(node: Node | null | undefined): Document {
  if (!node) {
    return typeof document !== 'undefined' ? document : ({} as Document)
  }
  if (node.nodeType === 9) {
    return node as Document
  }
  return node.ownerDocument || document
}

/**
 * 跨窗口安全获取元素的计算样式。
 * @param element 目标 DOM 元素
 * @returns CSSStyleDeclaration 计算样式
 */
export function getComputedStyle(element: Element): CSSStyleDeclaration {
  const win = getOwnerWindow(element)
  return win.getComputedStyle(element)
}

/**
 * 跨窗口安全创建 Range 实例，用于精准文本度量。
 * @param node 目标节点或上下文节点
 * @returns Range 实例
 */
export function createRange(node: Node): Range {
  const doc = getOwnerDocument(node)
  return doc.createRange()
}

/**
 * 跨窗口判定节点是否为 HTMLElement。
 * @param node 候选对象
 * @returns 是否为 HTMLElement 实例
 */
export function isHTMLElement(node: unknown): node is HTMLElement {
  if (!node || typeof node !== 'object') {
    return false
  }
  if (node instanceof HTMLElement) {
    return true
  }
  const win = (node as Node).ownerDocument?.defaultView
  if (win && typeof win.HTMLElement === 'function' && node instanceof win.HTMLElement) {
    return true
  }
  const candidate = node as { nodeType?: number; style?: unknown; tagName?: unknown }
  return (
    candidate.nodeType === 1 &&
    typeof candidate.style === 'object' &&
    typeof candidate.tagName === 'string'
  )
}

/**
 * 跨窗口判定节点是否为 SVGElement。
 * @param node 候选对象
 * @returns 是否为 SVGElement 实例
 */
export function isSVGElement(node: unknown): node is SVGElement {
  if (!node || typeof node !== 'object') {
    return false
  }
  if (node instanceof SVGElement) {
    return true
  }
  const win = (node as Node).ownerDocument?.defaultView
  if (win && typeof win.SVGElement === 'function' && node instanceof win.SVGElement) {
    return true
  }
  const candidate = node as { nodeType?: number; namespaceURI?: unknown; ownerSVGElement?: unknown }
  return candidate.nodeType === 1 && candidate.namespaceURI === 'http://www.w3.org/2000/svg'
}

/**
 * 跨窗口判定节点是否为 SVGSVGElement 根标签。
 * @param node 候选对象
 * @returns 是否为 SVGSVGElement 实例
 */
export function isSVGSVGElement(node: unknown): node is SVGSVGElement {
  if (!isSVGElement(node)) {
    return false
  }
  if (typeof SVGSVGElement !== 'undefined' && node instanceof SVGSVGElement) {
    return true
  }
  const win = (node as Node).ownerDocument?.defaultView
  if (win && typeof win.SVGSVGElement === 'function' && node instanceof win.SVGSVGElement) {
    return true
  }
  return (node as Element).tagName.toLowerCase() === 'svg'
}

/**
 * 跨窗口判定节点是否为 HTMLTableElement。
 * @param node 候选对象
 * @returns 是否为 HTMLTableElement 实例
 */
export function isHTMLTableElement(node: unknown): node is HTMLTableElement {
  if (!node || typeof node !== 'object') {
    return false
  }
  if (node instanceof HTMLTableElement) {
    return true
  }
  const win = (node as Node).ownerDocument?.defaultView
  if (win && typeof win.HTMLTableElement === 'function' && node instanceof win.HTMLTableElement) {
    return true
  }
  return isHTMLElement(node) && node.tagName.toLowerCase() === 'table'
}

/**
 * 跨窗口判定节点是否为 HTMLImageElement。
 * @param node 候选对象
 * @returns 是否为 HTMLImageElement 实例
 */
export function isHTMLImageElement(node: unknown): node is HTMLImageElement {
  if (!node || typeof node !== 'object') {
    return false
  }
  if (node instanceof HTMLImageElement) {
    return true
  }
  const win = (node as Node).ownerDocument?.defaultView
  if (win && typeof win.HTMLImageElement === 'function' && node instanceof win.HTMLImageElement) {
    return true
  }
  return isHTMLElement(node) && node.tagName.toLowerCase() === 'img'
}

/**
 * 跨窗口判定节点是否为 HTMLCanvasElement。
 * @param node 候选对象
 * @returns 是否为 HTMLCanvasElement 实例
 */
export function isHTMLCanvasElement(node: unknown): node is HTMLCanvasElement {
  if (!node || typeof node !== 'object') {
    return false
  }
  if (node instanceof HTMLCanvasElement) {
    return true
  }
  const win = (node as Node).ownerDocument?.defaultView
  if (win && typeof win.HTMLCanvasElement === 'function' && node instanceof win.HTMLCanvasElement) {
    return true
  }
  return isHTMLElement(node) && node.tagName.toLowerCase() === 'canvas'
}

/**
 * 跨窗口判定节点是否为 HTMLAnchorElement。
 * @param node 候选对象
 * @returns 是否为 HTMLAnchorElement 实例
 */
export function isHTMLAnchorElement(node: unknown): node is HTMLAnchorElement {
  if (!node || typeof node !== 'object') {
    return false
  }
  if (node instanceof HTMLAnchorElement) {
    return true
  }
  const win = (node as Node).ownerDocument?.defaultView
  if (win && typeof win.HTMLAnchorElement === 'function' && node instanceof win.HTMLAnchorElement) {
    return true
  }
  return isHTMLElement(node) && node.tagName.toLowerCase() === 'a'
}
