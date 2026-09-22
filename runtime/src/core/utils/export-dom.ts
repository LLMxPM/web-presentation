/**
 * 文件用途：提供 PDF 导出截图专用的 DOM 定位、离屏沙箱和 canvas 位图复制能力。
 */

export const RUNTIME_PAGE_PRINT_SOURCE_SELECTOR = '.runtime-page-print-source'

interface RuntimePageCaptureTargetOptions {
  routePath?: string
  width?: number
  height?: number
  backgroundColor?: string
}

export interface RuntimePageCaptureTarget {
  sourceElement: HTMLElement
  captureElement: HTMLElement
  cleanup: () => void
}

/**
 * 查找当前文档中可导出的真实页面节点。
 * @param routePath 目标路由路径；传入后仅匹配对应页面
 * @returns 真实页面节点
 */
export function findRuntimePageSource(routePath?: string): HTMLElement | null {
  const normalizedRoutePath = normalizeRoutePath(routePath)
  const sources = collectRuntimePageSources()

  if (normalizedRoutePath) {
    const matchedSource = sources.find(source => {
      return normalizeRoutePath(source.dataset.runtimeRoutePath) === normalizedRoutePath &&
        isVisibleRuntimePageSource(source)
    })

    if (matchedSource) {
      return matchedSource
    }

    return null
  }

  return sources.find(isVisibleRuntimePageSource) ?? null
}

/**
 * 创建离屏截图沙箱。
 * 说明：截图目标必须脱离布局缩放、侧栏和底栏预览影响，因此复制真实页面到固定设计尺寸容器中。
 * @param options 截图目标配置
 * @returns 沙箱目标；找不到页面时返回 null
 */
export function createRuntimePageCaptureTarget(
  options: RuntimePageCaptureTargetOptions = {},
): RuntimePageCaptureTarget | null {
  const sourceElement = findRuntimePageSource(options.routePath)
  if (!sourceElement) {
    return null
  }

  const sourceSize = measureElementSize(sourceElement)
  const width = resolvePositiveNumber(options.width, sourceSize.width, 1920)
  const height = resolvePositiveNumber(options.height, sourceSize.height, 1080)
  const sandbox = document.createElement('div')
  const clone = sourceElement.cloneNode(true) as HTMLElement
  const runtimeVariables = collectRuntimeCssVariables(sourceElement)

  sandbox.className = 'runtime-export-capture-sandbox'
  sandbox.setAttribute('aria-hidden', 'true')
  Object.assign(sandbox.style, {
    position: 'fixed',
    left: '-100000px',
    top: '0',
    width: `${width}px`,
    height: `${height}px`,
    margin: '0',
    padding: '0',
    overflow: 'hidden',
    pointerEvents: 'none',
    background: options.backgroundColor || '#ffffff',
    zIndex: '-1',
  })

  applyRuntimeVariables(sandbox, runtimeVariables)
  prepareClonedPageRoot(clone, width, height, runtimeVariables)
  stabilizeSingleLineText(sourceElement, clone)
  suppressScrollableOverflowForCapture(sourceElement, clone)
  copyCanvasContents(sourceElement, clone)

  sandbox.appendChild(clone)
  document.body.appendChild(sandbox)

  return {
    sourceElement,
    captureElement: sandbox,
    cleanup: () => {
      if (sandbox.parentNode) {
        sandbox.parentNode.removeChild(sandbox)
      }
    },
  }
}

/**
 * 将源节点中的 canvas 像素缓冲复制到克隆节点。
 * @param sourceRoot 源页面节点
 * @param clonedRoot 克隆页面节点
 */
export function copyCanvasContents(sourceRoot: HTMLElement, clonedRoot: HTMLElement): void {
  const sourceCanvases = collectCanvasElements(sourceRoot)
  const clonedCanvases = collectCanvasElements(clonedRoot)

  sourceCanvases.forEach((sourceCanvas, index) => {
    const clonedCanvas = clonedCanvases[index]
    if (!clonedCanvas) {
      return
    }

    copyCanvasBitmap(sourceCanvas, clonedCanvas)
  })
}

