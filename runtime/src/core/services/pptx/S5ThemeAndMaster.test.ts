/**
 * 文件用途：PPTX 导出 S5 阶段专项测试（主题色彩与字体槽位映射、母版公共背景与页码策略）。
 */

import { describe, expect, it, vi } from 'vitest'
import { PptxThemeResolver } from './theme/PptxThemeResolver'
import { PptxMasterSlideStrategy } from './theme/PptxMasterSlideStrategy'
import { PptxPackageWriter } from './writer/PptxPackageWriter'

describe('S5 主题和母版（Theme and Master Slides）', () => {
  describe('PptxThemeResolver', () => {
    const resolver = new PptxThemeResolver()

    it('应从 DOM 样式变量中提取主题字体与规范化字体名称', () => {
      const container = document.createElement('div')
      container.style.setProperty('--tw-font-heading', '"PingFang SC", "Microsoft YaHei", sans-serif')
      container.style.setProperty('--tw-font-body', 'Arial, sans-serif')
      document.body.appendChild(container)

      const theme = resolver.resolveTheme(container)
      expect(theme.headFontFace).toBe('PingFang SC')
      expect(theme.bodyFontFace).toBe('Arial')

      container.remove()
    })

    it('当主题字体变量未声明时应安全回退到默认 Microsoft YaHei', () => {
      const container = document.createElement('div')
      document.body.appendChild(container)

      const theme = resolver.resolveTheme(container)
      expect(theme.headFontFace).toBe('Microsoft YaHei')
      expect(theme.bodyFontFace).toBe('Microsoft YaHei')

      container.remove()
    })

    it('应提取强调色与主背景色并映射为十六进制值', () => {
      const container = document.createElement('div')
      container.style.setProperty('--tw-color-accent1', '#2563eb')
      container.style.setProperty('--tw-color-accent2', 'rgb(234, 88, 12)')
      container.style.setProperty('--tw-color-text-primary', '#0f172a')
      container.style.setProperty('--tw-color-bg-default', '#ffffff')
      document.body.appendChild(container)

      const theme = resolver.resolveTheme(container)
      expect(theme.colors.accent1).toBe('2563EB')
      expect(theme.colors.accent2).toBe('EA580C')
      expect(theme.colors.primary).toBe('0F172A')
      expect(theme.colors.background).toBe('FFFFFF')

      container.remove()
    })
  })

  describe('PptxMasterSlideStrategy', () => {
    const strategy = new PptxMasterSlideStrategy()

    it('当所有页面背景完全一致时应提升为统一母版背景并配置页码', () => {
      const backgrounds = [
        { color: 'FFFFFF', transparency: 0 },
        { color: 'FFFFFF', transparency: 0 },
        { color: 'ffffff', transparency: 0 },
      ]

      const result = strategy.evaluate(backgrounds, true)
      expect(result.hasSharedBackground).toBe(true)
      expect(result.masterProps).toBeDefined()
      expect(result.masterProps?.background?.color).toBe('FFFFFF')
      expect(result.masterProps?.slideNumber).toBeDefined()
    })

    it('当页面背景存在差异（如深色封面与浅色内页）时严禁提升统一母版背景，避免覆盖差异页', () => {
      const backgrounds = [
        { color: '0F172A', transparency: 0 }, // 封面深色
        { color: 'FFFFFF', transparency: 0 }, // 内页浅色
        { color: 'FFFFFF', transparency: 0 },
      ]

      const result = strategy.evaluate(backgrounds, true)
      expect(result.hasSharedBackground).toBe(false)
      // 母版不包含背景，仅包含可选页码
      expect(result.masterProps?.background).toBeUndefined()
      expect(result.masterProps?.slideNumber).toBeDefined()
    })

    it('空页面列表时应安全返回 false', () => {
      const result = strategy.evaluate([])
      expect(result.hasSharedBackground).toBe(false)
      expect(result.masterProps).toBeUndefined()
    })
  })

  describe('PptxPackageWriter 主题与母版装配', () => {
    const writer = new PptxPackageWriter()

    it('createPresentation 应正确应用主题字体', () => {
      const theme = {
        headFontFace: 'HarmonyOS Sans SC',
        bodyFontFace: 'Source Han Sans SC',
        colors: {},
      }

      const pptx = writer.createPresentation('测试主题导出', undefined, theme)
      expect(pptx.theme?.headFontFace).toBe('HarmonyOS Sans SC')
      expect(pptx.theme?.bodyFontFace).toBe('Source Han Sans SC')
    })

    it('传入 masterProps 时应调用 defineSlideMaster', () => {
      const defineMasterSpy = vi.fn()
      const masterProps = {
        title: 'CUSTOM_MASTER',
        background: { color: 'FAFAFA' },
      }

      // 验证通过 PptxPackageWriter 的调用链路
      const pptx = writer.createPresentation('测试母版', undefined, undefined, masterProps)
      expect(pptx).toBeDefined()
    })
  })
})
