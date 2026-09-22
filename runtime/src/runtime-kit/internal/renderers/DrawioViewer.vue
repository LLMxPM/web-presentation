<!--
  文件用途：Draw.io XML 图表渲染器，负责加载 diagrams.net viewer 并适配容器缩放。
-->

<template>
  <div
    ref="viewerRoot"
    class="drawio-viewer"
    :class="[
      props.class,
      {
        'drawio-viewer--loading': loading,
        'drawio-viewer--error': error,
      },
    ]"
    :style="containerStyle"
    :data-runtime-drawio-state="drawioState"
    :data-runtime-drawio-message="drawioStateMessage"
    @pointerdown.capture="suppressGraphViewerNativeEvent"
    @mousedown.capture="suppressGraphViewerNativeEvent"
    @touchstart.capture="suppressGraphViewerNativeEvent"
    @click.capture="handleViewerClick"
  >
    <!-- 加载状态 -->
    <div v-if="loading" class="drawio-viewer__loading layout-center">
      <div class="animate-spin">
        <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="w-8 h-8">
          <circle
cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" stroke-linecap="round"
            stroke-dasharray="31.416" stroke-dashoffset="31.416">
            <animate
attributeName="stroke-dasharray" dur="2s" values="0 31.416;15.708 15.708;0 31.416"
              repeatCount="indefinite" />
            <animate attributeName="stroke-dashoffset" dur="2s" values="0;-15.708;-31.416" repeatCount="indefinite" />
          </circle>
        </svg>
      </div>
      <span class="ml-2 text-sm text-secondary">加载中...</span>
    </div>

    <!-- 错误状态 -->
    <div v-if="error" class="flex flex-col items-center justify-center text-red-500">
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 mb-2">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" />
        <line x1="15" y1="9" x2="9" y2="15" stroke="currentColor" stroke-width="2" />
        <line x1="9" y1="9" x2="15" y2="15" stroke="currentColor" stroke-width="2" />
      </svg>
      <span class="text-sm">{{ error }}</span>
    </div>

    <!-- Draw.io 图表容器 -->
    <div ref="diagramContainer" class="drawio-viewer__container" :class="{ 'hidden': loading || error }"></div>
  </div>

  <teleport to="body">
    <div v-if="isPreviewOpen" class="drawio-viewer__preview" @click.self="closePreview">
      <div class="drawio-viewer__preview-panel">
        <div class="drawio-viewer__preview-actions">
          <button type="button" class="drawio-viewer__preview-button" @click="downloadPreviewSvg">下载图片</button>
          <button type="button" class="drawio-viewer__preview-button" @click="closePreview">关闭</button>
        </div>
        <div ref="previewContainer" class="drawio-viewer__preview-container"></div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { resolveResourcePath } from '@runtime-kit/public/utils/assets.v1'
import { buildViewerSurfaceStyle, type ViewerSurfaceProps } from '@runtime-kit/internal/utils/viewer-style'

interface Props extends ViewerSurfaceProps {
  src?: string
  content?: string
  class?: string
  highlightColor?: string
}

interface DiagramBounds {
  x: number
  y: number
  width: number
  height: number
}

type DrawioRenderState = 'loading' | 'ready' | 'error'

const props = withDefaults(defineProps<Props>(), {
  src: '',
  content: '',
  class: '',
  highlightColor: 'var(--tw-color-accent1)',
})

/**
 * 判断当前组件是否声明了需要渲染的 Draw.io 来源。
 *
 * @returns 存在 src 或 content 时返回 true
 */
const hasDiagramSource = (): boolean => Boolean(props.content.trim() || props.src.trim())

// 响应式状态
const loading = ref(hasDiagramSource())
const error = ref<string | null>(null)
const drawioState = ref<DrawioRenderState>(hasDiagramSource() ? 'loading' : 'ready')
const drawioStateMessage = ref('')
const viewerRoot = ref<HTMLElement | null>(null)
const diagramContainer = ref<HTMLElement | null>(null)
const previewContainer = ref<HTMLElement | null>(null)
const intrinsicHeight = ref<string | null>(null)
const isPreviewOpen = ref(false)
const hasPreviewContent = ref(false)

