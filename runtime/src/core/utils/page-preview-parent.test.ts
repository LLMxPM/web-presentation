// @vitest-environment jsdom

/**
 * 文件用途：验证 Runtime 挂载前失败时仅为页面预览回传版本化错误消息。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PAGE_PREVIEW_ERROR_EVENT } from '@/core/shared/page-preview'
import { notifyParentPagePreviewError } from '@/core/utils/page-preview-parent'

const previewContext = vi.hoisted(() => ({
  value: { previewKind: 'page', artifactId: 'artifact-page-1' } as {
    previewKind: string
    artifactId: string
  } | null,
}))

vi.mock('@/core/utils/path', () => ({
  getRuntimePreviewContext: () => previewContext.value,
}))

afterEach(() => vi.restoreAllMocks())

describe('notifyParentPagePreviewError', () => {
  it('页面预览初始化失败时应回传当前 artifact 错误', () => {
    const postMessage = vi.spyOn(window, 'postMessage').mockImplementation(() => undefined)
    expect(notifyParentPagePreviewError(new Error('配置加载失败'))).toBe(true)
    expect(postMessage).toHaveBeenCalledWith({
      type: PAGE_PREVIEW_ERROR_EVENT,
      payload: { version: 1, artifactId: 'artifact-page-1', message: '配置加载失败' },
    }, '*')
  })

  it('非页面预览不应发送页面错误消息', () => {
    previewContext.value = { previewKind: 'component', artifactId: 'artifact-component-1' }
    const postMessage = vi.spyOn(window, 'postMessage').mockImplementation(() => undefined)
    expect(notifyParentPagePreviewError(new Error('组件错误'))).toBe(false)
    expect(postMessage).not.toHaveBeenCalled()
    previewContext.value = { previewKind: 'page', artifactId: 'artifact-page-1' }
  })
})

