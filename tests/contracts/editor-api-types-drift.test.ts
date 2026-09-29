/**
 * 文件功能：Editor api.ts 手写镜像与 OpenAPI 生成物 api.generated.ts 的漂移对拍。
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const repoRoot = fileURLToPath(new URL('../../', import.meta.url))
const apiTsPath = join(repoRoot, 'editor/src/types/api.ts')
const generatedTsPath = join(repoRoot, 'editor/src/types/api.generated.ts')

/**
 * 手写镜像名 → OpenAPI 生成物名。
 * 分页泛型在 OpenAPI 中展开为具体 PagedResponse_*。
 */
const TYPE_NAME_MAP: Array<{ handwritten: string; generated: string }> = [
  { handwritten: 'AuthUser', generated: 'AuthUser' },
  { handwritten: 'ProjectItem', generated: 'ProjectItem' },
  { handwritten: 'PageItem', generated: 'PageItem' },
  { handwritten: 'PreviewArtifactResponse', generated: 'PreviewArtifactResponse' },
  { handwritten: 'WorkspaceComponentItem', generated: 'WorkspaceComponentItem' },
  { handwritten: 'ThemeItem', generated: 'WorkspaceThemeItem' },
  { handwritten: 'StyleItem', generated: 'WorkspaceStyleItem' },
  { handwritten: 'AssetItem', generated: 'AssetResponse' },
]

function extractInterfaceFields(source: string, interfaceName: string): Set<string> {
  const pattern = new RegExp(`export interface ${interfaceName}\\s*(?:<[^>]+>)?\\s*\\{([\\s\\S]*?)\\n\\}`)
  const match = pattern.exec(source)
  if (!match) {
    return new Set()
  }
  const fields = new Set<string>()
  for (const line of match[1].split('\n')) {
    const stripped = line.trim()
    if (!stripped || stripped.startsWith('//') || stripped.startsWith('*')) {
      continue
    }
    // 支持 `name?:`、`name:`、`"name"?:`、`"name":`
    const fieldMatch = /^(?:["']([A-Za-z_][A-Za-z0-9_]*)["']|([A-Za-z_][A-Za-z0-9_]*))\??\s*:/.exec(stripped)
    if (fieldMatch) {
      fields.add(fieldMatch[1] || fieldMatch[2])
    }
  }
  return fields
}

describe('editor api types drift', () => {
  it('api.generated.ts 应存在且标注为生成物', () => {
    const generated = readFileSync(generatedTsPath, 'utf-8')
    expect(generated).toContain('生成物，勿手改')
    expect(generated).toContain('codegen:editor-api')
    expect(generated).toContain('export const GENERATED_API_SCHEMA_NAMES')
  })

  it('OpenAPI 生成物应覆盖映射后的类型名', () => {
    const generated = readFileSync(generatedTsPath, 'utf-8')
    for (const { generated: name } of TYPE_NAME_MAP) {
      expect(generated, `生成物缺少 ${name}`).toContain(`export interface ${name}`)
    }
  })

  it('api.ts 手写镜像的 Top 字段必须是生成物字段的子集', () => {
    const apiSource = readFileSync(apiTsPath, 'utf-8')
    const generatedSource = readFileSync(generatedTsPath, 'utf-8')

    for (const { handwritten, generated: generatedName } of TYPE_NAME_MAP) {
      const handwrittenFields = extractInterfaceFields(apiSource, handwritten)
      const generatedFields = extractInterfaceFields(generatedSource, generatedName)
      if (handwrittenFields.size === 0) {
        continue
      }
      expect(generatedFields.size, `生成物未找到 ${generatedName}`).toBeGreaterThan(0)
      const missing = [...handwrittenFields].filter(f => !generatedFields.has(f))
      expect(
        missing,
        `${handwritten} → ${generatedName} 手写字段未出现在生成物中：${missing.join(', ')}`,
      ).toEqual([])
    }
  })

  it('生成物 schema 数量应合理（防止 codegen 空跑）', () => {
    const generated = readFileSync(generatedTsPath, 'utf-8')
    const matches = generated.match(/export (?:interface|type) /g) || []
    expect(matches.length).toBeGreaterThan(50)
  })
})
