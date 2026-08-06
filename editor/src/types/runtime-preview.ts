/**
 * 文件功能：定义 Editor 页面预览状态与 Runtime iframe ready/error 消息协议。
 */

export type RuntimePreviewStatus = 'idle' | 'generating' | 'loading' | 'slow' | 'ready' | 'error'

export const PAGE_PREVIEW_READY_EVENT = 'page-preview:ready'
export const PAGE_PREVIEW_ERROR_EVENT = 'page-preview:error'

export interface PagePreviewReadyMessage {
  type: typeof PAGE_PREVIEW_READY_EVENT
  payload: {
    version: 1
    artifactId: string
  }
}

export interface PagePreviewErrorMessage {
  type: typeof PAGE_PREVIEW_ERROR_EVENT
  payload: {
    version: 1
    artifactId: string
    message: string
  }
}

