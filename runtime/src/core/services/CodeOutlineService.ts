/**
 * 文件用途：提供 Vue SFC 源码的代码大纲解析服务。
 * 说明：解析 <template>、<script>/<script setup>、<style> 及模板内常见 HTML/组件标签，返回可用于导航的节点列表。
 */

export interface OutlineNode { id: string; label: string; line: number; children?: OutlineNode[] }

/**
 * 函数：解析 Vue SFC 源码生成代码大纲
 * @param src 源代码字符串
 */
export function parseVueSFCOutline(src: string): OutlineNode[] {
  const nodes: OutlineNode[] = []
  const idxToLine = (i: number) => (i <= 0 ? 1 : src.slice(0, i).split('\n').length)

  /**
   * 解析 <template> 树结构
   */
  const tplOpen = src.match(/<template[^>]*>/i)
  if (tplOpen && tplOpen.index != null) {
    const tplStart = tplOpen.index
    const tplClose = /<\/template>/i.exec(src.slice(tplStart))
    const tplEndAbs = tplClose ? tplStart + (tplClose.index ?? 0) + tplClose[0].length : src.length
    const templateStartLine = idxToLine(tplStart)
    const innerStartAbs = tplStart + tplOpen[0].length
    const inner = src.slice(innerStartAbs, tplEndAbs)

    const root: OutlineNode = { id: `tpl-${tplStart}`, label: 'template', line: templateStartLine, children: [] }
    const stack: OutlineNode[] = [root]

    const tagRe = /<\/?([A-Za-z][\w-]*)\b([^>]*)\/?\s*>/g
    let m: RegExpExecArray | null
    while ((m = tagRe.exec(inner))) {
      const full = m[0]
      const name = m[1]
      const attrs = m[2] || ''
      const isClose = /^<\//.test(full)
      const isSelfClose = /\/>\s*$/.test(full)
      const absPos = innerStartAbs + (m.index ?? 0)
      const line = idxToLine(absPos)

      if (isClose) {
        if (stack.length > 1) stack.pop()
        continue
      }

      const clsM = /\bclass\s*=\s*"([^"]+)"|\bclass\s*=\s*'([^']+)'/i.exec(attrs)
      const classFirst = clsM ? (clsM[1] || clsM[2] || '').split(/\s+/).filter(Boolean)[0] : undefined
      const label = classFirst ? `${name} .${classFirst}` : name
      const node: OutlineNode = { id: `tpl-${name}-${absPos}`, label, line, children: [] }
      stack[stack.length - 1].children!.push(node)
      if (!isSelfClose) stack.push(node)
    }

    nodes.push(root)
  }

  /**
   * 解析 <script setup> 中 import 的组件名
   */
  const scriptSetupOpen = src.match(/<script[^>]*setup[^>]*>/i)
  if (scriptSetupOpen && scriptSetupOpen.index != null) {
    const ssStart = scriptSetupOpen.index
    const ssClose = /<\/script>/i.exec(src.slice(ssStart))
    const ssEndAbs = ssClose ? ssStart + (ssClose.index ?? 0) : src.length
    const scriptContent = src.slice(ssStart, ssEndAbs)
    const startLine = idxToLine(ssStart)
    const compNames = new Set<string>()

    const addIfComponent = (name: string) => {
      const n = name.trim()
      if (!n) return
      if (/^-/.test(n)) return
      if (/[A-Z]/.test(n[0]) || n.includes('-')) compNames.add(n)
    }

    let m: RegExpExecArray | null
    const defaultImport = /import\s+([A-Za-z_]\w*)\s+from\s+['"][^'"]+['"]/g
    while ((m = defaultImport.exec(scriptContent))) addIfComponent(m[1])

    const namedImport = /import\s+\{([^}]+)\}\s+from\s+['"][^'"]+['"]/g
    while ((m = namedImport.exec(scriptContent))) {
      const names = (m[1] || '').split(',').map(s => s.trim()).filter(Boolean)
      names.forEach(n => addIfComponent(n.split(/\s+as\s+/i)[1] || n.split(/\s+as\s+/i)[0]))
    }

    if (compNames.size > 0) {
      const children: OutlineNode[] = []
      compNames.forEach(n => {
        children.push({ id: `comp-${n}-${ssStart}`, label: n, line: startLine })
      })
      nodes.push({ id: `ss-${ssStart}`, label: 'script setup imports', line: startLine, children })
    }
  }

  return nodes
}
