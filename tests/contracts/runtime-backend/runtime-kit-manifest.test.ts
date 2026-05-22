/**
 * 文件功能：校验 runtime 暴露给 backend 与平台集成层消费的 Runtime Kit manifest 基础契约。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const manifestPath = resolve(process.cwd(), 'runtime/src/runtime-kit/manifest/runtime-kit.manifest.json')
const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8')) as {
  alias?: string
  capabilities?: Array<{ import_path?: string; category?: string; kind?: string }>
}

describe('runtime-backend manifest contract', () => {
  it('应继续通过 @runtime-kit 暴露公开能力', () => {
    expect(manifest.alias).toBe('@runtime-kit')
  })

  it('不应把 internal、runtime-shell 和 component-preview 目录暴露给平台页面源码', () => {
    const importPaths = (manifest.capabilities || []).map((item) => item.import_path || '')
    for (const importPath of importPaths) {
      expect(importPath).not.toContain('/internal/')
      expect(importPath).not.toContain('/runtime-shell/')
      expect(importPath).not.toContain('/component-preview/')
    }
  })

  it('公开能力应保留 category 与 kind 说明，便于 backend 和 agent 侧排序与过滤', () => {
    for (const item of manifest.capabilities || []) {
      expect(item.category).toBeTruthy()
      expect(item.kind).toBeTruthy()
    }
  })
})