/**
 * 判断元素是否是可见的导出页面源。
 * @param element 候选页面源
 * @returns 是否可见且有有效尺寸
 */
export function isVisibleRuntimePageSource(element: HTMLElement): boolean {
  const style = window.getComputedStyle(element)
  const size = measureElementSize(element)

  return size.width > 0 &&
    size.height > 0 &&
    style.display !== 'none' &&
    style.visibility !== 'hidden' &&
    Number(style.opacity) !== 0
}

/**
 * 收集主内容区内的页面源节点。
 */
function collectRuntimePageSources(): HTMLElement[] {
  const mainSources = Array.from(
    document.querySelectorAll<HTMLElement>(`main ${RUNTIME_PAGE_PRINT_SOURCE_SELECTOR}`),
  )

  if (mainSources.length > 0) {
    return mainSources
  }

  return Array.from(document.querySelectorAll<HTMLElement>(RUNTIME_PAGE_PRINT_SOURCE_SELECTOR))
}

/**
 * 归一化路由路径，忽略 query 和 hash。
 * @param routePath 原始路由
 */
function normalizeRoutePath(routePath?: string | null): string {
  if (!routePath) {
    return ''
  }

  const normalized = routePath.trim().split(/[?#]/)[0]
  return normalized || '/'
}

/**
 * 测量元素设计尺寸，优先读取未受 transform 影响的 CSS 尺寸。
 * @param element 目标元素
 */
function measureElementSize(element: HTMLElement): { width: number; height: number } {
  const style = window.getComputedStyle(element)
  const rect = element.getBoundingClientRect()

  return {
    width: resolvePositiveNumber(
      parseCssPixelValue(style.width),
      element.offsetWidth,
      rect.width,
    ),
    height: resolvePositiveNumber(
      parseCssPixelValue(style.height),
      element.offsetHeight,
      rect.height,
    ),
  }
}

/**
 * 解析 CSS 像素值。
 * @param value CSS 长度
 */
function parseCssPixelValue(value: string): number | undefined {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined
}

/**
 * 从候选数值中选出第一个有效正数。
 * @param values 候选数值
 */
function resolvePositiveNumber(...values: Array<number | undefined>): number {
  const value = values.find(item => Number.isFinite(item) && Number(item) > 0)
  return value ? Math.round(value) : 1
}

/**
 * 配置克隆后的页面根节点。
 * @param clone 克隆节点
 * @param width 设计宽度
 * @param height 设计高度
 * @param variables 运行时 CSS 变量
 */
function prepareClonedPageRoot(
  clone: HTMLElement,
  width: number,
  height: number,
  variables: Array<[string, string]>,
): void {
  Object.assign(clone.style, {
    position: 'relative',
    inset: 'auto',
    transform: 'none',
    transformOrigin: 'top left',
    width: `${width}px`,
    height: `${height}px`,
    minWidth: `${width}px`,
    minHeight: `${height}px`,
    maxWidth: 'none',
    maxHeight: 'none',
    margin: '0',
    overflow: 'hidden',
    boxSizing: 'border-box',
  })

  applyRuntimeVariables(clone, variables)
}

/**
 * 稳定单行文本在截图渲染中的换行行为。
 * 说明：snapdom 生成图片时字体度量可能比页面实时布局略宽，导致原本单行的标题末字换行。
 * @param sourceRoot 源页面节点
 * @param clonedRoot 克隆页面节点
 */
function stabilizeSingleLineText(sourceRoot: HTMLElement, clonedRoot: HTMLElement): void {
  const sourceElements = collectHtmlElements(sourceRoot)
  const clonedElements = collectHtmlElements(clonedRoot)

  sourceElements.forEach((sourceElement, index) => {
    const clonedElement = clonedElements[index]
    if (!clonedElement || !shouldStabilizeSingleLineText(sourceElement)) {
      return
    }

    const style = window.getComputedStyle(sourceElement)
    const width = Math.ceil(measureTextElementWidth(sourceElement) + 12)

    clonedElement.style.whiteSpace = 'nowrap'
    clonedElement.style.wordBreak = 'keep-all'
    clonedElement.style.overflowWrap = 'normal'

    if (style.display !== 'inline') {
      clonedElement.style.width = `${width}px`
      clonedElement.style.minWidth = `${width}px`
      clonedElement.style.maxWidth = '100%'
    }
  })
}

/**
 * 在截图 clone 中隐藏滚动容器滚动条。
 * 说明：页面预览可以保留 overflow-auto 作为编辑兜底，但 PDF 位图导出应呈现固定画布，
 * 否则 snapDOM 会把内部滚动条一起绘制进图片。
 * @param sourceRoot 源页面节点
 * @param clonedRoot 克隆页面节点
 */
function suppressScrollableOverflowForCapture(sourceRoot: HTMLElement, clonedRoot: HTMLElement): void {
  const sourceElements = collectHtmlElements(sourceRoot)
  const clonedElements = collectHtmlElements(clonedRoot)

  sourceElements.forEach((sourceElement, index) => {
    const clonedElement = clonedElements[index]
    if (!clonedElement) {
      return
    }

    const style = window.getComputedStyle(sourceElement)
    if (!hasScrollableOverflow(style)) {
      return
    }

    clonedElement.scrollLeft = sourceElement.scrollLeft
    clonedElement.scrollTop = sourceElement.scrollTop
    clonedElement.style.overflow = 'hidden'
    clonedElement.style.overflowX = 'hidden'
    clonedElement.style.overflowY = 'hidden'
    clonedElement.style.setProperty('scrollbar-width', 'none')
    clonedElement.style.setProperty('-ms-overflow-style', 'none')
  })
}

/**
 * 判断计算样式中是否存在会绘制滚动条的 overflow。
 * @param style 计算样式
 */
function hasScrollableOverflow(style: CSSStyleDeclaration): boolean {
  return isScrollableOverflow(style.overflow) ||
    isScrollableOverflow(style.overflowX) ||
    isScrollableOverflow(style.overflowY)
}

/**
 * 判断单个 overflow 值是否可能显示滚动条。
 * @param value overflow 属性值
 */
function isScrollableOverflow(value: string): boolean {
  return value === 'auto' || value === 'scroll' || value === 'overlay'
}

/**
 * 判断文本节点是否需要单行稳定处理。
 * @param element 候选文本元素
 */
function shouldStabilizeSingleLineText(element: HTMLElement): boolean {
  const text = element.textContent?.trim()
  if (!text || element.children.length > 0 || isFormTextControl(element)) {
    return false
  }

  const style = window.getComputedStyle(element)
  if (
    style.display === 'none' ||
    style.visibility === 'hidden' ||
    Number(style.opacity) === 0 ||
    style.whiteSpace === 'pre-wrap' ||
    style.whiteSpace === 'pre-line'
  ) {
    return false
  }

  const lineHeight = resolveLineHeight(style)
  const height = element.scrollHeight ||
    element.clientHeight ||
    element.getBoundingClientRect().height ||
    parseCssPixelValue(style.height) ||
    lineHeight

  return lineHeight > 0 && height <= lineHeight * 1.35
}

/**
 * 判断元素是否是表单文本控件。
 * @param element 候选元素
 */
function isFormTextControl(element: HTMLElement): boolean {
  const tagName = element.tagName.toLowerCase()
  return tagName === 'textarea' ||
    tagName === 'input' ||
    tagName === 'select' ||
    element.isContentEditable
}

/**
 * 获取文本元素导出时的保守宽度。
 * @param element 文本元素
 */
function measureTextElementWidth(element: HTMLElement): number {
  const style = window.getComputedStyle(element)
  return Math.max(
    element.scrollWidth,
    element.clientWidth,
    element.getBoundingClientRect().width,
    parseCssPixelValue(style.width) ?? 0,
  )
}

/**
 * 解析元素行高。
 * @param style 计算样式
 */
function resolveLineHeight(style: CSSStyleDeclaration): number {
  const lineHeight = Number.parseFloat(style.lineHeight)
  if (Number.isFinite(lineHeight) && lineHeight > 0) {
    return lineHeight
  }

  const fontSize = Number.parseFloat(style.fontSize)
  return Number.isFinite(fontSize) && fontSize > 0 ? fontSize * 1.2 : 0
}

/**
 * 收集导出时需要继承的运行时 CSS 变量。
 * @param sourceElement 页面源节点
 */
function collectRuntimeCssVariables(sourceElement: HTMLElement): Array<[string, string]> {
  const variableMap = new Map<string, string>()
  const sources = [
    document.documentElement,
    document.body,
    sourceElement.closest('.responsive-layout'),
    sourceElement,
  ].filter((element): element is Element => Boolean(element))

  sources.forEach(element => {
    const style = window.getComputedStyle(element)
    for (let index = 0; index < style.length; index += 1) {
      const propertyName = style[index]
      if (!propertyName.startsWith('--')) {
        continue
      }

      const propertyValue = style.getPropertyValue(propertyName).trim()
      if (propertyValue) {
        variableMap.set(propertyName, propertyValue)
      }
    }
  })

  return Array.from(variableMap.entries())
}

/**
 * 应用运行时 CSS 变量。
 * @param element 目标元素
 * @param variables CSS 变量列表
 */
function applyRuntimeVariables(element: HTMLElement, variables: Array<[string, string]>): void {
  variables.forEach(([name, value]) => {
    element.style.setProperty(name, value)
  })
}

/**
 * 按 DOM 顺序收集根节点和所有 HTML 后代节点。
 * @param root 查询根节点
 */
function collectHtmlElements(root: HTMLElement): HTMLElement[] {
  return [root, ...Array.from(root.querySelectorAll<HTMLElement>('*'))]
}

/**
 * 按 DOM 顺序收集节点自身和后代 canvas。
 * @param root 查询根节点
 */
function collectCanvasElements(root: HTMLElement): HTMLCanvasElement[] {
  const canvases = Array.from(root.querySelectorAll<HTMLCanvasElement>('canvas'))

  if (root instanceof HTMLCanvasElement) {
    return [root, ...canvases]
  }

  return canvases
}

/**
 * 复制单个 canvas 位图。
 * @param sourceCanvas 源 canvas
 * @param clonedCanvas 克隆 canvas
 */
function copyCanvasBitmap(sourceCanvas: HTMLCanvasElement, clonedCanvas: HTMLCanvasElement): void {
  if (sourceCanvas.width <= 0 || sourceCanvas.height <= 0) {
    return
  }

  clonedCanvas.width = sourceCanvas.width
  clonedCanvas.height = sourceCanvas.height

  const sourceStyle = window.getComputedStyle(sourceCanvas)
  if (!clonedCanvas.style.width && sourceStyle.width && sourceStyle.width !== 'auto') {
    clonedCanvas.style.width = sourceStyle.width
  }
  if (!clonedCanvas.style.height && sourceStyle.height && sourceStyle.height !== 'auto') {
    clonedCanvas.style.height = sourceStyle.height
  }

  try {
    const context = clonedCanvas.getContext('2d')
    context?.clearRect(0, 0, clonedCanvas.width, clonedCanvas.height)
    context?.drawImage(sourceCanvas, 0, 0)
  } catch (error) {
    console.warn('复制导出 canvas 位图失败，相关图表可能无法出现在截图 PDF 中:', error)
  }
}
