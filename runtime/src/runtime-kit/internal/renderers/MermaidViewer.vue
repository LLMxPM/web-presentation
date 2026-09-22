<!--
  文件用途：Mermaid 文本图表渲染器，负责渲染、刷新和错误兜底展示。
-->

<template>
  <div
    class="mermaid-viewer"
    :style="surfaceStyle"
    :class="{ 'cursor-zoom-in group': previewEnabled }"
    :data-runtime-mermaid-state="mermaidState"
    :data-runtime-mermaid-message="mermaidStateMessage"
    v-bind="$attrs"
    @click="handleViewerClick"
  >
    <!-- 加载状态 -->
    <div v-if="loading" class="absolute inset-0 flex items-center justify-center bg-white bg-opacity-90 z-10">
      <div class="flex items-center space-x-2 text-gray-600">
        <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
        <span>正在渲染图表...</span>
      </div>
    </div>

    <!-- 错误状态 -->
    <div v-if="error" class="absolute inset-0 flex items-center justify-center bg-white bg-opacity-90 z-10">
      <div class="text-center text-red-600">
        <div class="text-lg font-semibold mb-2">渲染失败</div>
        <div class="text-sm">{{ error }}</div>
      </div>
    </div>

    <!-- 图表容器 - 始终存在 -->
    <div ref="diagramContainer" class="mermaid-diagram-container" :style="diagramStyle"></div>
  </div>

  <!-- 全屏预览弹层（覆盖整个浏览器窗口） -->
  <teleport to="body">
    <div
v-if="isPreviewOpen" class="fixed inset-0 bg-black bg-opacity-70 z-[9999] flex items-center justify-center"
      @click.self="closePreview">
      <!-- Container for diagram and controls, centered by flexbox parent -->
      <div class="relative cursor-zoom-out" :style="{ width: previewWidth, height: previewHeight }">
        <!-- Controls -->
        <div class="absolute top-4 right-4 z-50 flex space-x-2">
          <button
class="bg-gray-800/60 hover:bg-gray-900/70 text-white rounded px-3 py-1 shadow-lg transition-colors"
            @click="downloadPreviewSVG">下载图片</button>
          <button
class="bg-gray-800/60 hover:bg-gray-900/70 text-white rounded px-3 py-1 shadow-lg transition-colors"
            @click="closePreview">关闭</button>
        </div>
        <!-- Diagram -->
        <div
ref="previewContainer" class="mermaid-diagram-container w-full h-full"
          :style="{ backgroundColor: themeBackground }"></div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick, onBeforeUnmount } from 'vue'
import { createRafResizeObserver } from '@/core/utils/resize-observer'
import { buildViewerSurfaceStyle, type ViewerSurfaceProps } from '@runtime-kit/internal/utils/viewer-style'

// Props接口定义
interface Props extends ViewerSurfaceProps {
  /** 图表内容 */
  content?: string
  /** 图表文件路径 */
  src?: string
  /** 主题 */
  theme?: 'default' | 'dark' | 'forest' | 'neutral'
  /** 自定义配置 */
  config?: Record<string, unknown>
  /** 是否启用点击打开全屏预览 */
  previewEnabled?: boolean
}

type MermaidLibrary = Awaited<typeof import('mermaid')>['default']
type MermaidInitializeConfig = Parameters<MermaidLibrary['initialize']>[0]
type MermaidRenderState = 'loading' | 'ready' | 'error'
type SvgPanZoomFactory = (
  element: SVGElement,
  options?: Record<string, unknown>,
) => PanZoomController

interface PanZoomController {
  destroy?: () => void
  zoomIn: () => void
  zoomOut: () => void
  resetZoom: () => void
  reset: () => void
}

interface InteractiveSvgElement extends SVGSVGElement {
  __panZoomInstance?: PanZoomController
  __cleanupPanZoom?: () => void
}

interface PreviewContainerElement extends HTMLElement {
  _escHandler?: (event: KeyboardEvent) => void
}

// Props默认值
const props = withDefaults(defineProps<Props>(), {
  content: '',
  src: '',
  theme: 'default',
  config: () => ({}),
  previewEnabled: true
})

/**
 * 判断当前组件是否有可渲染 Mermaid 来源。
 * @returns 存在 content 或 src 时返回 true
 */
