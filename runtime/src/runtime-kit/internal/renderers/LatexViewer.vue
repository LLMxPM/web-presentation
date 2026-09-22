<!--
  文件用途：LaTeX 公式渲染器，负责使用 MathJax 将公式源码排版为 SVG HTML。
-->
<template>
  <section
    ref="viewerRef"
    class="latex-viewer"
    :class="fitClass"
    :style="surfaceStyle"
    v-bind="$attrs"
  >
    <!-- eslint-disable vue/no-v-html -- MathJax 输出由 renderer 生成，组件只渲染受控 SVG HTML。 -->
    <div
      v-if="renderedHtml"
      ref="contentRef"
      class="latex-viewer__content"
      :style="contentStyle"
      v-html="renderedHtml"
    />
    <!-- eslint-enable vue/no-v-html -->
    <span v-else-if="error" class="latex-viewer__state latex-viewer__state--error">{{ error }}</span>
    <span v-else class="latex-viewer__state">公式内容为空</span>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type CSSProperties } from 'vue'
import { useViewerSurfaceStyle, type ViewerSurfaceProps } from '@runtime-kit/internal/utils/viewer-style'
import { renderLatexToString, type MathStrictMode } from '@runtime-kit/internal/renderers/latex'

type LatexFitMode = 'contain' | 'none'

interface Props extends ViewerSurfaceProps {
  /** LaTeX 源码内容 */
  content?: string
  /** 公式整体适配模式；contain 会等比缩放完整内容，none 保留自然尺寸 */
  fit?: LatexFitMode
  /** 公式文本颜色，支持普通 CSS 颜色值和 CSS 变量 */
  textColor?: string
  /** 是否使用块级公式模式 */
  displayMode?: boolean
  /** 解析错误时是否抛出异常，保留为兼容旧组件参数 */
  throwOnError?: boolean
  /** 严格模式，保留为兼容旧组件参数 */
  strict?: MathStrictMode
  /** 是否允许受信任命令，保留为兼容旧组件参数 */
  trust?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  content: '',
  fit: 'contain',
  textColor: undefined,
  displayMode: false,
  throwOnError: false,
  strict: 'warn',
  trust: false,
})

const surfaceStyle = useViewerSurfaceStyle(props)
const renderedHtml = ref('')
const error = ref('')
const viewerRef = ref<HTMLElement | null>(null)
const contentRef = ref<HTMLElement | null>(null)
const contentScale = ref(1)
let renderVersion = 0
let resizeObserver: ResizeObserver | null = null
let fitUpdateTimer: number | null = null

const fitClass = computed(() => `latex-viewer--fit-${props.fit}`)
const contentStyle = computed<CSSProperties>(() => ({
  ...(props.textColor ? { color: props.textColor } : {}),
  ...(props.fit === 'contain' && contentScale.value !== 1
    ? {
        transform: `scale(${contentScale.value})`,
        transformOrigin: 'center center',
      }
    : {}),
}))

/**
 * 将 unknown 错误统一转为可展示文案。
 *
 * @param reason 捕获到的错误对象
 * @returns 错误消息
 */
function getErrorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason || '未知错误')
}

/**
 * 读取 CSS 像素值，无法解析时按 0 处理。
 *
 * @param value CSS 像素字符串
 * @returns 数值化像素
 */
function parseCssPixel(value: string): number {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) ? parsed : 0
}

/**
 * 计算渲染区域扣除 padding 后的可用尺寸。
 *
 * @param element 根容器元素
 * @returns 内容区宽高
 */
function getAvailableSize(element: HTMLElement): { width: number; height: number } {
  const style = window.getComputedStyle(element)
  const width = element.clientWidth
    - parseCssPixel(style.paddingLeft)
    - parseCssPixel(style.paddingRight)
  const height = element.clientHeight
    - parseCssPixel(style.paddingTop)
    - parseCssPixel(style.paddingBottom)

  return {
    width: Math.max(width, 0),
    height: Math.max(height, 0),
  }
}

/**
 * 读取元素不受 transform 影响的布局尺寸。
 *
 * @param element 目标元素
 * @param activeScale 当前视觉缩放倍率，用于还原 getBoundingClientRect 兜底值
 * @returns 元素布局宽高
 */
function getUnscaledElementSize(element: HTMLElement, activeScale: number): { width: number; height: number } {
  const scale = Number.isFinite(activeScale) && activeScale > 0 ? activeScale : 1
  const rect = element.getBoundingClientRect()

  return {
    width: Math.max(element.scrollWidth, element.offsetWidth, rect.width / scale),
    height: Math.max(element.scrollHeight, element.offsetHeight, rect.height / scale),
  }
}

/**
 * 获取 MathJax 公式组的自然尺寸。
 *
 * @param element 公式内容组元素
 * @param activeScale 当前视觉缩放倍率
 * @returns 自然宽高
 */
