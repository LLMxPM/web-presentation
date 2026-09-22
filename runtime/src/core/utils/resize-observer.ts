/**
 * 文件用途：提供 ResizeObserver 回调调度工具，避免在同一轮布局观测中同步写入 DOM。
 */

/**
 * 创建将回调延后到下一帧执行的 ResizeObserver。
 * @param callback 尺寸变化后的处理函数
 * @returns ResizeObserver 实例
 */
export function createRafResizeObserver(callback: ResizeObserverCallback): ResizeObserver {
  let frameId: number | null = null
  let latestEntries: ResizeObserverEntry[] = []

  return new ResizeObserver((entries, observer) => {
    latestEntries = entries
    if (frameId !== null) {
      return
    }

    frameId = requestResizeFrame(() => {
      frameId = null
      callback(latestEntries, observer)
    })
  })
}

/**
 * 请求下一帧执行；测试或特殊环境缺少 requestAnimationFrame 时回退到 timeout。
 * @param callback 待执行任务
 * @returns 调度句柄
 */
function requestResizeFrame(callback: FrameRequestCallback): number {
  if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
    return window.requestAnimationFrame(callback)
  }
  return window.setTimeout(() => callback(performance.now()), 0)
}
