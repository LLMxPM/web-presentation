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
 * 生成新的项目 preview artifact 并在新窗口打开。
 * 每次调用都会锁定最新配置；已打开的旧窗口继续停留在旧快照。
 */
export async function openProjectPresentation(options: ProjectPresentationOptions): Promise<void> {
  const popup = typeof window !== 'undefined' ? window.open('about:blank', '_blank') : null
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
