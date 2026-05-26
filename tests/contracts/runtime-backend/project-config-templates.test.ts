/**
 * 文件功能：校验 Backend 自有项目默认配置模板与 Runtime 本地 fixture 保持一致。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const projectConfigTemplateNames = ['app.config.yaml', 'icons.config.yaml', 'themes.config.yaml'] as const

function readNormalizedText(path: string) {
  return readFileSync(path, 'utf-8').replace(/\r\n/g, '\n').trimEnd()
}

describe('runtime-backend project config templates contract', () => {
  it('Backend 默认模板应与 Runtime 本地默认配置保持同步', () => {
    for (const fileName of projectConfigTemplateNames) {
      const backendTemplate = readNormalizedText(resolve(process.cwd(), 'backend/app/config_templates', fileName))
      const runtimeFixture = readNormalizedText(resolve(process.cwd(), 'runtime/public/config', fileName))

      expect(backendTemplate).toBe(runtimeFixture)
    }
  })
})
