/** 文件功能：用同一组正反例验证 Editor/Runtime 生成类型，并与 Backend 共用样本。 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { renderTypes } from '../../scripts/codegen/schema-types.mjs'
import { checkTypes } from './schema-typecheck-helper'

/** 从根仓读取文本；只规范换行，不屏蔽结构差异。 */
function read(path: string): string {
  return readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
}
const document = JSON.parse(read('backend/app/core/component_preview_schema.v1.json'))
const names = document['x-typescript-types'] as Record<string, string>
const schemas = Object.fromEntries(Object.entries(names).map(([ref, name]) => [name, ref === '#' ? document : document.$defs[ref.split('/').pop()!]]))
const expected = renderTypes(schemas, (ref: string) => names[ref])
const cases = JSON.parse(read('tests/fixtures/preview-schema-cases.json')) as Array<{name: string; valid: boolean; value: unknown}>

describe('previewSchema 三端契约', () => {
  for (const path of ['editor/src/types/component-preview', 'runtime/src/core/shared/runtime-preview']) {
    it(`${path} 消费完整生成物并通过正反例语义检查`, () => {
      const directory = path.slice(0, path.lastIndexOf('/'))
      const generated = read(`${directory}/component-preview.generated.ts`)
      expect(generated.slice(generated.indexOf('export type '))).toBe(expected)
      expect(read(`${path}.ts`)).toContain("from './component-preview.generated'")
      const source = `import type { ComponentPreviewSchema } from '../../${directory}/component-preview.generated'\n` + cases.map((sample, index) => `${sample.valid ? '' : '// @ts-expect-error ' + sample.name + '\n'}const sample${index}: ComponentPreviewSchema = ${JSON.stringify(sample.value)}`).join('\n')
      expect(checkTypes(source)).toEqual([])
    })
  }
})
