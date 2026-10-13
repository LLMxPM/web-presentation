/**
 * 文件用途：提供 PptxSlideIR 的收集适配器与向 PptxSlideLike 投射图元的投影器。
 */

import type {
  PptxGradientFillInstruction,
  PptxSlideLike,
} from '@/core/services/pptx/PPTXDomConverter.types'
import type {
  PptxSlideBackgroundIR,
  PptxSlideIR,
  PptxSlidePrimitiveIR,
} from '@/core/services/pptx/ir/PptxSlideIR.types'

/**
 * 支持写入演讲者备注的 Slide 扩展接口。
 */
export interface PptxNotesCapableSlideLike extends PptxSlideLike {
  addNotes?: (notes: string) => unknown
}

/**
 * 创建一个用于记录图元到内存数组的虚拟 Slide 收集器。
 * 约束：让现有的 Text/Media/Table/Gradient 提取器无需感知底层是真实 PptxGenJS Slide 还是 IR 收集器。
 * @param primitives 图元收集数组
 * @returns 虚拟 Slide 对象与背景读取函数
 */
export function createIrSlideCollector(primitives: PptxSlidePrimitiveIR[]): {
  slide: PptxSlideLike
  getBackground: () => PptxSlideBackgroundIR | undefined
} {
  let background: PptxSlideBackgroundIR | undefined

  const slide: PptxSlideLike = {
    addText(text, options) {
      const id = typeof options?.objectName === 'string' && options.objectName
        ? String(options.objectName)
        : `primitive-${primitives.length + 1}`
      primitives.push({
        kind: 'text',
        id,
        text,
        options,
      })
    },
    addShape(shapeType, options) {
      const id = typeof options?.objectName === 'string' && options.objectName
        ? String(options.objectName)
        : `primitive-${primitives.length + 1}`
      primitives.push({
        kind: 'shape',
        id,
        shapeType,
        options,
      })
    },
    addImage(options) {
      const id = typeof options?.objectName === 'string' && options.objectName
        ? String(options.objectName)
        : `primitive-${primitives.length + 1}`
      primitives.push({
        kind: 'image',
        id,
        options,
      })
    },
    addTable(rows, options) {
      const id = typeof options?.objectName === 'string' && options.objectName
        ? String(options.objectName)
        : `primitive-${primitives.length + 1}`
      primitives.push({
        kind: 'table',
        id,
        rows,
        options,
      })
    },
    get background() {
      return background
    },
    set background(value: unknown) {
      if (
        value &&
        typeof value === 'object' &&
        'color' in value &&
        typeof (value as { color?: unknown }).color === 'string'
      ) {
        const record = value as { color: string; transparency?: number }
        background = {
          color: record.color,
          transparency: typeof record.transparency === 'number' ? record.transparency : 0,
        }
      }
    },
  }

  return {
    slide,
    getBackground: () => background,
  }
}

/**
 * 将纯数据 PptxSlideIR 投射到目标 PptxSlideLike（真实 PptxGenJS Slide 或测试 Mock）。
 * @param slideIR 单页 PPTX 中间表示
 * @param slide 目标 Slide 对象
 * @param gradientFillCollector 可选的外部渐变指令收集器
 */
export function projectSlideIRToSlide(
  slideIR: PptxSlideIR,
  slide: PptxNotesCapableSlideLike,
  gradientFillCollector?: (instruction: PptxGradientFillInstruction) => void,
): void {
  if (slideIR.speakerNotes && typeof slide.addNotes === 'function') {
    slide.addNotes(slideIR.speakerNotes)
  }

  if (slideIR.background) {
    slide.background = {
      color: slideIR.background.color,
      transparency: slideIR.background.transparency,
    }
  }

  for (const primitive of slideIR.primitives) {
    switch (primitive.kind) {
      case 'text':
        slide.addText(primitive.text, primitive.options)
        break
      case 'shape':
        slide.addShape(primitive.shapeType, primitive.options)
        break
      case 'image':
        slide.addImage(primitive.options)
        break
      case 'table':
        slide.addTable(primitive.rows, primitive.options)
        break
    }
  }

  if (gradientFillCollector) {
    for (const instruction of slideIR.gradientFills) {
      gradientFillCollector(instruction)
    }
  }
}
