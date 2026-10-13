/**
 * 文件用途：PPTX 导出 S5 阶段专项测试（主题色彩与字体槽位映射、母版公共背景与页码策略）。
 */

import { describe, expect, it } from 'vitest'
import { strFromU8, unzipSync } from 'fflate'
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

    it('传入 masterProps 后实际页面继承指定母版背景', async () => {
      const masterProps = {
        title: 'CUSTOM_MASTER',
        background: { color: 'FAFAFA' },
      }

      const pptx = writer.createPresentation('测试母版', undefined, undefined, masterProps)
      pptx.addSlide({ masterName: 'CUSTOM_MASTER' })
      const files = unzipSync(await writer.generatePresentationBytes(pptx))
      expect(strFromU8(files['ppt/slideLayouts/slideLayout2.xml'])).toContain('<a:srgbClr val="FAFAFA"')
      expect(strFromU8(files['ppt/slides/_rels/slide1.xml.rels'])).toContain('slideLayout2.xml')
    })

    it('真实产物写入主题色，并将一致的不透明背景提升到实际母版', async () => {
      const pptx = writer.createPresentation('产物复核', undefined, {
        headFontFace: 'Microsoft YaHei', bodyFontFace: 'Microsoft YaHei', colors: { accent1: '123456', primary: '234567' },
      })
      pptx.addSlide().background = { color: 'ABCDEF' }
      pptx.addSlide().background = { color: 'ABCDEF' }
      const files = unzipSync(await writer.generatePresentationBytes(pptx))
      const theme = strFromU8(files['ppt/theme/theme1.xml'])
      expect(theme).toContain('<a:accent1><a:srgbClr val="123456"/></a:accent1>')
      expect(theme).toContain('<a:dk1><a:srgbClr val="234567"/></a:dk1>')
      expect(strFromU8(files['ppt/slideMasters/slideMaster1.xml'])).toContain('<a:srgbClr val="ABCDEF"')
      expect(strFromU8(files['ppt/slideLayouts/slideLayout1.xml'])).not.toContain('<p:bg>')
      expect(strFromU8(files['ppt/slides/slide1.xml'])).not.toContain('<p:bg>')
      expect(strFromU8(files['ppt/slides/slide2.xml'])).not.toContain('<p:bg>')
    })

    it('不同或半透明背景保留在原页，避免母版改变混合结果', async () => {
      for (const backgrounds of [
        [{ color: '123456' }, { color: 'ABCDEF' }],
        [{ color: '123456', transparency: 50 }, { color: '123456', transparency: 50 }],
      ]) {
        const pptx = writer.createPresentation('背景复核')
        backgrounds.forEach(background => { pptx.addSlide().background = background })
        const files = unzipSync(await writer.generatePresentationBytes(pptx))
        expect(strFromU8(files['ppt/slides/slide1.xml'])).toContain('<p:bg>')
        expect(strFromU8(files['ppt/slides/slide2.xml'])).toContain('<p:bg>')
      }
    })

    it('自定义布局已有背景时不提升相同页背景，避免布局底色覆盖母版', async () => {
      const pptx = writer.createPresentation('布局背景复核', undefined, undefined, {
        title: 'CUSTOM_MASTER', background: { color: 'FAFAFA' },
      })
      for (let index = 0; index < 2; index++) {
        pptx.addSlide({ masterName: 'CUSTOM_MASTER' }).background = { color: '123456' }
      }
      const files = unzipSync(await writer.generatePresentationBytes(pptx))
      expect(strFromU8(files['ppt/slideLayouts/slideLayout2.xml'])).toContain('<a:srgbClr val="FAFAFA"')
      for (const index of [1, 2]) {
        expect(strFromU8(files[`ppt/slides/slide${index}.xml`])).toContain('<a:srgbClr val="123456"')
      }
    })
  })
})