const hasDiagramSource = (): boolean => Boolean(props.content.trim() || props.src.trim())

// 响应式数据
const loading = ref(hasDiagramSource())
const error = ref<string | null>(null)
const mermaidState = ref<MermaidRenderState>(hasDiagramSource() ? 'loading' : 'ready')
const mermaidStateMessage = ref('')
const diagramContainer = ref<HTMLElement | null>(null)
const previewContainer = ref<PreviewContainerElement | null>(null)
const mermaidId = ref('')
let mermaidInstance: MermaidLibrary | null = null
let resizeObserver: ResizeObserver | null = null
const isPreviewOpen = ref(false)
let renderGeneration = 0

// 预览尺寸（基于窗口自适应）
const previewWidth = 'calc(100vw - 24px)'
const previewHeight = 'calc(100vh - 24px)'

// 计算属性
// 图表容器背景色，随主题变化
const themeBackground = computed(() => {
  switch (props.theme) {
    case 'dark':
      return '#0f172a' // slate-900 深色背景
    case 'forest':
      return '#f0fdf4' // green-50 森林主题浅绿色背景
    case 'neutral':
      return '#f5f5f5' // gray-100 中性浅灰背景
    default:
      return '#ffffff' // 默认白色背景
  }
})

const surfaceStyle = computed(() => buildViewerSurfaceStyle(props))

const diagramStyle = computed(() => ({
  ...(props.backgroundColor ? { backgroundColor: props.backgroundColor } : {}),
  overflow: 'hidden',
  alignItems: 'center',
  justifyContent: 'center'
}))

/**
 * 生成唯一ID
 * @returns 唯一标识符
 */
