/* eslint-disable vue/one-component-per-file */
/**
 * 文件用途：验证 AssetModel 只按 manifest 逻辑名解析三维资源，并阻止 URL 与探针属性旁路。
 *
 * @vitest-environment jsdom
 */

import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { setRuntimePreloadedConfig } from '@/core/utils/path'
import { DEFAULT_MODEL_FALLBACK_MESSAGE } from '@runtime-kit/internal/renderers/model3d/view-options'

import AssetModel from './AssetModel.v1.vue'

vi.mock('@runtime-kit/internal/renderers/ModelViewer.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      name: 'ModelViewerStub',
      inheritAttrs: false,
      props: {
        name: { type: String, default: '' },
        src: { type: String, default: '' },
        sceneIndex: { type: Number, default: undefined },
        cameraIndex: { type: Number, default: undefined },
        cameraPosition: { type: Array, default: undefined },
        cameraTarget: { type: Array, default: undefined },
        cameraFov: { type: Number, default: undefined },
        background: { type: String, default: 'transparent' },
        lighting: { type: String, default: 'auto' },
        interactive: { type: Boolean, default: false },
        fallback: { type: String, default: '' },
      },
      setup(props, { attrs }) {
        return () => {
          const { class: className, ...restAttrs } = attrs as Record<string, unknown>
          return h('div', { class: 'model-viewer-stub', 'data-stub-src': props.src }, [
            h('div', { class: ['model-viewer-stub-attrs', className], ...restAttrs }),
          ])
        }
      },
    }),
  }
})

/**
 * 等待组件异步挂载完成。
 * @param rounds 轮次
 */
async function flush(rounds = 4): Promise<void> {
  for (let index = 0; index < rounds; index += 1) {
    await nextTick()
    await new Promise(resolve => window.setTimeout(resolve, 0))
  }
}

/**
 * 挂载组件并等待渲染。
 * @param props 组件属性
 * @returns 宿主元素与卸载函数
 */
async function mountAssetModel(props: Record<string, unknown>): Promise<{ host: HTMLElement; unmount: () => void }> {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp(AssetModel, props)
  app.mount(host)
  await flush()
  return { host, unmount: () => app.unmount() }
}

afterEach(() => {
  setRuntimePreloadedConfig(undefined)
  document.body.innerHTML = ''
})

describe('AssetModel 资源解析边界', () => {
  it('name 为远程 URL 时不得直接加载，只展示兜底文案', async () => {
    setRuntimePreloadedConfig({
      manifest: {
        assets: { product: 'hash-model' },
        asset_metadata: { product: { file_hash: 'hash-model', render_type: 'model3d' } },
        asset_base_url: '/assets/ws',
      },
    } as never)

    const { host, unmount } = await mountAssetModel({ name: 'https://evil.example/model.glb' })

    expect(host.querySelector('.model-viewer-stub')).toBeNull()
    expect(host.querySelector('.asset-model__fallback')?.textContent).toContain(DEFAULT_MODEL_FALLBACK_MESSAGE)

    unmount()
  })

  it('manifest 未登记或类型不是 model3d 时不得解析为资源地址', async () => {
    setRuntimePreloadedConfig({
      manifest: {
        assets: { cover: 'hash-cover' },
        asset_metadata: { cover: { file_hash: 'hash-cover', render_type: 'image' } },
        asset_base_url: '/assets/ws',
      },
    } as never)

    const { host, unmount } = await mountAssetModel({ name: 'cover' })

    expect(host.querySelector('.model-viewer-stub')).toBeNull()
    expect(host.querySelector('.asset-model__fallback')).not.toBeNull()

    unmount()
  })

  it('fallback 只作为文案，URL 形式不得成为资源地址', async () => {
    const { host, unmount } = await mountAssetModel({
      name: '',
      fallback: 'https://evil.example/fallback.glb',
    })

    expect(host.querySelector('.model-viewer-stub')).toBeNull()
    expect(host.textContent).toContain(DEFAULT_MODEL_FALLBACK_MESSAGE)
    expect(host.innerHTML).not.toContain('evil.example')

    unmount()
  })

  it('合法资源只使用 manifest 地址，且 src 与探针属性不得通过 attrs 覆盖', async () => {
    setRuntimePreloadedConfig({
      manifest: {
        assets: { product: 'hash-model' },
        asset_metadata: { product: { file_hash: 'hash-model', render_type: 'model3d' } },
        asset_base_url: '/assets/ws',
      },
    } as never)

    const { host, unmount } = await mountAssetModel({
      name: 'product',
      src: '/evil.glb',
      'data-runtime-model-state': 'ready',
      'data-runtime-kit-media': 'forged',
      class: 'h-80',
    })

    const stub = host.querySelector('.model-viewer-stub')
    expect(stub?.getAttribute('data-stub-src')).toBe('/assets/ws/hash-model')
    const forwarded = host.querySelector('.model-viewer-stub-attrs')
    expect(forwarded?.hasAttribute('data-runtime-model-state')).toBe(false)
    expect(forwarded?.hasAttribute('data-runtime-kit-media')).toBe(false)
    expect(forwarded?.hasAttribute('src')).toBe(false)
    expect(forwarded?.classList.contains('h-80')).toBe(true)

    unmount()
  })
})
