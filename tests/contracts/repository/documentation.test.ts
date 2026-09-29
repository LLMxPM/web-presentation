/** 文件功能：检查已纳管 Markdown 的本地链接与代码围栏，发现目录迁移后的文档断链。 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { expect, it } from 'vitest'

/** 检查工作树现存文档，包含未暂存的新文档；已归档移动的旧路径不再作为输入。 */
function documents(): string[] {
  const files = execFileSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', '*.md'], { encoding: 'utf8' })
    .split('\0').filter(file => file && fs.existsSync(file))
  return [...new Set(files)]
}

it('文档中的相对链接必须指向存在的文件或目录', () => {
  const broken: string[] = []
  for (const file of documents()) {
    const source = fs.readFileSync(file, 'utf8')
    for (const match of source.matchAll(/\]\(([^\s)]+)/g)) {
      const target = match[1]!.split('#')[0]!
      if (!target || /^(?:[\w+.-]+:|\/|<|\{)/.test(target)) continue
      if (!fs.existsSync(path.resolve(path.dirname(file), decodeURIComponent(target)))) {
        broken.push(`${file}: ${target}`)
      }
    }
  }
  expect(broken).toEqual([])
})

it('Markdown 代码围栏必须闭合', () => {
  const broken: string[] = []
  for (const file of documents()) {
    let fence = ''
    for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
      const match = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/)
      if (!match) continue
      if (!fence) fence = match[1]!
      else if (match[1]![0] === fence[0] && match[1]!.length >= fence.length && !match[2]!.trim()) fence = ''
    }
    if (fence) broken.push(file)
  }
  expect(broken).toEqual([])
})