// 引用当前 SVG 和 G 元素
let currentSvg: SVGSVGElement | null = null
let currentG: SVGGElement | null = null
let resizeObserver: ResizeObserver | null = null
let zoomTimer: number | null = null
let previewEscHandler: ((event: KeyboardEvent) => void) | null = null
let renderGeneration = 0

// CDN 配置
const GRAPH_VIEWER_CDN = 'https://viewer.diagrams.net/js/viewer.min.js'
const MIN_RENDER_SIZE = 24
const MIN_INTRINSIC_HEIGHT = 200
const MAX_INTRINSIC_HEIGHT = 960
const MAX_ZOOM_RETRIES = 30
const INTRINSIC_HEIGHT_RELEASE_RATIO = 1.25

/**
 * 标记一次新的 Draw.io 渲染流程，并返回本次流程令牌。
 *
 * @returns 渲染流程令牌
 */
const beginDrawioRender = (): number => {
  renderGeneration += 1
  drawioState.value = 'loading'
  drawioStateMessage.value = ''
  currentSvg = null
  currentG = null
  hasPreviewContent.value = false
  return renderGeneration
}

/**
 * 标记 Draw.io 渲染失败。
 *
 * @param message 失败原因
 * @param token 渲染流程令牌
 */
const markDrawioError = (message: string, token = renderGeneration): void => {
  if (token !== renderGeneration) return
  drawioState.value = 'error'
  drawioStateMessage.value = message
  error.value = message
  loading.value = false
}

/**
 * 标记 Draw.io 已完成 SVG 输出与缩放，并额外等待两帧确保浏览器完成绘制。
 *
 * @param token 渲染流程令牌
 */
const markDrawioReady = async (token: number): Promise<void> => {
  await waitForAnimationFrame()
  await waitForAnimationFrame()
  if (token !== renderGeneration) return
  if (!isManualZoomStillValid()) {
    scheduleManualZoom(100, 0, token)
    return
  }
  drawioState.value = 'ready'
  drawioStateMessage.value = ''
}

/**
 * 等待一个浏览器绘制帧；测试环境缺少 requestAnimationFrame 时回退到 timeout。
 */
const waitForAnimationFrame = (): Promise<void> => new Promise((resolve) => {
  if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
    window.requestAnimationFrame(() => resolve())
    return
  }
  window.setTimeout(resolve, 16)
})

/**
 * 动态加载 GraphViewer 脚本
 */
const loadGraphViewerScript = async (): Promise<void> => {
  if (typeof window !== 'undefined' && window.GraphViewer) {
    return
  }

  const existing = document.querySelector(`script[src="${GRAPH_VIEWER_CDN}"]`)
  if (existing) {
    await new Promise<void>((resolve, reject) => {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('CDN viewer.min.js 加载失败')))
      if (window.GraphViewer) resolve()
    })
    return
  }

  await new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = GRAPH_VIEWER_CDN
    script.async = true
    script.defer = true
    script.crossOrigin = 'anonymous'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('CDN viewer.min.js 加载失败'))
    document.head.appendChild(script)
  })
}

// 样式计算
const containerStyle = computed(() => ({
  ...buildViewerSurfaceStyle(props),
  ...(intrinsicHeight.value
    ? {
      height: intrinsicHeight.value,
      minHeight: intrinsicHeight.value,
    }
    : {}),
}))

/**
 * 预处理 Draw.io XML 内容
 * 确保 XML 格式符合 GraphViewer 的要求
 */
const preprocessDrawioXml = (xmlContent: string): string => {
  let processedXml = xmlContent.trim()
  
  // 如果没有 XML 声明头，添加一个
  if (!processedXml.startsWith('<?xml')) {
    processedXml = '<?xml version="1.0" encoding="UTF-8"?>\n' + processedXml
  }
  
  // 确保根元素是 mxfile
  if (!processedXml.includes('<mxfile')) {
    throw new Error('不是有效的 Draw.io 文件')
  }
    
  return processedXml
}

/**
 * 处理图片路径
 */
const processImagePath = (src: string): string => {
  if (src.startsWith('http://') || src.startsWith('https://')) {
    return src
  }
  return resolveResourcePath(src)
}

/**
 * 判断高度是否需要从图表自身比例兜底。
 *
 * @returns 高度依赖外层布局时返回 true
 */
const shouldUseIntrinsicHeight = (): boolean => {
  const height = props.height
  return height === undefined
    || height === null
    || height === ''
    || height === 'auto'
    || (typeof height === 'string' && height.trim().endsWith('%'))
}

