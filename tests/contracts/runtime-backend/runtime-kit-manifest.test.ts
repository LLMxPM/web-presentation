/**
 * 文件功能：校验 runtime 暴露给 backend 与平台集成层消费的 Runtime Kit manifest 基础契约。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const manifestPath = resolve(process.cwd(), 'runtime/src/runtime-kit/manifest/runtime-kit.manifest.json')
const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8')) as {
  alias?: string
  exports?: Array<{
    import_path?: string
    category?: string
    kind?: string
    name?: string
    base_name?: string
    version_no?: number
    capability?: { enabled?: boolean }
  }>
}

const exportsList = manifest.exports ?? []

describe('runtime-backend manifest contract', () => {
  it('应继续通过 @runtime-kit 暴露公开能力', () => {
    expect(manifest.alias).toBe('@runtime-kit')
  })

  it('manifest 应包含非空 exports 清单', () => {
    expect(exportsList.length).toBeGreaterThan(0)
  })

  it('不应把 internal、runtime-shell 和 component-preview 目录暴露给平台页面源码', () => {
    for (const item of exportsList) {
      const importPath = item.import_path || ''
      expect(importPath).not.toContain('/internal/')
      expect(importPath).not.toContain('/runtime-shell/')
      expect(importPath).not.toContain('/component-preview/')
    }
  })

  it('公开能力应保留 category 与 kind 说明，便于 backend 和 agent 侧排序与过滤', () => {
    for (const item of exportsList) {
      expect(item.category).toBeTruthy()
      expect(item.kind).toBeTruthy()
    }
  })

  it('导出项应使用 <ExportName>.v<整数版本> 命名并指向带 .vN 的公开路径', () => {
    for (const item of exportsList) {
      const name = item.name || ''
      const importPath = item.import_path || ''
      expect(name).toMatch(/\.v\d+$/)
      expect(importPath).toContain(`.${name.split('.').pop()}`)
      expect(importPath.startsWith('@runtime-kit/')).toBe(true)
    }
  })
})
