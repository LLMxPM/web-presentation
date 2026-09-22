// @vitest-environment jsdom

/**
 * 文件用途：验证单页预览宿主页把页面模块 ready/error 终态回传给 Editor。
 */
import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PAGE_PREVIEW_ERROR_EVENT, PAGE_PREVIEW_READY_EVENT } from '@/core/shared/page-preview'
import StandalonePreviewView from './StandalonePreviewView.vue'

const previewState = vi.hoisted(() => ({
  value: { state: 'ready', message: '' } as {
    state: 'loading' | 'ready' | 'error' | 'empty'
    message: string
  },
}))

vi.mock('@/core/utils/path', () => ({
  getRuntimePreviewContext: () => ({ artifactId: 'artifact-page-1' }),
  getRuntimePreloadedConfig: () => undefined,
}))

vi.mock('@/runtime-shell/preview/ViewPreview.vue', () => ({
  default: {
    name: 'ViewPreviewStub',
    emits: ['state-change'],
    setup(_props: unknown, { emit }: { emit: (event: string, payload: unknown) => void }) {
      emit('state-change', previewState.value)
      return () => null
    },
  },
}))

afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe('StandalonePreviewView', () => {
  it('页面模块 ready 时应回传带 artifact 的版本化消息', async () => {
    previewState.value = { state: 'ready', message: '' }
    const postMessage = vi.spyOn(window, 'postMessage').mockImplementation(() => undefined)
    const app = mountView()
    await nextTick()

    expect(postMessage).toHaveBeenCalledWith({
      type: PAGE_PREVIEW_READY_EVENT,
      payload: { version: 1, artifactId: 'artifact-page-1' },
    }, '*')
    app.unmount()
  })

  it('页面模块 error 时应回传真实错误', async () => {
    previewState.value = { state: 'error', message: '模块加载失败' }
    const postMessage = vi.spyOn(window, 'postMessage').mockImplementation(() => undefined)
    const app = mountView()
    await nextTick()

    expect(postMessage).toHaveBeenCalledWith({
      type: PAGE_PREVIEW_ERROR_EVENT,
      payload: { version: 1, artifactId: 'artifact-page-1', message: '模块加载失败' },
    }, '*')
    app.unmount()
  })
})

/** 挂载单页预览宿主页并返回应用实例。 */
function mountView() {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp(StandalonePreviewView, {
    filePath: 'src/views/demo.vue',
  })
  app.mount(host)
  return app
}
