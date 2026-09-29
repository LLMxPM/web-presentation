/** 文件功能：检查完整 API 生成类型及核心实体消费，覆盖必填、类型、枚举与嵌套漂移。 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { renderTypes } from '../../scripts/codegen/schema-types.mjs'
import { checkTypes } from './schema-typecheck-helper'

/** 从根仓读取契约文本并统一换行。 */
function read(path: string): string {
  return readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
}
const document = JSON.parse(read('editor/src/types/openapi.json'))
const generated = read('editor/src/types/api.generated.ts')

describe('API 完整契约与消费', () => {
  it('所有生成类型与 OpenAPI 一致，CI 另行从 Backend 重导源文件', () => {
    expect(generated.slice(generated.indexOf('export type '))).toBe(renderTypes(document.components.schemas))
  })
  it('核心实体必须引用生成类型，缺少别名立即失败', () => {
    const source = read('editor/src/types/api.ts')
    for (const name of ['AuthUser', 'PreviewSizePreset', 'WorkspaceItem', 'ProjectItem', 'PageItem', 'WorkspaceComponentItem', 'WorkspaceStyleItem', 'WorkspaceThemeItem', 'AssetResponse', 'PreviewArtifactResponse']) {
      expect(source).toContain(`export type ${name} = GeneratedApi.${name}`)
      expect(document.components.schemas).toHaveProperty(name)
    }
  })
  it('字段类型、必填、枚举及嵌套修改都会改变生成物', () => {
    const source = { Sample: { type: 'object', properties: { name: { type: 'string' }, mode: { enum: ['a', 'b'] }, nested: { type: 'array', items: { type: 'number' } } } } }
    const baseline = renderTypes(source)
    for (const mutate of [
      (schema: any) => { schema.properties.name.type = 'number' },
      (schema: any) => { schema.required = ['name'] },
      (schema: any) => { schema.properties.mode.enum = ['a'] },
      (schema: any) => { schema.properties.nested.items.type = 'boolean' },
    ]) {
      const changed = structuredClone(source)
      mutate(changed.Sample)
      expect(renderTypes(changed)).not.toBe(baseline)
    }
  })
  it('生成器保留真实消费所需的必填、枚举、嵌套及 null 语义', () => {
    const types = renderTypes({ Sample: { type: 'object', required: ['name', 'mode', 'nested'], properties: { name: { type: 'string' }, mode: { enum: ['a', 'b'] }, nested: { type: 'array', items: { type: 'number' } }, nullable: { anyOf: [{ type: 'string' }, { type: 'null' }] } } } })
    const valid = `const value: Sample = { name: 'x', mode: 'a', nested: [1], nullable: null }`
    expect(checkTypes(types + valid)).toEqual([])
    for (const value of ["{ mode: 'a', nested: [] }", "{ name: 1, mode: 'a', nested: [] }", "{ name: 'x', mode: 'c', nested: [] }", "{ name: 'x', mode: 'a', nested: ['bad'] }"]) {
      expect(checkTypes(types + `const value: Sample = ${value}`)).not.toEqual([])
    }
  })
})