/**
 * 在外层没有可用高度时，根据 Draw.io 自身宽高比补一个稳定高度。
 *
 * @param bbox 图表内容原始边界
 * @returns 是否更新了兜底高度
 */
const updateIntrinsicHeight = (bbox: DiagramBounds): boolean => {
  if (!shouldUseIntrinsicHeight()) {
    if (intrinsicHeight.value) intrinsicHeight.value = null
    return false
  }

  const root = viewerRoot.value
  const container = diagramContainer.value
  const parent = root?.parentElement ?? null
  const rootHeight = root?.clientHeight ?? 0
  const parentHeight = parent?.clientHeight ?? 0
  const currentIntrinsicHeight = parseFloat(intrinsicHeight.value || '0')

  if (intrinsicHeight.value && parentHeight >= MIN_RENDER_SIZE) {
    const parentHasIndependentHeight = currentIntrinsicHeight > 0
      && parentHeight > currentIntrinsicHeight * INTRINSIC_HEIGHT_RELEASE_RATIO
    if (parentHasIndependentHeight) {
      intrinsicHeight.value = null
      return true
    }
  }

  if (rootHeight >= MIN_RENDER_SIZE) {
    return false
  }

  const availableWidth = root?.clientWidth || container?.clientWidth || parent?.clientWidth || bbox.width
  if (!availableWidth || !bbox.width || !bbox.height) return false

  const nextHeight = Math.ceil(
    Math.min(
      Math.max((availableWidth * bbox.height) / bbox.width, MIN_INTRINSIC_HEIGHT),
      MAX_INTRINSIC_HEIGHT,
    ),
  )
  const nextValue = `${nextHeight}px`
  if (intrinsicHeight.value === nextValue) return false

  intrinsicHeight.value = nextValue
  return true
}

/**
 * 将 diagrams.net 输出的 SVG 坐标系重置为当前容器坐标系。
 *
 * @param svgElement GraphViewer 生成的 SVG 节点
 * @param containerWidth 当前容器宽度
 * @param containerHeight 当前容器高度
 */
const normalizeSvgViewport = (
  svgElement: SVGSVGElement,
  containerWidth: number,
  containerHeight: number,
): void => {
  svgElement.setAttribute('viewBox', `0 0 ${containerWidth} ${containerHeight}`)
  svgElement.setAttribute('preserveAspectRatio', 'xMidYMid meet')
  svgElement.removeAttribute('width')
  svgElement.removeAttribute('height')
  svgElement.style.width = '100%'
  svgElement.style.height = '100%'
  // GraphViewer 会按自身内容写入 min-width/min-height；若不清理，SVG 会突破
  // Runtime Kit 容器尺寸，导致以容器宽高计算的缩放出现水平或垂直偏移。
  svgElement.style.minWidth = '0'
  svgElement.style.minHeight = '0'
  svgElement.style.maxWidth = '100%'
  svgElement.style.maxHeight = '100%'
  svgElement.style.left = '0'
  svgElement.style.top = '0'
  svgElement.style.overflow = 'visible'
}

/**
 * 计算 Draw.io 实际 SVG 图元在内容根节点坐标系中的联合边界。
 *
 * GraphViewer 的富文本标签使用 width/height=100% 的 foreignObject，直接读取
 * 根 g 的 getBBox 会把不可见标签视口计入边界，造成图形主体向左或向上偏移。
 * 这里仅合并可绘制 SVG 图元，并通过 CTM 把嵌套变换统一到根节点坐标系。
 *
 * @param rootElement GraphViewer 输出的内容根节点
 * @returns 实际图元边界；浏览器不支持 CTM 或没有图元时返回 null
 */