function getNaturalContentSize(element: HTMLElement, activeScale: number): { width: number; height: number } {
  const contentSize = getUnscaledElementSize(element, activeScale)
  const containers = Array.from(element.querySelectorAll<HTMLElement>('mjx-container'))
  const childWidth = Math.max(
    0,
    ...containers.map(item => getUnscaledElementSize(item, activeScale).width),
  )
  const childHeight = containers.reduce((total, item) => {
    return total + getUnscaledElementSize(item, activeScale).height
  }, 0)

  return {
    width: Math.max(contentSize.width, childWidth),
    height: Math.max(contentSize.height, childHeight),
  }
}

/**
 * 按 contain 语义计算并应用公式整体缩放比例。
 */
function updateFitScale(): void {
  if (props.fit !== 'contain') {
    contentScale.value = 1
    return
  }

  const root = viewerRef.value
  const content = contentRef.value
  if (!root || !content) {
    contentScale.value = 1
    return
  }

  const availableSize = getAvailableSize(root)
  const naturalSize = getNaturalContentSize(content, contentScale.value)
  if (
    availableSize.width <= 0
    || availableSize.height <= 0
    || naturalSize.width <= 0
    || naturalSize.height <= 0
  ) {
    contentScale.value = 1
    return
  }

  const nextScale = Math.min(
    availableSize.width / naturalSize.width,
    availableSize.height / naturalSize.height,
  )
  contentScale.value = Number.isFinite(nextScale) && nextScale > 0
    ? Math.round(nextScale * 10000) / 10000
    : 1
}

/**
 * 延迟刷新缩放，等待 Vue DOM 更新与浏览器布局完成。
 */
function scheduleFitUpdate(): void {
  if (typeof window === 'undefined') {
    updateFitScale()
    return
  }

  if (fitUpdateTimer !== null) {
    window.clearTimeout(fitUpdateTimer)
  }
  fitUpdateTimer = window.setTimeout(() => {
    fitUpdateTimer = null
    updateFitScale()
  }, 0)
}

/**
 * 刷新 ResizeObserver 监听目标。
 */
function refreshResizeObserver(): void {
  if (!resizeObserver) return

  resizeObserver.disconnect()
  if (viewerRef.value) resizeObserver.observe(viewerRef.value)
  if (contentRef.value) resizeObserver.observe(contentRef.value)
}

/**
 * 使用 MathJax 渲染当前公式内容。
 */
async function renderFormula(): Promise<void> {
  const currentVersion = ++renderVersion
  renderedHtml.value = ''
  error.value = ''
  contentScale.value = 1

  const source = props.content.trim()
  if (!source) {
    scheduleFitUpdate()
    return
  }

  try {
    const html = await renderLatexToString(source, {
      displayMode: props.displayMode,
      throwOnError: props.throwOnError,
      strict: props.strict,
      trust: props.trust,
    })
    if (currentVersion === renderVersion) {
      renderedHtml.value = html
      await nextTick()
      refreshResizeObserver()
      scheduleFitUpdate()
    }
  } catch (reason) {
    if (currentVersion === renderVersion) {
      error.value = `LaTeX 渲染失败：${getErrorMessage(reason)}`
      scheduleFitUpdate()
    }
  }
}

watch(
  () => [props.content, props.displayMode, props.throwOnError, props.strict, props.trust],
  () => {
    void renderFormula()
  },
)

watch(
  () => [props.fit, props.width, props.height, props.minHeight, props.padding],
  async () => {
    await nextTick()
    scheduleFitUpdate()
  },
)

onMounted(() => {
  resizeObserver = new ResizeObserver(() => scheduleFitUpdate())
  refreshResizeObserver()
  void renderFormula()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  if (fitUpdateTimer !== null) {
    window.clearTimeout(fitUpdateTimer)
    fitUpdateTimer = null
  }
})

defineExpose({
  reload: renderFormula,
  updateFit: updateFitScale,
})
</script>

<style scoped>
.latex-viewer {
  box-sizing: border-box;
  display: flex;
  max-width: 100%;
  margin-inline: auto;
  align-items: center;
  justify-content: center;
  overflow: auto;
}

.latex-viewer--fit-contain {
  overflow: hidden;
}

.latex-viewer__content {
  display: flex;
  width: 100%;
  max-width: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.65em;
  text-align: center;
}

.latex-viewer--fit-contain .latex-viewer__content {
  width: max-content;
  max-width: none;
  flex: 0 0 auto;
  overflow: visible;
}

.latex-viewer__content :deep(mjx-container) {
  align-self: center;
  max-width: 100%;
  margin: 0;
  overflow-x: auto;
  overflow-y: hidden;
}

.latex-viewer--fit-contain .latex-viewer__content :deep(mjx-container) {
  max-width: none;
  overflow: visible;
}

.latex-viewer__content :deep(mjx-container[display='true']) {
  display: block;
  width: 100%;
  text-align: center;
}

.latex-viewer--fit-contain .latex-viewer__content :deep(mjx-container[display='true']) {
  width: auto;
}

.latex-viewer__content :deep(mjx-container > svg) {
  display: block;
  margin-inline: auto;
  fill: currentColor;
  stroke: currentColor;
}

.latex-viewer__state {
  color: #94a3b8;
  font-size: 14px;
}

.latex-viewer__state--error {
  color: #dc2626;
}
</style>
