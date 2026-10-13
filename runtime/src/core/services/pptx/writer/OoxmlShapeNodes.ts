/** 文件用途：按 XML 元素边界读取幻灯片直接图元，避免正则跨形状匹配或进入嵌套组成员。 */

export interface OoxmlShapeNode {
  start: number
  end: number
  xml: string
  name?: string
}

/** 转义 XML 属性值，供图元名称匹配和组名称序列化复用。 */
export function escapeXmlAttribute(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/**
 * 扫描 spTree 的直接图元；兼容单个图元片段测试，保留原始 XML 与字节位置。
 * 只解析标签层级，不改写文本、关系、命名空间或非图元内容。
 */
export function readSlideShapeNodes(xml: string): OoxmlShapeNode[] {
  const hasTree = /<p:spTree(?:\s[^>]*)?>/.test(xml)
  const stack: string[] = []
  const nodes: OoxmlShapeNode[] = []
  let current: { start: number; depth: number } | undefined
  for (const match of xml.matchAll(/<!--[\s\S]*?-->|<\/?([\w:.-]+)\b[^>]*>/g)) {
    const token = match[0]
    const tag = match[1]
    if (!tag) continue
    const closing = token.startsWith('</')
    const selfClosing = token.endsWith('/>')
    if (!closing) {
      const isDirect = hasTree ? stack.at(-1) === 'p:spTree' : stack.length === 0
      if (!current && isDirect && ['p:sp', 'p:pic', 'p:graphicFrame', 'p:grpSp'].includes(tag)) {
        current = { start: match.index!, depth: stack.length }
      }
      if (!selfClosing) stack.push(tag)
    } else {
      if (stack.pop() !== tag) throw new Error('PPTX 图元 XML 标签不匹配')
      if (current && stack.length === current.depth) {
        const end = match.index! + token.length
        const fragment = xml.slice(current.start, end)
        const name = /<p:cNvPr\b[^>]*\bname="([^"]*)"/.exec(fragment)?.[1]
        nodes.push({ start: current.start, end, xml: fragment, name })
        current = undefined
      }
    }
  }
  if (current || stack.length) throw new Error('PPTX 图元 XML 未闭合')
  return nodes
}

/** 分配当前幻灯片尚未使用的形状 ID，避免固定 ID 与大量图元冲突。 */
export function nextSlideShapeId(xml: string): number {
  return Math.max(0, ...Array.from(xml.matchAll(/<p:cNvPr\b[^>]*\bid="(\d+)"/g), match => Number(match[1]))) + 1
}
