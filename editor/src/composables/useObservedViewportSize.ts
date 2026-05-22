// 文件功能：提供可复用的预览视口尺寸监听与 contain 缩放计算，统一处理舞台类容器的尺寸测量。
import { onBeforeUnmount, reactive, ref } from 'vue'

interface UseObservedViewportSizeOptions {
  subtractPadding?: boolean
}

interface CalculateContainScaleOptions {
  viewportWidth: number
  viewportHeight: number
  contentWidth: number
  contentHeight: number
  maxScale?: number
}

/**
 * 监听指定元素的可用宽高，支持按需扣除元素内边距。
 * @param options 视口测量选项
 * @returns 视口引用、尺寸状态与监听控制方法
 */
export function useObservedViewportSize(options: UseObservedViewportSizeOptions = {}) {
  const viewportRef = ref<HTMLElement | null>(null)
  const viewportSize = reactive({
    width: 0,
    height: 0,
  })

  let viewportResizeObserver: ResizeObserver | null = null

  /**
   * 读取当前元素可用宽高，必要时扣除 padding。
   */
  function updateViewportSize(): void {
    const element = viewportRef.value
    if (!element) {
      viewportSize.width = 0
      viewportSize.height = 0
      return
    }

    const rect = element.getBoundingClientRect()
    let width = rect.width
    let height = rect.height

    if (options.subtractPadding) {
      const computedStyle = window.getComputedStyle(element)
      const horizontalPadding = Number.parseFloat(computedStyle.paddingLeft || '0')
        + Number.parseFloat(computedStyle.paddingRight || '0')
      const verticalPadding = Number.parseFloat(computedStyle.paddingTop || '0')
        + Number.parseFloat(computedStyle.paddingBottom || '0')
      width -= horizontalPadding
      height -= verticalPadding
    }

    viewportSize.width = Math.max(width, 0)
    viewportSize.height = Math.max(height, 0)
  }

  /**
   * 开始监听当前元素尺寸变化，并立即同步一次结果。
   */
  function observeViewport(): void {
    if (!viewportRef.value || typeof ResizeObserver === 'undefined') {
      updateViewportSize()
      return
    }

    disconnectViewportObserver()
    viewportResizeObserver = new ResizeObserver(() => {
      updateViewportSize()
    })
    viewportResizeObserver.observe(viewportRef.value)
    updateViewportSize()
  }

  /**
   * 释放当前尺寸监听器，避免组件销毁后残留观察器。
   */
  function disconnectViewportObserver(): void {
    viewportResizeObserver?.disconnect()
    viewportResizeObserver = null
  }

  onBeforeUnmount(() => {
    disconnectViewportObserver()
  })

  return {
    viewportRef,
    viewportSize,
    updateViewportSize,
    observeViewport,
    disconnectViewportObserver,
  }
}

/**
 * 计算内容在视口内的 contain 等比缩放值。
 * @param options 视口、内容尺寸与最大缩放约束
 * @returns 不超过最大值的等比缩放结果
 */
export function calculateContainScale(options: CalculateContainScaleOptions): number {
  const {
    viewportWidth,
    viewportHeight,
    contentWidth,
    contentHeight,
    maxScale = 1,
  } = options

  if (viewportWidth <= 0 || viewportHeight <= 0 || contentWidth <= 0 || contentHeight <= 0) {
    return maxScale
  }

  const widthScale = viewportWidth / contentWidth
  const heightScale = viewportHeight / contentHeight
  return Math.min(widthScale, heightScale, maxScale)
}
