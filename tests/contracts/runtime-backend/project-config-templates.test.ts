/**
 * 文件功能：校验 Backend 与 Runtime 均携带各自需要的项目默认配置模板文件。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const projectConfigTemplateNames = {
  'app.config.yaml': ['app:'],
  'icons.config.yaml': ['static_icons:'],
  'themes.config.yaml': ['themes:', 'default:'],
} as const

function readNormalizedText(path: string) {
  return readFileSync(path, 'utf-8').replace(/\r\n/g, '\n').trimEnd()
}

describe('runtime-backend project config templates contract', () => {
  it('Backend 和 Runtime 应分别保留可读取的默认配置模板', () => {
    for (const [fileName, requiredMarkers] of Object.entries(projectConfigTemplateNames)) {
      const backendTemplate = readNormalizedText(resolve(process.cwd(), 'backend/app/config_templates', fileName))
      const runtimeFixture = readNormalizedText(resolve(process.cwd(), 'runtime/public/config', fileName))

      expect(backendTemplate.length).toBeGreaterThan(0)
      expect(runtimeFixture.length).toBeGreaterThan(0)
      for (const marker of requiredMarkers) {
        expect(backendTemplate).toContain(marker)
        expect(runtimeFixture).toContain(marker)
      }
    }
  })
})
