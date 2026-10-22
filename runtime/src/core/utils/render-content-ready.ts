/** 文件功能：等待单页主画布异步模块挂载，防止占位画面先被标记为渲染就绪。 */
import type { RenderContentException } from './render-ready'

/** 只等待单页主预览，侧栏缩略图不参与；模块终态必须来自 ViewPreview 的真实状态。 */
export function waitForMainPreviewContent(timeoutMs: number): Promise<RenderContentException[]> {
  const preview = document.querySelector('.standalone-preview-view [data-runtime-view-preview-state]')
  if (!preview) return Promise.resolve([])
  return new Promise(resolve => {
    const observer = new MutationObserver(checkState)
    /** 状态提交后子页面已完成本轮 DOM 挂载，可以继续等待时间轴初始化。 */
    function checkState(): void {
      const state = preview!.getAttribute('data-runtime-view-preview-state')
      if (state === 'loading') return
      observer.disconnect()
      clearTimeout(timer)
      resolve(state === 'ready' ? [] : [{
        code: 'PAGE_PREVIEW_LOAD_FAILED',
        message: (preview!.getAttribute('data-runtime-view-preview-message') || '页面预览模块加载失败。').slice(0, 240),
      }])
    }
    observer.observe(preview, { attributes: true, attributeFilter: ['data-runtime-view-preview-state'] })
    const timer = setTimeout(() => {
      observer.disconnect()
      resolve([{ code: 'PAGE_PREVIEW_LOAD_TIMEOUT', message: '页面预览模块未在限定时间内挂载。' }])
    }, timeoutMs)
    checkState()
  })
}
