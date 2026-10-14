/** 文件用途：处理直接子节点绘制顺序及无法拆分的视觉合成；普通 overflow 越界优先保留可编辑对象。 */
import { getComputedStyle, isHTMLElement } from '../dom/PPTXDomEnvironment'

/** 判断 CSS 视觉效果是否启用，兼容测试环境的空字符串。 */
function enabled(value?: string): boolean {
  return Boolean(value && value !== 'none' && value !== 'normal')
}

/** 无法逐图元表达的合成效果才截图；overflow 和圆角裁切不触发降级，原生对象保留实测几何。 */
export function requiresCompositeScreenshot(element: HTMLElement): boolean {
  const style = getComputedStyle(element)
  if (enabled(style.filter) || enabled(style.backdropFilter) || enabled(style.clipPath) ||
    enabled(style.maskImage) || enabled(style.mixBlendMode)) return true
  const children = Array.from(element.children).filter(isHTMLElement)
  const opacity = Number.parseFloat(style.opacity || '1')
  if (opacity > 0 && opacity < 1 && children.length > 0) {
    const background = style.backgroundColor.replace(/\s/g, '')
    if (background && !['transparent', 'rgba(0,0,0,0)'].includes(background)) return true
    const boxes = children.map(child => child.getBoundingClientRect())
    if (boxes.some((box, index) => boxes.slice(index + 1).some(other => box.width > 0 && box.height > 0 &&
      Math.min(box.right, other.right) > Math.max(box.left, other.left) &&
      Math.min(box.bottom, other.bottom) > Math.max(box.top, other.top)))) return true
  }
  return false
}

/**
 * 按同一父级内的负层级、普通流、定位层和正层级顺序绘制，保留同层 DOM 次序。
 * Flex/Grid 的 order 仅作用于直接元素；完整的跨层叠上下文顺序仍需单独实现与验收。
 */
export function collectPaintOrderedChildren(element: Element): ChildNode[] {
  const parentStyle = getComputedStyle(element)
  const flexOrGrid = /flex|grid/.test(parentStyle.display)
  return Array.from(element.childNodes).map((node, index) => {
    if (!isHTMLElement(node)) return { node, index, order: 0, phase: 1, z: 0 }
    const style = getComputedStyle(node)
    const order = flexOrGrid ? Number.parseFloat(style.order) || 0 : 0
    const positioned = ['relative', 'absolute', 'fixed', 'sticky'].includes(style.position) || flexOrGrid
    const explicitZ = positioned && style.zIndex && style.zIndex !== 'auto' && Number.isFinite(Number(style.zIndex))
    const z = explicitZ ? Number(style.zIndex) : 0
    const phase = explicitZ ? (z < 0 ? 0 : 2) : positioned ? 2 : 1
    return { node, index, order, phase, z }
  }).sort((a, b) => a.phase - b.phase || a.z - b.z || a.order - b.order || a.index - b.index).map(item => item.node)
}