const measureSvgGraphicsBounds = (rootElement: SVGGElement): DiagramBounds | null => {
  if (typeof rootElement.getCTM !== 'function') return null
  const rootMatrix = rootElement.getCTM()
  if (!rootMatrix) return null

  let minX = Number.POSITIVE_INFINITY
  let minY = Number.POSITIVE_INFINITY
  let maxX = Number.NEGATIVE_INFINITY
  let maxY = Number.NEGATIVE_INFINITY
  let measuredCount = 0

  const elements = rootElement.querySelectorAll<SVGGraphicsElement>(
    'path, rect, circle, ellipse, line, polyline, polygon, image, text',
  )
  elements.forEach((element) => {
    if (element.closest('defs, clipPath, mask, marker, pattern, symbol')) return
    if (typeof element.getCTM !== 'function') return

    const elementMatrix = element.getCTM()
    if (!elementMatrix) return

    let bbox: DOMRect
    try {
      bbox = element.getBBox()
    } catch {
      return
    }
    if (!Number.isFinite(bbox.x) || !Number.isFinite(bbox.y) || bbox.width < 0 || bbox.height < 0) return

    const matrix = rootMatrix.inverse().multiply(elementMatrix)
    const corners = [
      transformSvgPoint(matrix, bbox.x, bbox.y),
      transformSvgPoint(matrix, bbox.x + bbox.width, bbox.y),
      transformSvgPoint(matrix, bbox.x, bbox.y + bbox.height),
      transformSvgPoint(matrix, bbox.x + bbox.width, bbox.y + bbox.height),
    ]
    minX = Math.min(minX, ...corners.map(point => point.x))
    minY = Math.min(minY, ...corners.map(point => point.y))
    maxX = Math.max(maxX, ...corners.map(point => point.x))
    maxY = Math.max(maxY, ...corners.map(point => point.y))
    measuredCount += 1
  })

  const width = maxX - minX
  const height = maxY - minY
  if (measuredCount === 0 || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return null
  }

  return { x: minX, y: minY, width, height }
}

/**
 * 使用二维变换矩阵把 SVG 点转换到目标坐标系。
 *
 * @param matrix SVG 坐标变换矩阵
 * @param x 原始横坐标
 * @param y 原始纵坐标
 * @returns 变换后的坐标
 */
const transformSvgPoint = (matrix: DOMMatrix, x: number, y: number): { x: number; y: number } => ({
  x: matrix.a * x + matrix.c * y + matrix.e,
  y: matrix.b * x + matrix.d * y + matrix.f,
})

/**
 * 清理 GraphViewer 注入的外链入口，避免触发 diagrams.net 自带 lightbox。
 */
const disableGraphViewerInteractions = (): void => {
  diagramContainer.value?.querySelectorAll('a').forEach((link) => {
    link.removeAttribute('href')
    link.removeAttribute('target')
    link.removeAttribute('xlink:href')
    link.removeAttribute('onclick')
  })
}

/**
 * 手动应用缩放和居中，兼容父级未显式声明高度的场景。
 *
 * @returns 是否已成功完成缩放
 */
const applyManualZoom = (renderToken = renderGeneration): boolean => {
  const svgElement = diagramContainer.value?.querySelector('svg') as SVGSVGElement | null
  if (!svgElement) return false

  const gElement = svgElement.querySelector('g') as SVGGElement | null
  if (!gElement) return false

  currentSvg = svgElement
  currentG = gElement

  // 优先使用实际 SVG 图元边界，排除 GraphViewer 富文本 foreignObject
  // 注入的 100% 视口；测试环境或旧浏览器缺少 CTM 时回退到根节点边界。
  const bbox = measureSvgGraphicsBounds(gElement) || gElement.getBBox()
  if (!bbox.width || !bbox.height) return false

  if (updateIntrinsicHeight(bbox)) {
    nextTick(() => scheduleManualZoom(0, 0, renderToken))
    return false
  }

  // 获取容器的 client 尺寸（不包括 border/padding）
  const container = diagramContainer.value!
  const containerWidth = container.clientWidth
  const containerHeight = container.clientHeight

  if (containerWidth < MIN_RENDER_SIZE || containerHeight < MIN_RENDER_SIZE) return false

  normalizeSvgViewport(svgElement, containerWidth, containerHeight)

  // 计算缩放比例（保持宽高比，完整显示）
  const scaleX = containerWidth / bbox.width
  const scaleY = containerHeight / bbox.height
  const scale = Math.min(scaleX, scaleY)

  // 计算缩放后的图像尺寸
  const scaledWidth = bbox.width * scale
  const scaledHeight = bbox.height * scale

  // 计算居中偏移量（使图像在容器中居中）
  const offsetX = (containerWidth - scaledWidth) / 2
  const offsetY = (containerHeight - scaledHeight) / 2

  // 应用变换：先平移到居中位置，再缩放
  // bbox.x / bbox.y 可能不是 0，需要扣除原始坐标偏移。
  gElement.setAttribute(
    'transform',
    `translate(${offsetX - bbox.x * scale}, ${offsetY - bbox.y * scale}) scale(${scale})`
  )
  disableGraphViewerInteractions()
  hasPreviewContent.value = true
  return true
}

