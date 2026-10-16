/** 文件功能：从 model_view_options.v1.json 生成 Editor/Runtime 共同使用的展示参数类型。 */
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { renderTypes } from './schema-types.mjs'

const root = fileURLToPath(new URL('../../', import.meta.url))
const document = JSON.parse(readFileSync(resolve(root, 'backend/app/core/model_view_options.v1.json'), 'utf8'))
const names = document['x-typescript-types']
const schemas = Object.fromEntries(Object.entries(names).map(([ref, name]) => [name, ref === '#' ? document : document.$defs[ref.split('/').pop()]]))
const source = '/** 文件功能：由 model_view_options.v1.json 生成的共享类型，勿手改；运行 pnpm run codegen:model-view-types。 */\n\n'
  + renderTypes(schemas, ref => {
    if (!names[ref]) throw new Error(`未命名的 modelViewOptions 引用：${ref}`)
    return names[ref]
  })
const outputs = process.argv.slice(2)
for (const target of outputs.length ? outputs : ['editor/src/types/model-view-options.generated.ts', 'runtime/src/core/shared/model-view-options.generated.ts']) {
  writeFileSync(resolve(root, target), source, 'utf8')
}
