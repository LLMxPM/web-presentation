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

const lightblueThemeMarkers = [
  'name: 明亮商务蓝',
  'description: 明亮、专业、克制的商务主题，适合汇报、方案和数据解读。',
  'primary: "#20364D"',
  'secondary: "#627487"',
  'invert: "#FFFFFF"',
  'default: "#FFFFFF"',
  'invert: "#173B5C"',
  'default: "#D8E2EC"',
  'subtle: "#EDF2F6"',
  'default: "#1B6CA8"',
  'hover: "#0F4C81"',
  'visited: "#5E6CB5"',
  '- "#2D7BB8"',
  '- "#159A8C"',
  '- "#D39A24"',
  '- "#E07B67"',
  '- "#6C73B8"',
  '- "#6C9BB8"',
] as const

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

  it('Backend 与 Runtime 的 lightblue 默认主题应保持同一套商务色板', () => {
    const backendTemplate = readNormalizedText(resolve(process.cwd(), 'backend/app/config_templates/themes.config.yaml'))
    const runtimeFixture = readNormalizedText(resolve(process.cwd(), 'runtime/public/config/themes.config.yaml'))

    for (const marker of lightblueThemeMarkers) {
      expect(backendTemplate).toContain(marker)
      expect(runtimeFixture).toContain(marker)
    }
  })
})