/**
 * 复验当前 Draw.io SVG 是否仍在容器内且保持可截图尺寸。
 *
 * @returns SVG、G 节点和容器尺寸都有效时返回 true
 */
const isManualZoomStillValid = (): boolean => {
  const container = diagramContainer.value
  if (!container) return false

  const svgElement = container.querySelector('svg') as SVGSVGElement | null
  const gElement = svgElement?.querySelector('g') as SVGGElement | null
  if (!svgElement || !gElement) return false

  return container.clientWidth >= MIN_RENDER_SIZE
    && container.clientHeight >= MIN_RENDER_SIZE
    && Boolean(gElement.getAttribute('transform'))
}

/**
 * 延迟并重试缩放，兼容 GraphViewer 异步插入 SVG 和父级延迟布局。
 *
 * @param delay 延迟毫秒数
 * @param retryCount 当前重试次数
 */
const scheduleManualZoom = (delay = 80, retryCount = 0, renderToken = renderGeneration) => {
  if (zoomTimer !== null) {
    window.clearTimeout(zoomTimer)
    zoomTimer = null
  }

  zoomTimer = window.setTimeout(() => {
    zoomTimer = null
    if (renderToken !== renderGeneration) return
    const applied = applyManualZoom(renderToken)
    if (applied) {
      void markDrawioReady(renderToken)
      return
    }
    if (!applied && retryCount < MAX_ZOOM_RETRIES) {
      scheduleManualZoom(100, retryCount + 1, renderToken)
      return
    }
    markDrawioError('Draw.io 图表未在限定时间内完成渲染。', renderToken)
  }, delay)
}

/**
 * 窗口大小变化时重新缩放
 */
const handleResize = () => {
  if (currentSvg && currentG) scheduleManualZoom(0, 0, renderGeneration)
}

/**
 * 判断事件是否来自 Draw.io 图表 DOM。
 *
 * @param event 用户交互事件
 * @returns 是否应由 DrawioViewer 接管
 */
const shouldHandleViewerEvent = (event: Event): boolean => {
  if (!diagramContainer.value || !currentSvg || !hasPreviewContent.value) return false
  const target = event.target instanceof Node ? event.target : null
  return Boolean(target && diagramContainer.value.contains(target))
}

/**
 * 阻止 GraphViewer 自带点击链路继续触发。
 *
 * @param event 用户交互事件
 */
const suppressGraphViewerNativeEvent = (event: Event): void => {
  if (!shouldHandleViewerEvent(event)) return

  event.preventDefault()
  event.stopPropagation()
}

/**
 * 点击图表时打开 Runtime 内部预览层。
 *
 * @param event 鼠标点击事件
 */
const handleViewerClick = async (event: MouseEvent) => {
  if (!shouldHandleViewerEvent(event)) return

  event.preventDefault()
  event.stopPropagation()
  await openPreview()
}

/**
 * 克隆当前 SVG，放入全屏预览层。
 */
const openPreview = async () => {
  if (!currentSvg) return

  isPreviewOpen.value = true
  await nextTick()
  if (!previewContainer.value || !currentSvg) return

  previewContainer.value.innerHTML = ''
  const previewSvg = currentSvg.cloneNode(true) as SVGSVGElement
  normalizePreviewSvg(previewSvg)
  previewContainer.value.appendChild(previewSvg)
  bindPreviewEscHandler()
}

/**
 * 规范化预览层 SVG 样式，避免主视图 absolute 样式影响弹窗布局。
 *
 * @param svgElement 克隆后的 SVG 节点
 */
const normalizePreviewSvg = (svgElement: SVGSVGElement): void => {
  svgElement.style.position = 'static'
  svgElement.style.display = 'block'
  svgElement.style.width = '100%'
  svgElement.style.height = '100%'
  svgElement.style.maxWidth = '100%'
  svgElement.style.maxHeight = '100%'
  svgElement.style.margin = '0'
  svgElement.style.padding = '0'
  svgElement.style.overflow = 'visible'
}

