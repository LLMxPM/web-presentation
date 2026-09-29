/** 文件功能：将已导出的 Backend OpenAPI 生成为 Editor 实际消费的类型文件。 */
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { renderTypes } from './schema-types.mjs'

const root = fileURLToPath(new URL('../../', import.meta.url))
const input = resolve(process.argv[2] || `${root}/editor/src/types/openapi.json`)
const output = resolve(process.argv[3] || `${root}/editor/src/types/api.generated.ts`)
const schemas = JSON.parse(readFileSync(input, 'utf8')).components.schemas
const content = '/** 文件功能：由 Backend OpenAPI 生成的 API 类型，勿手改；运行 pnpm run codegen:editor-api。 */\n\n'
  + renderTypes(schemas)
writeFileSync(output, content, 'utf8')
console.log(`已生成 ${Object.keys(schemas).length} 个 API 类型`)
