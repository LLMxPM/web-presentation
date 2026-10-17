// @vitest-environment jsdom
/** 文件功能：验证真实宿主根节点在初始化前获得执行上下文与媒体禁播属性。 */
import { createApp, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it } from 'vitest'
import RuntimeCaptureLayout from '@/runtime-shell/transitions/RuntimeCaptureLayout.vue'
import ViewPreview from '@/runtime-shell/preview/ViewPreview.vue'
import StandalonePreviewView from '@/views/StandalonePreviewView.vue'
import { initializeRuntimeExecution, resetRuntimeExecutionForTests } from './execution-scope'

afterEach(() => {
  resetRuntimeExecutionForTests()
  document.body.innerHTML = ''
})

function mount(component: Parameters<typeof createApp>[0], props: Record<string, unknown> = {}) {
  const root = document.createElement('div')
  document.body.append(root)
  const app = createApp(component, props)
  app.mount(root)
  return { root, app }
}

describe('执行上下文宿主', () => {
  it('编辑器单页预览为交互预览，允许手势但禁止自动播放', async () => {
    resetRuntimeExecutionForTests()
    const { root, app } = mount(StandalonePreviewView, { filePath: '' })
    await nextTick()

    const host = root.querySelector<HTMLElement>('.standalone-preview-view')
    expect(host?.dataset.runtimeExecution).toBe('interactive-preview')
    expect(host?.dataset.runtimeMedia).toBe('gesture')
    const preview = root.querySelector<HTMLElement>('[data-runtime-view-preview-state]')
    expect(preview?.dataset.runtimeExecution).toBe('interactive-preview')
    expect(preview?.dataset.runtimeMedia).toBe('gesture')
    app.unmount()
  })

  it('ViewPreview 默认按缩略图静态上下文处理', async () => {
    resetRuntimeExecutionForTests()
    const { root, app } = mount(ViewPreview, { filePath: '' })
    await nextTick()

    const preview = root.querySelector<HTMLElement>('[data-runtime-view-preview-state]')
    expect(preview?.dataset.runtimeExecution).toBe('thumbnail')
    expect(preview?.dataset.runtimeMedia).toBe('block')
    app.unmount()
  })

  it('捕获宿主使用初始化出的静态策略', async () => {
    initializeRuntimeExecution('?runtimeCapture=1')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { render: () => null } }],
    })
    await router.push('/')
    await router.isReady()
    const root = document.createElement('div')
    document.body.append(root)
    const app = createApp(RuntimeCaptureLayout)
    app.use(router)
    app.mount(root)
    await nextTick()

    const host = root.querySelector<HTMLElement>('.runtime-capture-layout')
    expect(host?.dataset.runtimeExecution).toBe('capture')
    expect(host?.dataset.runtimeMedia).toBe('block')
    app.unmount()
  })
})
