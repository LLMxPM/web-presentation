/**
 * 文件功能：统一打开项目单窗口放映入口。
 * 先同步打开占位窗口再创建新的不可变 preview artifact，避免 await 后被浏览器弹窗拦截。
 */
import { createProjectPreviewArtifact } from '@/api/preview'

export interface ProjectPresentationOptions {
  projectId: number
  entryRoute?: string | null
}

/**
 * 在用户手势内同步预开占位窗口，供保存后继续放映复用。
 * 浏览器只允许用户点击后的同步调用打开新窗口，因此保存前必须先调用本函数。
 */
export function preopenProjectPresentationWindow(): Window | null {
  return typeof window !== 'undefined' ? window.open('about:blank', '_blank') : null
}

/**
 * 生成新的项目 preview artifact 并在新窗口打开。
 * 每次调用都会锁定最新配置；已打开的旧窗口继续停留在旧快照。
 * @param options 项目与入口路由
 * @param preopenedWindow 保存前预开的占位窗口；省略时在函数内同步打开
 */
export async function openProjectPresentation(
  options: ProjectPresentationOptions,
  preopenedWindow?: Window | null,
): Promise<void> {
  const popup = preopenedWindow && !preopenedWindow.closed
    ? preopenedWindow
    : preopenProjectPresentationWindow()
  try {
    const preview = await createProjectPreviewArtifact(options.projectId, options.entryRoute ?? null)
    if (popup && !popup.closed) {
      popup.location.replace(preview.preview_url)
      return
    }
    const fallback = typeof window !== 'undefined' ? window.open(preview.preview_url, '_blank') : null
    if (!fallback) {
      throw new Error('浏览器阻止了新窗口，请允许弹窗后重试。')
    }
  } catch (error) {
    if (popup && !popup.closed) {
      popup.close()
    }
    throw error
  }
}