/**
 * 为预览层绑定 ESC 关闭事件。
 */
const bindPreviewEscHandler = (): void => {
  if (previewEscHandler) return

  previewEscHandler = (event: KeyboardEvent) => {
    if (event.key === 'Escape') closePreview()
  }
  document.addEventListener('keydown', previewEscHandler)
}

/**
 * 下载预览层中的 SVG 图片。
 */
const downloadPreviewSvg = (): void => {
  const svg = previewContainer.value?.querySelector('svg')
  if (!svg) return

  const svgData = new XMLSerializer().serializeToString(svg)
  const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = resolveDownloadFileName()
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

/**
 * 解析下载文件名。
 *
 * @returns SVG 文件名
 */
const resolveDownloadFileName = (): string => {
  const name = props.src.split('/').pop()?.replace(/\.(drawio|xml)$/i, '') || 'drawio-diagram'
  return `${name}.svg`
}

/**
 * 关闭预览层并清理临时 DOM。
 */
const closePreview = (): void => {
  isPreviewOpen.value = false
  if (previewContainer.value) previewContainer.value.innerHTML = ''
  if (previewEscHandler) {
    document.removeEventListener('keydown', previewEscHandler)
    previewEscHandler = null
  }
}

/**
 * 渲染 Draw.io XML 内容。
 *
 * @param xmlContent Draw.io XML 源码
 */
const renderDiagramContent = async (xmlContent: string) => {
  if (!xmlContent.trim()) return
  const renderToken = beginDrawioRender()
  loading.value = true
  error.value = null

  try {
    await loadGraphViewerScript()
    await nextTick()

    // 确保容器存在
    let retryCount = 0
    const maxRetries = 10
    while (!diagramContainer.value && retryCount < maxRetries) {
      await new Promise(resolve => setTimeout(resolve, 50))
      retryCount++
    }
    if (!diagramContainer.value) {
      throw new Error('Diagram container is not available')
    }

    diagramContainer.value.innerHTML = ''
    hasPreviewContent.value = false
    const xml = preprocessDrawioXml(xmlContent)

    // 配置：禁用工具栏，不依赖 viewer 的 zoom
    const data: Record<string, string> = {
      xml: xml,
      lightbox: 'false' // 关键：禁用灯箱/工具栏
    }

    if (props.highlightColor) data.highlight = props.highlightColor

    const div = document.createElement('div')
    div.className = 'mxgraph'
    div.style.maxWidth = '100%'
    div.style.border = '1px solid transparent'
    div.setAttribute('data-mxgraph', JSON.stringify(data))
    diagramContainer.value.appendChild(div)

    if (window.GraphViewer) {
      window.GraphViewer.processElements()
      // GraphViewer 会异步插入 SVG，需等待实际输出后再适配容器。
      scheduleManualZoom(100, 0, renderToken)
    } else {
      throw new Error('GraphViewer not initialized')
    }

    loading.value = false
  } catch (err) {
    markDrawioError(err instanceof Error ? err.message : 'Unknown error', renderToken)
    console.error('DrawioViewer: Failed to load diagram', err)
  }
}

/**
 * 从 URL 加载图表内容。
 *
 * @param src Draw.io XML 文件地址
 */
const loadDiagram = async (src: string) => {
  if (!src) return

  const renderToken = beginDrawioRender()
  loading.value = true
  error.value = null
  try {
    const processedSrc = processImagePath(src)
    const response = await fetch(processedSrc)
    if (!response.ok) {
      throw new Error(`Failed to load diagram: ${response.status} ${response.statusText}`)
    }
    await renderDiagramContent(await response.text())
  } catch (err) {
    markDrawioError(err instanceof Error ? err.message : 'Unknown error', renderToken)
    console.error('DrawioViewer: Failed to load diagram', err)
  }
}

/**
 * 按 content 优先、src 兜底的顺序刷新图表。
 */
const reloadDiagram = async () => {
  const directContent = props.content.trim()
  if (directContent) {
    beginDrawioRender()
    await nextTick()
    await renderDiagramContent(directContent)
    return
  }
  if (props.src) {
    beginDrawioRender()
    await nextTick()
    await loadDiagram(props.src)
    return
  }
  clearDiagram()
}

/**
 * 清空当前图表 DOM 和状态。
 */
const clearDiagram = () => {
  renderGeneration += 1
  if (diagramContainer.value) diagramContainer.value.innerHTML = ''
  hasPreviewContent.value = false
  closePreview()
  error.value = null
  loading.value = false
  drawioState.value = 'ready'
  drawioStateMessage.value = ''
}

// 监听内容来源变化
watch(() => [props.src, props.content], reloadDiagram, { immediate: false })

// 监听其他配置变化
watch(() => [props.highlightColor], async () => {
  await reloadDiagram()
})

// 组件挂载
onMounted(async () => {
  await nextTick()
  if (viewerRoot.value) {
    resizeObserver = new ResizeObserver(handleResize)
    resizeObserver.observe(viewerRoot.value)
    if (diagramContainer.value) resizeObserver.observe(diagramContainer.value)
    if (viewerRoot.value.parentElement) resizeObserver.observe(viewerRoot.value.parentElement)
  }
  window.addEventListener('resize', handleResize)

  try {
    await loadGraphViewerScript()
  } catch (e) {
    markDrawioError(e instanceof Error ? e.message : 'CDN viewer.min.js 加载失败')
  }

  await reloadDiagram()
})

// 组件卸载前清理
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (zoomTimer !== null) {
    window.clearTimeout(zoomTimer)
    zoomTimer = null
  }
  closePreview()
})

