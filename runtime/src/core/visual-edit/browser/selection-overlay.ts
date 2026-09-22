/**
 * 文件用途：管理 Runtime 可视化编辑选区与悬停提示的 fixed 覆盖层，并跟踪滚动与缩放。
 */

export interface VisualEditSelectionOverlay {
  show(targets: Element[]): void
  clear(): void
  dispose(): void
}

type VisualEditOverlayKind = 'selection' | 'hover'

/** 创建不触碰业务元素 class/style 的多目标选区覆盖层。 */
export function createSelectionOverlay(
  runtimeWindow: Window,
  runtimeDocument: Document,
): VisualEditSelectionOverlay {
  return createVisualEditOverlay(runtimeWindow, runtimeDocument, 'selection')
}

/** 创建不触碰业务元素 class/style 的单目标悬停覆盖层。 */
export function createHoverOverlay(
  runtimeWindow: Window,
  runtimeDocument: Document,
): VisualEditSelectionOverlay {
  return createVisualEditOverlay(runtimeWindow, runtimeDocument, 'hover')
}

/**
 * 创建指定视觉类型的覆盖层；悬停层位于选区层下方，避免遮盖已选中状态。
 */
function createVisualEditOverlay(
  runtimeWindow: Window,
  runtimeDocument: Document,
  kind: VisualEditOverlayKind,
): VisualEditSelectionOverlay {
  let targets: Element[] = []
  let overlays: HTMLDivElement[] = []
  let tracking = false

  const update = (): void => {
    targets.forEach((target, index) => {
      const overlay = overlays[index]
      if (!overlay || !target.isConnected) return
      const rect = target.getBoundingClientRect()
      overlay.style.left = `${rect.left}px`
      overlay.style.top = `${rect.top}px`
      overlay.style.width = `${rect.width}px`
      overlay.style.height = `${rect.height}px`
    })
  }
  const startTracking = (): void => {
    if (tracking) return
    tracking = true
    runtimeWindow.addEventListener('resize', update)
    runtimeDocument.addEventListener('scroll', update, true)
  }
  const stopTracking = (): void => {
    if (!tracking) return
    tracking = false
    runtimeWindow.removeEventListener('resize', update)
    runtimeDocument.removeEventListener('scroll', update, true)
  }
  const clear = (): void => {
    targets = []
    overlays.forEach(overlay => overlay.remove())
    overlays = []
    stopTracking()
  }

  return {
    show(nextTargets: Element[]): void {
      targets = nextTargets
      while (overlays.length < targets.length) {
        const overlay = runtimeDocument.createElement('div')
        overlay.setAttribute('aria-hidden', 'true')
        overlay.dataset.pageVisualOverlay = kind
        Object.assign(overlay.style, {
          position: 'fixed',
          pointerEvents: 'none',
          boxSizing: 'border-box',
          border: kind === 'selection' ? '2px solid #2563eb' : '1px dashed #0ea5e9',
          borderRadius: '2px',
          zIndex: kind === 'selection' ? '2147483647' : '2147483646',
        })
        runtimeDocument.body.appendChild(overlay)
        overlays.push(overlay)
      }
      while (overlays.length > targets.length) overlays.pop()?.remove()
      update()
      startTracking()
    },
    clear,
    dispose: clear,
  }
}
