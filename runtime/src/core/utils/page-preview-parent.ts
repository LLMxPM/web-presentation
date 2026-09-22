/**
 * 文件用途：在 Runtime 应用尚未挂载时向页面预览父窗口回传初始化失败消息。
 */
import { PAGE_PREVIEW_ERROR_EVENT, type PagePreviewErrorMessage } from '@/core/shared/page-preview'
import { getRuntimePreviewContext } from '@/core/utils/path'

/**
 * 当前上下文为单页面预览时通知父窗口初始化失败。
 * @param error 初始化阶段错误
 * @returns 是否已发送消息
 */
export function notifyParentPagePreviewError(error: unknown): boolean {
  const previewContext = getRuntimePreviewContext()
  if (
    typeof window === 'undefined'
    || !window.parent
    || previewContext?.previewKind !== 'page'
    || !previewContext.artifactId
  ) {
    return false
  }

  const message: PagePreviewErrorMessage = {
    type: PAGE_PREVIEW_ERROR_EVENT,
    payload: {
      version: 1,
      artifactId: previewContext.artifactId,
      message: error instanceof Error && error.message ? error.message : 'Runtime 初始化失败。',
    },
  }
  window.parent.postMessage(message, '*')
  return true
}

