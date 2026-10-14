/** 文件用途：测量文字的实际行布局，为 PPTX 文本扩宽提供单行或多行依据，支持 iframe 和行内富文本。 */
import { createRange, getOwnerDocument, isTextNode } from '../dom/PPTXDomEnvironment'

/**
 * 判断锚点的可见文字是否处于同一行；没有有效 Range 布局时返回 null，由调用方保守回退。
 * 只测量文本节点，避免行内元素的盒模型被误算成文字行；相同行的不同字号按垂直重叠合并。
 */
export function measureSingleLineText(anchor: Node): boolean | null {
  const nodes: Text[] = []
  if (isTextNode(anchor)) {
    nodes.push(anchor)
  } else {
    const walker = getOwnerDocument(anchor).createTreeWalker(anchor, 4 /* SHOW_TEXT */)
    for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node as Text)
  }

  let lineTop = -Infinity
  let lineBottom = Infinity
  let measured = false
  try {
    for (const node of nodes) {
      if (!node.textContent?.trim()) continue
      const range = createRange(node)
      range.selectNodeContents(node)
      if (typeof range.getClientRects !== 'function') continue
      let nodeTop: number | null = null
      for (const rect of Array.from(range.getClientRects())) {
        if (rect.width <= 0 || rect.height <= 0) continue
        // 同一文字节点的字体一致，不同顶部对应不同文字行；极紧行距也不能合并成单行。
        if (nodeTop !== null && Math.abs(rect.top - nodeTop) > 0.5) return false
        nodeTop = rect.top
        // 去掉字形矩形的上下边缘，避免紧行距下两行仅边缘重叠被误认为单行。
        lineTop = Math.max(lineTop, rect.top + rect.height * 0.2)
        lineBottom = Math.min(lineBottom, rect.bottom - rect.height * 0.2)
        measured = true
        if (lineBottom <= lineTop + 0.5) return false
      }
    }
  } catch {
    return null
  }
  return measured ? true : null
}
