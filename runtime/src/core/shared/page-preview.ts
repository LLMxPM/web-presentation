/**
 * 文件用途：定义单页面预览 iframe 向 Editor 回传 ready/error 状态的版本化消息协议。
 */

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

