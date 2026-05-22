/**
 * 文件功能：校验 runtime 对接文档中仍声明 preview artifact manifest/config-bundle/modules 三个核心接口。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const docPath = resolve(process.cwd(), 'runtime/docs/integration/backend-api.md')
const backendApiDoc = readFileSync(docPath, 'utf-8')

describe('runtime-backend release artifact contract', () => {
  it('应继续声明 manifest/config-bundle/modules 三个内部接口', () => {
    expect(backendApiDoc).toContain('/internal/runtime/preview-artifacts/{artifact_id}/manifest')
    expect(backendApiDoc).toContain('/internal/runtime/preview-artifacts/{artifact_id}/config-bundle')
    expect(backendApiDoc).toContain('/internal/runtime/preview-artifacts/{artifact_id}/modules')
  })
})
