/** 文件功能：按真实字体差值验证 PPTX 符号、数字与空格补偿，覆盖累计误差、逐行预算及总量上限。 */
import { describe, expect, it } from 'vitest'
import { calculateTextTypographyWidthGuard } from './TextTypographyWidthGuard'

const FONT_SIZE_PX = 22.5
const INCH_PER_PX = 13.333 / 1920

/** 将字体审计使用的设计像素换算为导出英寸，再还原预算用于对拍。 */
function budgetPixels(text: string, widthPixels = 650, isTextShape = false): number {
  return calculateTextTypographyWidthGuard(text, FONT_SIZE_PX * INCH_PER_PX, widthPixels * INCH_PER_PX, isTextShape) / INCH_PER_PX
}

describe('PPTX 字体替换宽度预算', () => {
  it.each([
    ['“”', 28.04], ['‘’', 34.70], ['——', 3.61], ['–‐‑‒-', 5.23],
    ['∶', 14.54], ['↗', 6.03], ['→←', 6.18], ['∑∏√∞∫', 6.34],
    ['%‰', 3.92], ['°′″', 2.28], ['.,;:!?/\\|<>~', 10.61],
    ['·•∙●▪', 3.56], ['«»‹›', 3.54], ['$¥€£¢', 5.35],
    ['©®™№#&@', 11.10],
  ])('符号 %s 的预算覆盖当前系统字体栈到微软雅黑的实测差值', (text, measuredDifference) => {
    expect(budgetPixels(text)).toBeGreaterThanOrEqual(measuredDifference)
  })

  it('395 页的引号、破折号、数字与空格累计预算覆盖约 42px 差值', () => {
    const text = '核心动作是“配对”——把 100 个不同的数，变成 50 组相同的和。'
    expect(budgetPixels(text)).toBeGreaterThan(42)
    expect(budgetPixels(text)).toBeLessThanOrEqual(FONT_SIZE_PX * 2.5)
  })

  it('数字和空格的补偿能够累积，覆盖 100 与 50 的约 5.9px 差值', () => {
    expect(budgetPixels('100 50')).toBeGreaterThan(5.33 + 0.49)
    expect(budgetPixels('100 50')).toBeGreaterThan(budgetPixels('100'))
  })

  it('各行先合并符号和数字预算，再取最大行，不把不同文字行的误差相加', () => {
    expect(budgetPixels('“引用”\r\n100 50')).toBe(budgetPixels('“引用”'))
    expect(budgetPixels('“引用” 100 50')).toBeGreaterThan(budgetPixels('“引用”\n100 50'))
  })

  it('大量符号和数字仍受字号及文本框比例的共同上限约束', () => {
    expect(budgetPixels('‘’100 '.repeat(100))).toBeCloseTo(FONT_SIZE_PX * 2.5)
    expect(budgetPixels('‘’100 '.repeat(100), 60)).toBeCloseTo(60 * 0.15)
    expect(budgetPixels('‘’100 '.repeat(100), 60, true)).toBeCloseTo(60 * 0.1)
  })

  it('普通中文和宽度稳定的全角标点不增加这层字体差值预算', () => {
    expect(budgetPixels('普通中文，。；：？！')).toBe(0)
  })
})