const generateId = (): string => {
  return `mermaid-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}

/**
 * 将未知错误对象统一转成可展示文案。
 * @param reason 捕获到的错误对象
 * @returns 错误消息
 */
const getErrorMessage = (reason: unknown): string => {
  return reason instanceof Error ? reason.message : String(reason || '未知错误')
}

/**
 * 标记一次新的 Mermaid 渲染流程，并返回流程令牌。
 * @returns 当前渲染流程令牌
 */
const beginMermaidRender = (): number => {
  renderGeneration += 1
  mermaidState.value = 'loading'
  mermaidStateMessage.value = ''
  return renderGeneration
}

/**
 * 标记 Mermaid 渲染失败。
 * @param message 失败原因
 * @param token 渲染流程令牌
 */
const markMermaidError = (message: string, token = renderGeneration): void => {
  if (token !== renderGeneration) return
  mermaidState.value = 'error'
  mermaidStateMessage.value = message
  error.value = message
  loading.value = false
}

/**
 * 标记 Mermaid 已完成 SVG 输出与浏览器绘制。
 * @param token 渲染流程令牌
 */
const markMermaidReady = async (token: number): Promise<void> => {
  await waitForAnimationFrame()
  await waitForAnimationFrame()
  if (token !== renderGeneration) return
  mermaidState.value = 'ready'
  mermaidStateMessage.value = ''
  loading.value = false
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
 * 读取容器中的 Mermaid SVG，并收窄为支持自定义挂载字段的类型。
 * @param container 图表容器
 * @returns SVG 元素；不存在时返回 null
 */
const getInteractiveSvg = (container?: ParentNode | null): InteractiveSvgElement | null => {
  const svg = container?.querySelector('svg')
  return svg instanceof SVGSVGElement ? svg as InteractiveSvgElement : null
}

/**
 * 清理指定容器下的 pan/zoom 交互实例。
 * @param container 图表容器
 */
const cleanupPanZoom = (container?: ParentNode | null): void => {
  getInteractiveSvg(container)?.__cleanupPanZoom?.()
}

/**
 * 初始化Mermaid
 */
const initMermaid = async () => {
  if (mermaidInstance) {
    return mermaidInstance
  }

  try {
    // 动态导入mermaid
    const mermaidModule = await import('mermaid')
    mermaidInstance = mermaidModule.default

    // 配置mermaid
    const baseConfig: MermaidInitializeConfig = {
      startOnLoad: false,
      theme: props.theme,
      securityLevel: 'loose',
      themeVariables: {
        background: themeBackground.value,
        primaryColor: '#3b82f6',
        primaryTextColor: '#1f2937',
        primaryBorderColor: '#d1d5db',
        lineColor: '#6b7280',
        secondaryColor: '#f3f4f6',
        tertiaryColor: '#ffffff'
      },
      flowchart: {
        useMaxWidth: true,
        htmlLabels: true,
        curve: 'basis'
      },
      sequence: {
        useMaxWidth: true,
        wrap: true
      },
      gantt: {
        useMaxWidth: true,
        fontSize: 12
      },
      pie: {
        useMaxWidth: true
      }
    }

    const config = {
      ...baseConfig,
      ...props.config
    } as MermaidInitializeConfig

    mermaidInstance.initialize(config)
    return mermaidInstance
  } catch (err) {
    console.error('Failed to initialize Mermaid:', err)
    throw new Error(`无法加载Mermaid库: ${getErrorMessage(err)}`, { cause: err })
  }
}

/**
 * 从文件加载内容
 */
const loadContentFromFile = async (src: string): Promise<string> => {
  try {
    const response = await fetch(src)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }
    return await response.text()
  } catch (err) {
    throw new Error(`无法加载文件 ${src}: ${getErrorMessage(err)}`, { cause: err })
  }
}

/**
 * 自适应缩放，确保图表在容器内完整显示
 */
const fitSvgToContainer = (container?: HTMLElement | null) => {
  const target = container ?? diagramContainer.value
  if (!target) return
  const svgEl = target.querySelector('svg') as SVGSVGElement | null
  if (!svgEl) return

  // 如果没有 viewBox，则尝试使用 BBox 或宽高推断
  const hasViewBox = !!svgEl.getAttribute('viewBox')
  if (!hasViewBox) {
    try {
      const bbox = typeof svgEl.getBBox === 'function' ? svgEl.getBBox() : null
      if (bbox && bbox.width && bbox.height) {
        svgEl.setAttribute('viewBox', `0 0 ${Math.ceil(bbox.width)} ${Math.ceil(bbox.height)}`)
      }
    } catch {
      const wAttr = svgEl.getAttribute('width')
      const hAttr = svgEl.getAttribute('height')
      const w = wAttr ? parseFloat(wAttr) : svgEl.clientWidth
      const h = hAttr ? parseFloat(hAttr) : svgEl.clientHeight
      if (w && h) {
        svgEl.setAttribute('viewBox', `0 0 ${Math.ceil(w)} ${Math.ceil(h)}`)
      }
    }
  }

  // 让 SVG 根据容器缩放并保持纵横比
  svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet')
  svgEl.removeAttribute('width')
  svgEl.removeAttribute('height')
  svgEl.style.width = '100%'
  svgEl.style.height = '100%'
  svgEl.style.maxWidth = '100%'
  svgEl.style.maxHeight = '100%'
}

/**
 * 渲染图表
 */
const renderDiagram = async (content: string) => {
  const renderToken = beginMermaidRender()
  if (!content?.trim()) {
    markMermaidError('图表内容为空', renderToken)
    return
  }

  loading.value = true
  error.value = null

  try {
    // 等待DOM准备
    await nextTick()

    // 确保容器元素存在
    if (!diagramContainer.value) {
      // 等待容器元素挂载
      let retryCount = 0
      while (!diagramContainer.value && retryCount < 50) {
        await new Promise(resolve => setTimeout(resolve, 100))
        await nextTick()
        retryCount++
      }
    }

    if (!diagramContainer.value) {
      throw new Error('图表容器未找到，请检查组件是否正确挂载')
    }

    // 清空容器
    diagramContainer.value.innerHTML = ''

    // 初始化Mermaid
    const mermaid = await initMermaid()

    // 生成唯一ID
    mermaidId.value = generateId()

    // 渲染图表（不进行失败重试）
    const { svg } = await mermaid.render(mermaidId.value, content.trim())

    if (!svg) {
      throw new Error('渲染结果为空')
    }

    // 插入SVG
    diagramContainer.value.innerHTML = svg

    // 主视图始终自适应容器，不启用交互
    fitSvgToContainer(diagramContainer.value)

    await markMermaidReady(renderToken)
  } catch (err) {
    markMermaidError(getErrorMessage(err), renderToken)
    console.error('MermaidViewer render error:', err)
  }
}

/**
 * 添加交互功能
 */
const addInteractivity = (container?: HTMLElement | null) => {
  const target = container ?? diagramContainer.value
  if (!target) return

  const svg = target.querySelector('svg')
  if (!svg) return

  // 动态导入svg-pan-zoom库
  import('svg-pan-zoom').then((svgPanZoomModule) => {
    const svgPanZoom = ((
      'default' in svgPanZoomModule ? svgPanZoomModule.default : svgPanZoomModule
    ) as unknown) as SvgPanZoomFactory

    // 确保svgPanZoom是一个函数
    if (typeof svgPanZoom !== 'function') {
      console.error('svg-pan-zoom is not a function')
      return
    }

    // 初始化svg-pan-zoom
    const panZoomInstance = svgPanZoom(svg, {
      zoomEnabled: true, // 预览模式始终启用缩放
      panEnabled: true, // 预览模式始终启用平移
      controlIconsEnabled: false, // 不显示默认控制图标
      fit: true, // 初始适配容器
      center: true, // 初始居中
      contain: false, // 关键配置：允许SVG超出容器边界，实现无限制平移
      minZoom: 0.1,
      maxZoom: 10,
      zoomScaleSensitivity: 0.1,
      dblClickZoomEnabled: true,
      mouseWheelZoomEnabled: true,
      preventMouseEventsDefault: true,
      beforeZoom: function () {
        // 可以在这里添加缩放前的逻辑
        return true
      },
      beforePan: function (oldPan, newPan) {
        // 配合contain: false，实现真正的无限制平移
        return newPan
      }
    })

    const interactiveSvg = svg as InteractiveSvgElement
    interactiveSvg.__panZoomInstance = panZoomInstance

    // 添加键盘快捷键支持
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!panZoomInstance) return

      switch (event.key) {
        case '+':
        case '=':
          event.preventDefault()
          panZoomInstance.zoomIn()
          break
        case '-':
          event.preventDefault()
          panZoomInstance.zoomOut()
          break
        case '0':
          event.preventDefault()
          panZoomInstance.resetZoom()
          break
        case 'r':
        case 'R':
          if (event.ctrlKey || event.metaKey) {
            event.preventDefault()
            panZoomInstance.reset()
          }
          break
      }
    }

    // 添加键盘事件监听
    document.addEventListener('keydown', handleKeyDown)

    interactiveSvg.__cleanupPanZoom = () => {
      document.removeEventListener('keydown', handleKeyDown)
      if (panZoomInstance && typeof panZoomInstance.destroy === 'function') {
        panZoomInstance.destroy()
      }
    }

  }).catch((error) => {
    console.error('Failed to load svg-pan-zoom:', error)
  })
}

/**
 * 重新加载图表
 */
const reload = async () => {
  let content = props.content

  if (!content && props.src) {
    const renderToken = beginMermaidRender()
    loading.value = true
    error.value = null
    try {
      content = await loadContentFromFile(props.src)
      if (renderToken !== renderGeneration) return
    } catch (err) {
      markMermaidError(getErrorMessage(err), renderToken)
      return
    }
  }

  if (content) {
    await renderDiagram(content)
    return
  }
  clear()
}

/**
 * 清空图表
 */
const clear = () => {
  renderGeneration += 1
  if (diagramContainer.value) {
    cleanupPanZoom(diagramContainer.value)
    diagramContainer.value.innerHTML = ''
  }
  if (previewContainer.value) {
    cleanupPanZoom(previewContainer.value)
    previewContainer.value.innerHTML = ''
  }
  error.value = null
  loading.value = false
  mermaidState.value = 'ready'
  mermaidStateMessage.value = ''
}

/**
 * 更新内容
 */
const updateContent = async (newContent: string) => {
  await renderDiagram(newContent)
}

/**
 * 导出SVG
 */
const exportSVG = (): string | null => {
  if (!diagramContainer.value) return null

  const svg = diagramContainer.value.querySelector('svg')
  return svg ? svg.outerHTML : null
}

/**
 * 事件：点击主视图打开预览
 */
const handleViewerClick = async () => {
  if (!props.previewEnabled) return
  await openPreview()
}

/**
 * 打开全屏预览
 */
const openPreview = async () => {
  isPreviewOpen.value = true
  await nextTick()
  // 渲染到预览容器，开启交互
  let content = props.content
  if (!content && props.src) {
    try {
      content = await loadContentFromFile(props.src)
    } catch (err) {
      error.value = getErrorMessage(err)
      console.error('预览内容加载失败:', err)
      return
    }
  }
  if (previewContainer.value && content) {
    try {
      // 使用独立容器渲染
      previewContainer.value.innerHTML = ''
      const mermaid = await initMermaid()
      mermaidId.value = generateId()
      const { svg } = await mermaid.render(mermaidId.value, content.trim())
      previewContainer.value.innerHTML = svg

      // 关键：先让SVG自适应容器，获得正确的viewBox和初始尺寸
      fitSvgToContainer(previewContainer.value)

      // 然后再启用交互
      addInteractivity(previewContainer.value)
    } catch (err) {
      console.error('预览渲染失败:', err)
    }
  }

  // ESC 关闭
  const escHandler = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      closePreview()
    }
  }
  document.addEventListener('keydown', escHandler)
  if (previewContainer.value) {
    previewContainer.value._escHandler = escHandler
  }
}

/**
 * 下载预览图表为SVG文件
 */
const downloadPreviewSVG = () => {
  if (!previewContainer.value) return

  const svg = previewContainer.value.querySelector('svg')
  if (!svg) return

  // 序列化SVG内容
  const svgData = new XMLSerializer().serializeToString(svg)

  // 创建Blob对象
  const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' })

  // 创建下载链接
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${mermaidId.value || 'mermaid-diagram'}.svg` // 使用图表ID或默认名
  document.body.appendChild(a)
  a.click()

  // 清理
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * 关闭预览
 */
const closePreview = () => {
  isPreviewOpen.value = false
  // 清理预览容器
  if (previewContainer.value) {
    cleanupPanZoom(previewContainer.value)
    previewContainer.value.innerHTML = ''
  }
  // 移除 ESC 事件
  const escHandler = previewContainer.value?._escHandler
  if (escHandler) {
    document.removeEventListener('keydown', escHandler)
    if (previewContainer.value) {
      previewContainer.value._escHandler = undefined
    }
  }
}

// 监听props变化
watch(() => [props.src, props.content], () => {
  void reload()
}, { immediate: false })

watch(() => props.theme, () => {
  mermaidInstance = null // 重置实例以应用新主题
  void reload()
})

// 组件挂载后初始化
onMounted(() => {
  reload()
  // 监听尺寸变化，保持主视图自适应
  const handleResize = () => fitSvgToContainer(diagramContainer.value)
  window.__mermaidViewerResizeHandler = handleResize
  window.addEventListener('resize', handleResize)
  if (diagramContainer.value) {
    resizeObserver = createRafResizeObserver(() => fitSvgToContainer(diagramContainer.value))
    resizeObserver.observe(diagramContainer.value)
  }
})

// 组件卸载前清理
onBeforeUnmount(() => {
  clear()
  // 清理监听
  const handleResize = window.__mermaidViewerResizeHandler
  if (handleResize) {
    window.removeEventListener('resize', handleResize)
    window.__mermaidViewerResizeHandler = undefined
  }
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
})

// 暴露方法
defineExpose({
  reload,
  clear,
  updateContent,
  exportSVG,
  openPreview,
  closePreview
})

declare global {
  interface Window {
    __mermaidViewerResizeHandler?: () => void
  }
}
</script>

<style scoped>
.mermaid-viewer {
  position: relative;
  box-sizing: border-box;
  display: flex;
  overflow: hidden;
}

.mermaid-diagram-container {
  position: relative;
  flex: 1 1 auto;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mermaid-diagram-container :deep(svg) {
  max-width: none;
  max-height: none;
  width: auto;
  height: auto;
}

/* 移除原有的居中样式，因为已在容器中设置 */

/* 响应式设计 */
@media (max-width: 768px) {
  .mermaid-diagram-container :deep(svg) {
    max-width: none;
    max-height: none;
    width: auto;
    height: auto;
  }
}
</style>
