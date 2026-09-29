/**
 * 文件功能：previewSchema 三端对拍（TS 侧）——JSON Schema 单一源 vs Editor/Runtime 手写 interface。
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

import { describe, expect, it } from 'vitest'

const repoRoot = fileURLToPath(new URL('../../', import.meta.url))
const schemaPath = join(repoRoot, 'backend/app/core/component_preview_schema.v1.json')
const editorTsPath = join(repoRoot, 'editor/src/types/component-preview.ts')
const runtimeTsPath = join(repoRoot, 'runtime/src/core/shared/runtime-preview.ts')

interface SchemaDocument {
  properties: Record<string, unknown>
  $defs: Record<string, { required?: string[]; properties?: Record<string, unknown> }>
  'x-typescript-interfaces': Record<string, string[] | string>
}

function loadSchema(): SchemaDocument {
  return JSON.parse(readFileSync(schemaPath, 'utf-8')) as SchemaDocument
}

function extractInterfaceFields(tsSource: string, interfaceName: string): Set<string> {
  const pattern = new RegExp(`export interface ${interfaceName}\\s*\\{([\\s\\S]*?)\\n\\}`)
  const match = pattern.exec(tsSource)
  if (!match) {
    return new Set()
  }
  const fields = new Set<string>()
  for (const line of match[1].split('\n')) {
    const stripped = line.trim()
    if (!stripped || stripped.startsWith('//') || stripped.startsWith('*')) {
      continue
    }
    const fieldMatch = /^([A-Za-z_][A-Za-z0-9_]*)\??:/.exec(stripped)
    if (fieldMatch) {
      fields.add(fieldMatch[1])
    }
  }
  return fields
}

function tsInterfaceMap(schema: SchemaDocument): Record<string, string[]> {
  const raw = schema['x-typescript-interfaces']
  const result: Record<string, string[]> = {}
  for (const [name, fields] of Object.entries(raw)) {
    if (name === 'description' || !Array.isArray(fields)) {
      continue
    }
    result[name] = fields.map(String)
  }
  return result
}

describe('preview schema parity (TS)', () => {
  it('JSON Schema 单一源应声明顶层 props/slots/mocks/presets', () => {
    const schema = loadSchema()
    expect(schema.properties).toHaveProperty('props')
    expect(schema.properties).toHaveProperty('slots')
    expect(schema.properties).toHaveProperty('mocks')
    expect(schema.properties).toHaveProperty('presets')
    expect(schema.$defs.propField?.required).toEqual(['type'])
  })

  it('Editor component-preview.ts 应对齐 JSON Schema 映射字段', () => {
    const schema = loadSchema()
    const source = readFileSync(editorTsPath, 'utf-8')
    const mapping = tsInterfaceMap(schema)

    for (const [interfaceName, expectedFields] of Object.entries(mapping)) {
      const actual = extractInterfaceFields(source, interfaceName)
      expect(actual.size, `Editor 未找到 interface ${interfaceName}`).toBeGreaterThan(0)
      for (const field of expectedFields) {
        expect(actual, `Editor ${interfaceName} 缺少字段 ${field}`).toContain(field)
      }
    }
  })

  it('Runtime runtime-preview.ts 应对齐 JSON Schema 映射字段', () => {
    const schema = loadSchema()
    const source = readFileSync(runtimeTsPath, 'utf-8')
    const mapping = tsInterfaceMap(schema)

    for (const [interfaceName, expectedFields] of Object.entries(mapping)) {
      const actual = extractInterfaceFields(source, interfaceName)
      expect(actual.size, `Runtime 未找到 interface ${interfaceName}`).toBeGreaterThan(0)
      for (const field of expectedFields) {
        expect(actual, `Runtime ${interfaceName} 缺少字段 ${field}`).toContain(field)
      }
    }
  })

  it('Editor 与 Runtime 的 ComponentPreviewSchema 字段集合必须一致', () => {
    const editorFields = extractInterfaceFields(readFileSync(editorTsPath, 'utf-8'), 'ComponentPreviewSchema')
    const runtimeFields = extractInterfaceFields(readFileSync(runtimeTsPath, 'utf-8'), 'ComponentPreviewSchema')
    expect([...editorFields].sort()).toEqual([...runtimeFields].sort())
    expect(editorFields).toEqual(new Set(['props', 'slots', 'mocks', 'presets']))
  })
})
