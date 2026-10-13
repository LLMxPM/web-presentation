/**
 * 文件用途：统一导出节点所属文档的样式、Range 和 DOM 类型判断，避免 iframe 的跨窗口构造器差异。
 */

/** 获取节点所属文档；脱离文档的调用回退到当前宿主。 */
export function getOwnerDocument(node?: Node | null): Document {
  return node?.nodeType === 9 ? node as Document : node?.ownerDocument ?? document
}

/** 获取节点所属窗口；独立创建且没有窗口的文档回退到宿主。 */
export function getOwnerWindow(node?: Node | null): Window {
  return getOwnerDocument(node).defaultView ?? window
}

/** 在元素所属的窗口读取计算样式，保留 iframe 视口与主题。 */
export function getComputedStyle(element: Element): CSSStyleDeclaration {
  return getOwnerWindow(element).getComputedStyle(element)
}

/** 在文本节点所属文档创建测量 Range。 */
export function createRange(node: Node): Range {
  return getOwnerDocument(node).createRange()
}

/** 判断元素节点；nodeType 不依赖任一窗口的 Element 构造器。 */
export function isElement(node: unknown): node is Element {
  return Boolean(node && typeof node === 'object' && (node as Node).nodeType === 1)
}

/** 判断文本节点，支持 iframe 和独立文档。 */
export function isTextNode(node: unknown): node is Text {
  return Boolean(node && typeof node === 'object' && (node as Node).nodeType === 3)
}

/** 仅接受 HTML 命名空间；SVG 也有 style 属性，不能借此判为 HTML。 */
export function isHTMLElement(node: unknown): node is HTMLElement {
  return isElement(node) && node.namespaceURI === 'http://www.w3.org/1999/xhtml'
}

/** 判断 SVG 命名空间元素，避免跨窗口 instanceof 失效。 */
export function isSVGElement(node: unknown): node is SVGElement {
  return isElement(node) && node.namespaceURI === 'http://www.w3.org/2000/svg'
}

/** 判断 SVG 根节点。 */
export function isSVGSVGElement(node: unknown): node is SVGSVGElement {
  return isSVGElement(node) && node.localName === 'svg'
}

/** 判断 HTML 表格根节点。 */
export function isHTMLTableElement(node: unknown): node is HTMLTableElement {
  return isHTMLElement(node) && node.localName === 'table'
}

/** 判断 HTML 图片节点。 */
export function isHTMLImageElement(node: unknown): node is HTMLImageElement {
  return isHTMLElement(node) && node.localName === 'img'
}

/** 判断 HTML Canvas 节点。 */
export function isHTMLCanvasElement(node: unknown): node is HTMLCanvasElement {
  return isHTMLElement(node) && node.localName === 'canvas'
}

/** 判断 HTML 视频节点。 */
export function isHTMLVideoElement(node: unknown): node is HTMLVideoElement {
  return isHTMLElement(node) && node.localName === 'video'
}

/** 判断 HTML 链接节点。 */
export function isHTMLAnchorElement(node: unknown): node is HTMLAnchorElement {
  return isHTMLElement(node) && node.localName === 'a'
}
