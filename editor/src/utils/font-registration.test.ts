/**
 * 文件功能：验证字体注册推断工具的字体族、字重、样式与格式推断及默认注册组装逻辑。
 */
import { describe, expect, it } from 'vitest'

import {
  buildDefaultFontRegistration,
  inferFontFamily,
  inferFontFormat,
  inferFontStyle,
  inferFontWeight,
} from '@/utils/font-registration'

describe('inferFontFamily', () => {
  it('应剥离字重后缀，使同族不同字重归并', () => {
    expect(inferFontFamily('SourceHanSans-Bold.woff2')).toBe('SourceHanSans')
    expect(inferFontFamily('SourceHanSans-Regular.otf')).toBe('SourceHanSans')
    expect(inferFontFamily('Roboto_Light.ttf')).toBe('Roboto')
  })

  it('应剥离组合的字重与样式后缀', () => {
    expect(inferFontFamily('SourceHanSans-BoldItalic.ttf')).toBe('SourceHanSans')
    expect(inferFontFamily('Inter-Italic-Variable.woff2')).toBe('Inter')
  })

  it('无后缀时应保留原始基础名', () => {
    expect(inferFontFamily('MyFont.woff2')).toBe('MyFont')
  })

  it('仅由后缀构成时应保留该词避免空族名', () => {
    expect(inferFontFamily('Bold.woff2')).toBe('Bold')
  })
})

describe('inferFontWeight', () => {
  it('应将字重后缀映射为 CSS 数值', () => {
    expect(inferFontWeight('SourceHanSans-Bold.woff2')).toBe('700')
    expect(inferFontWeight('SourceHanSans-Thin.woff2')).toBe('100')
    expect(inferFontWeight('SourceHanSans-SemiBold.woff2')).toBe('600')
    expect(inferFontWeight('SourceHanSans-ExtraBold.woff2')).toBe('800')
  })

  it('可变字体应返回全字重范围', () => {
    expect(inferFontWeight('Inter-Variable.woff2')).toBe('100 900')
    expect(inferFontWeight('Inter-VF.woff2')).toBe('100 900')
  })

  it('无字重信息时应回退 400', () => {
    expect(inferFontWeight('MyFont.woff2')).toBe('400')
    expect(inferFontWeight('SourceHanSans-Regular.woff2')).toBe('400')
  })
})

describe('inferFontStyle', () => {
  it('命中斜体标记时应返回 italic', () => {
    expect(inferFontStyle('SourceHanSans-Italic.woff2')).toBe('italic')
    expect(inferFontStyle('SourceHanSans-Oblique.woff2')).toBe('italic')
  })

  it('无斜体标记时应返回 normal', () => {
    expect(inferFontStyle('SourceHanSans-Bold.woff2')).toBe('normal')
  })
})

describe('inferFontFormat', () => {
  it('应根据扩展名推断格式，未知时回退 woff2', () => {
    expect(inferFontFormat('a.ttf')).toBe('ttf')
    expect(inferFontFormat('a.otf')).toBe('otf')
    expect(inferFontFormat('a.woff')).toBe('woff')
    expect(inferFontFormat('a.bin')).toBe('woff2')
  })
})

describe('buildDefaultFontRegistration', () => {
  it('应组装字体族名与推断的字重、样式、格式', () => {
    expect(buildDefaultFontRegistration('SourceHanSans-Bold.woff2')).toEqual({
      family_name: 'SourceHanSans',
      font_format: 'woff2',
      font_weight: '700',
      font_style: 'normal',
      font_display: 'swap',
    })
  })

  it('应识别可变字体与斜体组合', () => {
    expect(buildDefaultFontRegistration('Inter-Italic-Variable.woff2')).toEqual({
      family_name: 'Inter',
      font_format: 'woff2',
      font_weight: '100 900',
      font_style: 'italic',
      font_display: 'swap',
    })
  })
})
