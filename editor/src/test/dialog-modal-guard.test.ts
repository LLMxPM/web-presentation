/**
 * 文件功能：防止 Editor 重新引入绕过 BaseDialog 的自绘模态实现。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const sourceRoot = resolve(process.cwd(), 'src')
const allowedModalFiles = new Set([
  'components/ui/BaseDialog.vue',
])

/**
 * 递归收集目录下的全部 Vue 文件。
 * @param currentDir 当前遍历目录
 * @returns 目录内所有 Vue 文件绝对路径
 */
function collectVueFiles(currentDir: string): string[] {
  const result: string[] = []
  for (const entry of readdirSync(currentDir)) {
    const absolutePath = join(currentDir, entry)
    const stats = statSync(absolutePath)
    if (stats.isDirectory()) {
      result.push(...collectVueFiles(absolutePath))
      continue
    }
    if (absolutePath.endsWith('.vue')) {
      result.push(absolutePath)
    }
  }
  return result
}

describe('dialog modal guard', () => {
  it('仅允许 BaseDialog 持有全屏模态 Teleport 壳层', () => {
    const offenders = collectVueFiles(sourceRoot)
      .map(filePath => ({
        relativePath: relative(sourceRoot, filePath).replace(/\\/g, '/'),
        source: readFileSync(filePath, 'utf-8'),
      }))
      .filter(file => file.source.includes('Teleport to="body"') && file.source.includes('fixed inset-0'))
      .filter(file => !allowedModalFiles.has(file.relativePath))
      .map(file => file.relativePath)

    expect(offenders).toEqual([])
  })
})
