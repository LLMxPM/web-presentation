/** 文件功能：将仓库使用的 JSON Schema/OpenAPI 结构确定性转换为 TypeScript 类型。 */

/** 转换类型表达式；引用解析由调用方提供，遇到未支持的结构显式失败。 */
export function schemaType(schema, referenceName = ref => ref.split('/').pop()) {
  if (schema === true) return 'unknown'
  if (schema === false) return 'never'
  if (!schema || typeof schema !== 'object') throw new Error('Schema 必须是对象或布尔值')
  if (schema.$ref) return referenceName(schema.$ref)
  if ('const' in schema) return JSON.stringify(schema.const)
  if (schema.enum) return schema.enum.map(value => JSON.stringify(value)).join(' | ')
  if (schema.anyOf || schema.oneOf) return (schema.anyOf || schema.oneOf).map(value => `(${schemaType(value, referenceName)})`).join(' | ')
  if (schema.allOf) return schema.allOf.map(value => `(${schemaType(value, referenceName)})`).join(' & ')
  if (Array.isArray(schema.type)) return schema.type.map(type => schemaType({ ...schema, type }, referenceName)).join(' | ')
  if (schema.type === 'array') return `(${schemaType(schema.items ?? {}, referenceName)})[]`
  if (schema.type === 'object' || schema.properties) {
    const required = new Set(schema.required || [])
    const fields = Object.entries(schema.properties || {}).map(([name, value]) =>
      `  ${JSON.stringify(name)}${required.has(name) ? '' : '?'}: ${schemaType(value, referenceName)}`)
    const additional = schema.additionalProperties
    if (additional !== false) {
      const valueType = schemaType(typeof additional === 'object' ? additional : {}, referenceName)
      // 无具名属性时采用 Record；开放对象有具名属性时保留索引约束。
      if (!fields.length) return `Record<string, ${valueType}>`
      if (additional !== undefined) fields.push(`  [key: string]: ${valueType}`)
    }
    return `{\n${fields.join('\n')}\n}`
  }
  if (schema.type === 'integer' || schema.type === 'number') return 'number'
  if (['string', 'boolean', 'null'].includes(schema.type)) return schema.type
  if (schema.type) throw new Error(`未支持的 Schema 类型：${schema.type}`)
  return 'unknown'
}

/** 按名称排序生成类型；Schema 变化直接改变生成文本，可供 CI 做完整差异检查。 */
export function renderTypes(schemas, referenceName) {
  return Object.keys(schemas).sort().map(name => {
    if (!/^[A-Za-z_$][\w$]*$/.test(name)) throw new Error(`非法 TypeScript 类型名：${name}`)
    return `export type ${name} = ${schemaType(schemas[name], referenceName)}\n`
  }).join('\n')
}