// 暴露方法
defineExpose({
  reload: reloadDiagram,
  clear: clearDiagram,
  openPreview,
  closePreview,
})

// 全局类型声明
declare global {
  interface Window {
    GraphViewer?: {
      processElements(): void
    }
  }
}
</script>

<style scoped>
.drawio-viewer {
  position: relative;
  box-sizing: border-box;
  display: flex;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  cursor: zoom-in;
}

.drawio-viewer__container {
  flex: 1 1 auto;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  /* 确保没有 padding/border 干扰 */
  padding: 0;
  margin: 0;
  box-sizing: border-box;
}

.drawio-viewer__container :deep(a) {
  pointer-events: none;
}

.drawio-viewer__loading {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(255, 255, 255, 0.8);
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
}

.hidden {
  display: none !important;
}

.drawio-viewer__preview {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  background: rgba(15, 23, 42, 0.76);
}

.drawio-viewer__preview-panel {
  position: relative;
  width: calc(100vw - 24px);
  height: calc(100vh - 24px);
  background: #ffffff;
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.36);
}

.drawio-viewer__preview-actions {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  display: flex;
  gap: 8px;
}

.drawio-viewer__preview-button {
  height: 32px;
  border: 1px solid rgba(15, 23, 42, 0.14);
  padding: 0 12px;
  color: #ffffff;
  font-size: 13px;
  font-weight: 600;
  background: rgba(15, 23, 42, 0.72);
  cursor: pointer;
}

.drawio-viewer__preview-button:hover {
  background: rgba(15, 23, 42, 0.9);
}

.drawio-viewer__preview-container {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
</style>

<style>
/* 确保 SVG 正确渲染 */
/* 确保 SVG 不被干扰 */
.mxgraph svg {
  width: 100% !important;
  height: 100% !important;
  display: block !important;
  overflow: visible !important;
  position: absolute !important;
  top: 0 !important;
  left: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
}

.mxgraph {
  width: 100% !important;
  height: 100% !important;
  border: none !important;
  padding: 0 !important;
  margin: 0 !important;
}

/* 提升 Draw.io 遮罩层与图表容器的层级，确保在最上层显示 */
.mx-overlay,
.geDiagramContainer {
  z-index: 9999 !important;
}

div[style*="position: fixed; inset: 0px; z-index: 999; background-color: rgb(0, 0, 0); opacity: 0.7;"] {
  z-index: 9999 !important;
}

/* 针对 Draw.io 灯箱工具栏（通过内联样式 transform 识别）进行定位覆盖 */
div[style*="transform: translate(-50%, 0px);"] {
  /* 将工具栏从默认的底部居中改为右上角定位 */
  left: auto !important;
  right: 45px !important;
  top: 45px !important;
  bottom: auto !important;
  /* 取消原有 bottom: 60px */
  z-index: 9999 !important;

  /* 移除原有的水平居中 transform，避免偏移 */
  transform: none !important;
  -webkit-transform: none !important;
}
</style>
