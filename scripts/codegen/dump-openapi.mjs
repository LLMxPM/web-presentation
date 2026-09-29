/**
 * 文件功能：离线导出 Backend FastAPI OpenAPI 文档，供 Editor 类型 codegen 使用。
 * 用法：node scripts/codegen/dump-openapi.mjs [outputPath]
 */

import { spawnSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const outputPath = resolve(process.argv[2] || join(repoRoot, 'editor/src/types/openapi.json'))

const pythonSnippet = `
import json, sys
from app.main import app
print(json.dumps(app.openapi(), ensure_ascii=False))
`

const result = spawnSync(
  'uv',
  ['run', '--project', 'backend', 'python', '-c', pythonSnippet],
  {
    cwd: repoRoot,
    encoding: 'utf-8',
    maxBuffer: 32 * 1024 * 1024,
  },
)

if (result.status !== 0) {
  console.error('导出 OpenAPI 失败：', result.stderr || result.stdout)
  process.exit(result.status || 1)
}

const openapi = JSON.parse(result.stdout)
mkdirSync(dirname(outputPath), { recursive: true })
writeFileSync(outputPath, `${JSON.stringify(openapi, null, 2)}\n`, 'utf-8')
console.log(`OpenAPI 已写入 ${outputPath}`)
console.log(`paths=${Object.keys(openapi.paths || {}).length} schemas=${Object.keys(openapi.components?.schemas || {}).length}`)
