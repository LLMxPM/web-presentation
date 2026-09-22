/**
 * 文件用途：处理 PPTX 导出中的 SVG 源读取、样式内联和 data URL 序列化。
 */

import { PPTXCssParser } from '@/core/services/pptx/PPTXCssParser'

const SVG_COLOR_STYLE_PROPERTIES = ['fill', 'stroke', 'color'] as const

const SVG_STYLE_PROPERTIES = [
  'opacity',
  'fill-opacity',
  'stroke-opacity',
  'stroke-width',
  'stroke-dasharray',
  'stroke-linecap',
  'stroke-linejoin',
  'stroke-miterlimit',
  'font-family',
  'font-size',
  'font-weight',
  'font-style',
  'text-anchor',
  'dominant-baseline',
] as const

type MeasureElementPixels = (element: Element) => { width: number; height: number }

interface SvgSerializeViewBox {
  x: number
  y: number
  width: number
  height: number
}

interface SvgSerializeOptions {
  measured?: { width: number; height: number }
  viewBox?: SvgSerializeViewBox
  removeResponsiveSizing?: boolean
}

/**
 * SVG 序列化器，负责把内联 SVG 序列化，并把外部 SVG 源文件原样封装为 data URL。
 */
export class PPTXSvgSerializer {
  constructor(
    private readonly cssParser: PPTXCssParser,
    private readonly measureElementPixels: MeasureElementPixels,
  ) {}

  /**
   * 将 SVG 序列化为 data URL。
   * @param svg SVG 元素
   * @param options 导出期覆盖参数
   */
  svgToDataUrl(svg: SVGSVGElement, options?: SvgSerializeOptions): string {
    const clone = this.prepareSvgClone(svg, options)
    const serialized = new XMLSerializer().serializeToString(clone)
    return `data:image/svg+xml;base64,${this.toBase64(serialized)}`
  }

  /**
   * 尝试读取 SVG 源 XML。
   * @param path 图片 URL 或 data URL
   */
  async resolveSvgSource(path: string): Promise<string> {
    const normalized = String(path || '').trim()
    if (!normalized) {
      return ''
    }

    const dataSource = this.decodeSvgDataUrl(normalized)
    if (dataSource) {
      return dataSource
    }

    if (!this.shouldFetchSvgSource(normalized) || typeof fetch !== 'function') {
      return ''
    }

    try {
      const response = await fetch(normalized)
      if (!response.ok) {
        return ''
      }
      const source = await response.text()
      const contentType = response.headers.get('content-type') || ''
      return this.isSvgXmlSource(source, contentType) ? source : ''
    } catch {
      return ''
    }
  }

  /**
   * 将外部 SVG 源 XML 原样封装为 PPTX 可嵌入 data URL。
   * @param svgSource SVG XML
   */
  svgSourceToDataUrl(svgSource: string): string {
    return `data:image/svg+xml;base64,${this.toBase64(svgSource)}`
  }

  /**
   * 判断内联 SVG 是否包含 PowerPoint 不兼容的结构。
   * 说明：Mermaid 的 htmlLabels 和 Draw.io 的富文本标签通常会落在 foreignObject 中，
   * PowerPoint 导入 SVG 后会直接忽略这部分内容，表现为“图形存在但文字消失”。
   * @param svg SVG 元素
   * @returns 需要改走位图降级时返回 true
   */
  shouldRasterizeForPpt(svg: SVGSVGElement): boolean {
    return Boolean(svg.querySelector('foreignObject'))
  }

  /**
   * 判断 SVG XML 源码是否包含 PowerPoint 不兼容的结构。
   * @param svgSource SVG XML 文本
   * @returns 需要改走位图降级时返回 true
   */
  shouldRasterizeSourceForPpt(svgSource: string): boolean {
    return /<\s*foreignObject[\s>]/i.test(String(svgSource || ''))
  }

  /**
   * 克隆 SVG 并内联关键计算样式。
   * @param svg 原始 SVG 元素
   * @param options 导出期覆盖参数
   */
  private prepareSvgClone(svg: SVGSVGElement, options?: SvgSerializeOptions): SVGSVGElement {
    const clone = svg.cloneNode(true) as SVGSVGElement
    this.prepareSvgRootAttributes(clone, options?.measured ?? this.measureElementPixels(svg), options)
    this.inlineSvgComputedStyles(svg, clone)
    if (options?.removeResponsiveSizing) {
      this.removeResponsiveRootSizing(clone)
    }
    return clone
  }

