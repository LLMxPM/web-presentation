/* eslint-disable vue/one-component-per-file */
/**
 * 文件用途：验证三维渲染器的状态机与探针契约（jsdom，不依赖真实 WebGL）。
 *
 * @vitest-environment jsdom
 */

import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import { setRuntimePreloadedConfig } from '@/core/utils/path'
import { MODEL_STATIC_FRAME_HANDLE_KEY, readModelStaticFrameHandle } from '@/core/shared/model-static-frame-contract'

import ModelViewer from './ModelViewer.vue'
import { DEFAULT_MODEL_FALLBACK_MESSAGE } from './model3d/view-options'

/**
 * 等待组件内部异步状态推进。
 * @param rounds 轮次
 */
async function flush(rounds = 6): Promise<void> {
  for (let index = 0; index < rounds; index += 1) {
    await nextTick()
    await new Promise(resolve => window.setTimeout(resolve, 0))
  }
}

afterEach(() => {
  setRuntimePreloadedConfig(undefined)
  document.body.innerHTML = ''
})

describe('ModelViewer 状态机', () => {
  it('无效展示参数应在加载前进入 error 态并展示 fallback 文案', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ModelViewer, {
      name: 'product',
      src: './product.glb',
      cameraIndex: 0,
      cameraFov: 45,
    })
    app.mount(host)
    await flush()

    const root = host.querySelector<HTMLElement>('.model-viewer')
    expect(root?.dataset.runtimeModelState).toBe('error')
    expect(root?.dataset.runtimeModelMessage).toContain('cameraFov')
    expect(host.textContent).toContain(DEFAULT_MODEL_FALLBACK_MESSAGE)
    expect(host.querySelector('.model-viewer__error-message')?.textContent).toContain(DEFAULT_MODEL_FALLBACK_MESSAGE)

    app.unmount()
  })

  it('render_type 与 model3d 不匹配时应给出明确错误而不是渲染引擎', async () => {
    setRuntimePreloadedConfig({
      manifest: {
        asset_metadata: {
          product: { file_hash: 'h1', render_type: 'image' },
        },
        assets: { product: 'h1' },
      },
    } as never)

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ModelViewer, {
      name: 'product',
      src: './product.glb',
    })
    app.mount(host)
    await flush()

    const root = host.querySelector<HTMLElement>('.model-viewer')
    expect(root?.dataset.runtimeModelState).toBe('error')
    expect(root?.dataset.runtimeModelMessage).toContain('image')
    expect(host.querySelector('.model-viewer__error-detail')?.textContent).toContain('image')

    app.unmount()
  })

  it('外部透传属性不得覆盖媒体与探针契约属性', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ModelViewer, {
      name: 'product',
      src: '',
      'data-runtime-model-state': 'ready',
      'data-runtime-model-message': 'forged',
      'data-runtime-kit-media': 'forged',
      'data-runtime-kit-media-kind': 'image',
    })
    app.mount(host)
    await flush()

    const root = host.querySelector<HTMLElement>('.model-viewer')
    expect(root?.dataset.runtimeKitMedia).toBe('v1')
    expect(root?.dataset.runtimeKitMediaKind).toBe('model3d')
    expect(root?.dataset.runtimeModelState).toBe('error')
    expect(root?.dataset.runtimeModelMessage).not.toBe('forged')

    app.unmount()
  })

  it('根节点应声明媒体与探针契约属性', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ModelViewer, {
      name: 'product',
      src: '',
    })
    app.mount(host)
    await flush()

    const root = host.querySelector<HTMLElement>('.model-viewer')
    expect(root?.dataset.runtimeKitMedia).toBe('v1')
    expect(root?.dataset.runtimeKitMediaKind).toBe('model3d')
    expect(root?.dataset.runtimeModelState).toMatch(/^(loading|ready|error)$/)
    // 无 src 时应进入错误态并展示兜底文案。
    expect(root?.dataset.runtimeModelState).toBe('error')
    expect(host.textContent).toContain(DEFAULT_MODEL_FALLBACK_MESSAGE)

    app.unmount()
  })

  it('挂载应注册静态帧采集句柄，卸载应注销；未就绪时 describe/capture 返回 null', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ModelViewer, {
      name: 'product',
      src: '',
    })
    app.mount(host)
    await flush()

    const root = host.querySelector<HTMLElement>('.model-viewer')
    expect(root).not.toBeNull()

    // jsdom 无 WebGL：实例处于错误态，句柄存在但必须拒绝采集。
    const handle = readModelStaticFrameHandle(root!)
    expect(handle).not.toBeNull()
    expect(handle?.describe()).toBeNull()
    expect(handle?.capture()).toBeNull()

    // 暴露的采集入口与句柄共享同一套就绪门禁
    const exposed = (app._instance?.exposed ?? {}) as { captureStaticFrame?: () => unknown }
    expect(exposed.captureStaticFrame?.()).toBeNull()

    app.unmount()
    expect((root as unknown as Record<string, unknown>)[MODEL_STATIC_FRAME_HANDLE_KEY]).toBeUndefined()
  })
})
