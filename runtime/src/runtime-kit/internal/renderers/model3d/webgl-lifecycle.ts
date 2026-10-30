/** 文件功能：合并实例可见性、尺寸与 WebGL 丢失状态，避免任一恢复事件提前解除另一来源的暂挂。 */
interface LifecycleOptions {
  pause(value: boolean): void
  requestRender(): void
  lost(): void
  restored(): void
}

/** 每个 Viewer 独占其 canvas 监听；重绑与卸载都先移除旧监听再接新实例。 */
export function createModelWebglLifecycle(options: LifecycleOptions) {
  let canvas: HTMLCanvasElement | null = null, lost = false, visible = true, sized = true, disposed = false
  /** 所有来源必须同时允许，才恢复绘制和实例 Mixer。 */
  function refresh(): void {
    const paused = disposed || lost || !visible || !sized || document.hidden
    options.pause(paused)
    if (!paused) options.requestRender()
  }
  /** 丢失即撤销旧绘制证明，并通知任务受阻；preventDefault 允许浏览器尝试恢复。 */
  function contextLost(event: Event): void { event.preventDefault(); lost = true; refresh(); options.lost() }
  /** 解除上下文暂挂仍需重新取得真实首帧，不能直接把状态改为 ready。 */
  function contextRestored(): void { lost = false; refresh(); options.restored() }
  /** 拆除监听不销毁由池负责的 renderer/context。 */
  function unbind(): void {
    canvas?.removeEventListener('webglcontextlost', contextLost)
    canvas?.removeEventListener('webglcontextrestored', contextRestored)
    canvas = null
  }
  document.addEventListener('visibilitychange', refresh)
  return {
    bind(element: HTMLCanvasElement) { unbind(); canvas = element; lost = false; canvas.addEventListener('webglcontextlost', contextLost); canvas.addEventListener('webglcontextrestored', contextRestored); refresh() },
    setVisible(value: boolean) { visible = value; refresh() },
    setSized(value: boolean) { sized = value; refresh() },
    refresh,
    unbind,
    dispose() { if (disposed) return; disposed = true; document.removeEventListener('visibilitychange', refresh); unbind(); refresh() },
  }
}
