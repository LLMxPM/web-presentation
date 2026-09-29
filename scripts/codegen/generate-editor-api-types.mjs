/**
 * 文件功能：从 OpenAPI components.schemas 生成 Editor TypeScript 接口类型。
 * 用法：node scripts/codegen/generate-editor-api-types.mjs [openapiPath] [outputPath]
 */

import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const openapiPath = resolve(process.argv[2] || join(repoRoot, 'editor/src/types/openapi.json'))
const outputPath = resolve(process.argv[3] || join(repoRoot, 'editor/src/types/api.generated.ts'))

if (!existsSync(openapiPath)) {
  console.error(`OpenAPI 文件不存在：${openapiPath}`)
  console.error('先运行：node scripts/codegen/dump-openapi.mjs')
  process.exit(1)
}

const openapi = JSON.parse(readFileSync(openapiPath, 'utf-8'))
const schemas = openapi.components?.schemas || {}

/**
 * 把 OpenAPI schema 转为 TypeScript 类型字符串。
 */
function tsType(schema, depth = 0) {
  if (!schema || typeof schema !== 'object') {
    return 'unknown'
  }
  if (schema.$ref) {
    const name = schema.$ref.split('/').pop()
    return name
  }
  if (schema.anyOf || schema.oneOf) {
    const variants = schema.anyOf || schema.oneOf
    return variants.map(v => tsType(v, depth)).join(' | ')
  }
  if (schema.allOf) {
    return schema.allOf.map(v => tsType(v, depth)).join(' & ')
  }
  if (schema.enum) {
    return schema.enum.map(v => JSON.stringify(v)).join(' | ')
  }
  const t = schema.type
  if (t === 'array') {
    const item = tsType(schema.items || {}, depth + 1)
    return item.includes(' ') || item.includes('|') || item.includes('&') ? `(${item})[]` : `${item}[]`
  }
  if (t === 'object' || schema.properties) {
    if (!schema.properties || Object.keys(schema.properties).length === 0) {
      if (schema.additionalProperties && typeof schema.additionalProperties === 'object') {
        return `Record<string, ${tsType(schema.additionalProperties, depth + 1)}>`
      }
      return 'Record<string, unknown>'
    }
    const required = new Set(schema.required || [])
    const lines = Object.entries(schema.properties).map(([key, prop]) => {
      const optional = required.has(key) ? '' : '?'
      return `  ${JSON.stringify(key)}${optional}: ${tsType(prop, depth + 1)}`
    })
    return `{\n${lines.join('\n')}\n}`
  }
  if (t === 'string') return 'string'
  if (t === 'number' || t === 'integer') return 'number'
  if (t === 'boolean') return 'boolean'
  if (t === 'null') return 'null'
  return 'unknown'
}

const lines = [
  '/**',
  ' * 文件功能：由 OpenAPI 生成的 Editor API 类型镜像（生成物，勿手改）。',
  ' * ',
  ' * 生成命令：pnpm run codegen:editor-api',
  ' * 事实源：Backend /openapi.json → scripts/codegen/generate-editor-api-types.mjs',
  ' */',
  '',
  '/* eslint-disable */',
  '',
]

const schemaNames = Object.keys(schemas).sort()
for (const name of schemaNames) {
  const schema = schemas[name]
  const comment = schema.description ? `/** ${schema.description.replace(/\*\//g, '*\\/')} */\n` : ''
  // 顶层对象 → interface；其它 → type alias
  if (schema.type === 'object' && schema.properties) {
    const required = new Set(schema.required || [])
    const body = Object.entries(schema.properties).map(([key, prop]) => {
      const optional = required.has(key) ? '' : '?'
      return `  ${JSON.stringify(key)}${optional}: ${tsType(prop, 1)}`
    })
    lines.push(`${comment}export interface ${name} {\n${body.join('\n')}\n}`)
  } else {
    lines.push(`${comment}export type ${name} = ${tsType(schema)}`)
  }
  lines.push('')
}

lines.push(`export type GeneratedApiSchemaName = ${schemaNames.map(n => JSON.stringify(n)).join(' | ') || 'never'}`)
lines.push('')
lines.push(`export const GENERATED_API_SCHEMA_NAMES: readonly GeneratedApiSchemaName[] = [`)
for (const name of schemaNames) {
  lines.push(`  ${JSON.stringify(name)},`)
}
lines.push('] as const')
lines.push('')

writeFileSync(outputPath, lines.join('\n'), 'utf-8')
console.log(`已生成 ${outputPath}（${schemaNames.length} 个 schema）`)