  /**
   * 补齐 PowerPoint 识别 SVG 所需的根属性。
   * @param svg SVG 根节点
   * @param measured 外部测量尺寸
   * @param options 导出期覆盖参数
   */
  private prepareSvgRootAttributes(
    svg: SVGSVGElement,
    measured: { width: number; height: number },
    options?: SvgSerializeOptions,
  ): void {
    if (!svg.getAttribute('xmlns') && svg.namespaceURI !== 'http://www.w3.org/2000/svg') {
      svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
    }
    if (!svg.getAttribute('xmlns:xlink')) {
      svg.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink')
    }

    const viewBox = options?.viewBox
    const width = Math.round(viewBox?.width ?? measured.width)
    const height = Math.round(viewBox?.height ?? measured.height)
    if (viewBox && viewBox.width > 0 && viewBox.height > 0) {
      svg.setAttribute(
        'viewBox',
        `${this.formatSvgViewBoxValue(viewBox.x)} ${this.formatSvgViewBoxValue(viewBox.y)} ${this.formatSvgViewBoxValue(viewBox.width)} ${this.formatSvgViewBoxValue(viewBox.height)}`,
      )
    } else if (!svg.getAttribute('viewBox') && width > 0 && height > 0) {
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`)
    }
    if ((viewBox || options?.removeResponsiveSizing || !svg.getAttribute('width')) && width > 0) {
      svg.setAttribute('width', String(width))
    }
    if ((viewBox || options?.removeResponsiveSizing || !svg.getAttribute('height')) && height > 0) {
      svg.setAttribute('height', String(height))
    }
    if (!svg.getAttribute('preserveAspectRatio')) {
      svg.setAttribute('preserveAspectRatio', 'xMidYMid meet')
    }
  }

  /**
   * 移除根 SVG 上依赖父容器的 100%/auto 尺寸样式，避免离开页面后重新解释布局。
   * @param svg 克隆后的 SVG 根节点
   */
  private removeResponsiveRootSizing(svg: SVGSVGElement): void {
    svg.style.removeProperty('width')
    svg.style.removeProperty('height')
    svg.style.removeProperty('max-width')
    svg.style.removeProperty('max-height')
    svg.style.removeProperty('left')
    svg.style.removeProperty('top')
  }

  /**
   * 将 SVG 节点的关键计算样式内联到克隆节点。
   * @param source 原始节点
   * @param clone 克隆节点
   */
  private inlineSvgComputedStyles(source: Element, clone: Element): void {
    if (source instanceof SVGElement && clone instanceof SVGElement) {
      const style = window.getComputedStyle(source)
      const currentColor = this.cssParser.parseCssColor(style.color, source, { hex: '000000', alpha: 1 })

      SVG_COLOR_STYLE_PROPERTIES.forEach(property => {
        const rawValue = source.getAttribute(property) || style.getPropertyValue(property) || ''
        if (rawValue === 'none') {
          clone.setAttribute(property, 'none')
          return
        }

        const color = this.cssParser.parseCssColor(rawValue, source, currentColor)
        if (color) {
          clone.setAttribute(property, `#${color.hex}`)
          if (property !== 'color' && color.alpha < 1) {
            clone.setAttribute(`${property}-opacity`, this.formatCssNumber(color.alpha))
          }
        }
      })

      SVG_STYLE_PROPERTIES.forEach(property => {
        const rawValue = style.getPropertyValue(property) || source.getAttribute(property) || ''
        if (rawValue && rawValue !== 'normal' && rawValue !== 'none' && rawValue !== 'depends on user agent') {
          clone.setAttribute(property, rawValue)
        }
      })
    }

    const sourceChildren = Array.from(source.children)
    const cloneChildren = Array.from(clone.children)
    sourceChildren.forEach((sourceChild, index) => {
      const cloneChild = cloneChildren[index]
      if (cloneChild) {
        this.inlineSvgComputedStyles(sourceChild, cloneChild)
      }
    })
  }

  /**
   * 解码 SVG data URL。
   * @param value data URL
   */
  private decodeSvgDataUrl(value: string): string {
    const match = value.match(/^data:image\/svg\+xml(?:;[^,]*)?,(.*)$/i)
    if (!match) {
      return ''
    }

    try {
      if (/;base64,/i.test(value)) {
        const binary = window.atob(match[1])
        const bytes = Uint8Array.from(binary, char => char.charCodeAt(0))
        return new TextDecoder().decode(bytes)
      }
      return decodeURIComponent(match[1])
    } catch {
      return ''
    }
  }

  /**
   * 判断图片 URL 是否值得读取源 SVG。
   * @param path 图片 URL
   */
  private shouldFetchSvgSource(path: string): boolean {
    return /\.svg(?:[?#].*)?$/i.test(path) ||
      path.startsWith('blob:') ||
      path.includes('image/svg+xml')
  }

  /**
   * 判断响应内容是否为 SVG XML。
   * @param source 响应文本
   * @param contentType 响应类型
   */
  private isSvgXmlSource(source: string, contentType: string): boolean {
    const normalizedSource = source.trim().replace(/^<\?xml[^>]*>\s*/i, '').replace(/^<!doctype[^>]*>\s*/i, '')
    return contentType.toLowerCase().includes('image/svg+xml') ||
      /^<svg[\s>]/i.test(normalizedSource)
  }

  /**
   * 格式化 CSS 数字，避免 SVG 属性中出现过长浮点。
   * @param value 原始数值
   */
  private formatCssNumber(value: number): string {
    return String(Math.round(value * 1000) / 1000)
  }

  /**
   * 格式化 viewBox 数值，避免 SVG 属性出现过长浮点。
   * @param value 原始数值
   */
  private formatSvgViewBoxValue(value: number): string {
    return String(Math.round(value * 1000) / 1000)
  }

  /**
   * UTF-8 字符串转 base64。
   * @param value 原始字符串
   */
  private toBase64(value: string): string {
    const bytes = new TextEncoder().encode(value)
    let binary = ''
    bytes.forEach(byte => {
      binary += String.fromCharCode(byte)
    })
    return window.btoa(binary)
  }
}
