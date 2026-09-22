/**
 * 文件用途：提供 PPTX DOM 转换器测试共用的转换入口、slide mock 与资源辅助工具。
 */

import { vi } from 'vitest'
import { PPTXDomConverter, type PptxGradientFillInstruction } from './PPTXDomConverter'
import type { PptxTextContentLike } from './PPTXDomConverter.types'

type CaptureElementAsPng = (element: HTMLElement) => Promise<string>

const shapeTypes = {
  rect: 'rect',
  roundRect: 'roundRect',
  ellipse: 'ellipse',
  line: 'line',
}

/**
 * 执行转换。
 * @param slide slide mock
 * @param captureElementAsPng 截图函数
 */
export async function convert(
  slide = createSlideMock(),
  captureElementAsPng: CaptureElementAsPng = vi.fn(async (element: HTMLElement) => {
    void element
    return 'data:image/png;base64,test'
  }),
  gradientFillCollector?: (instruction: PptxGradientFillInstruction) => void,
) {
  const pageElement = document.getElementById('page') as HTMLElement
  const converter = new PPTXDomConverter()

  return converter.convertPage({
    slide,
    pageElement,
    pageIndex: 1,
    pageTitle: '测试页',
    pageRoute: '/test',
    pageWidthPx: 1920,
    pageHeightPx: 1080,
    slideWidthIn: 13.333,
    slideHeightIn: 7.5,
    shapeTypes,
    captureElementAsPng,
    gradientFillCollector,
  })
}

/**
 * 创建 slide API mock。
 */
export function createSlideMock() {
  const events: Array<Record<string, unknown>> = []
  return {
    __events: events,
    addText: vi.fn((text: PptxTextContentLike, options?: Record<string, unknown>) => {
      events.push({ kind: 'text', text, options })
    }),
    addShape: vi.fn((shapeName: string, options?: Record<string, unknown>) => {
      events.push({ kind: 'shape', shapeName, options })
    }),
    addImage: vi.fn((options?: Record<string, unknown>) => {
      events.push({ kind: 'image', options })
    }),
    addTable: vi.fn((rows?: unknown[], options?: Record<string, unknown>) => {
      events.push({ kind: 'table', rows, options })
    }),
    background: undefined as Record<string, unknown> | undefined,
  }
}

/**
 * 解码 SVG data URL，便于断言源 XML。
 * @param data data URL
 */
export function decodeSvgDataUrl(data: string): string {
  const base64 = data.replace(/^data:image\/svg\+xml;base64,/, '')
  const binary = window.atob(base64)
  const bytes = Uint8Array.from(binary, char => char.charCodeAt(0))
  return new TextDecoder().decode(bytes)
}

/**
 * stub 脱离 DOM 的 Image 尺寸，便于验证背景图 cover 的代理比例逻辑。
 * @param width 模拟原图宽度
 * @param height 模拟原图高度
 */
export function stubDetachedImageSize(width: number, height: number): void {
  class MockImage extends EventTarget {
    complete = false
    naturalWidth = 0
    naturalHeight = 0
    private currentSrc = ''

    set src(value: string) {
      this.currentSrc = value
      this.complete = true
      this.naturalWidth = width
      this.naturalHeight = height
      queueMicrotask(() => this.dispatchEvent(new Event('load')))
    }

    get src(): string {
      return this.currentSrc
    }
  }

  vi.stubGlobal('Image', MockImage)
}
