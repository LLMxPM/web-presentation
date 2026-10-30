// @vitest-environment jsdom
/**
 * 文件功能：验证 Scene 资源组件 固定受控属性、目标标记与 v1 兼容边界。
 */

import { createApp, nextTick, type App } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { setRuntimePreloadedConfig } from '@/core/utils/path'

import AssetAudioV1 from './AssetAudio.v1.vue'
import AssetModelV3 from './AssetModel.v3.vue'
import AssetVideoV1 from './AssetVideo.v1.vue'

vi.mock('@runtime-kit/internal/renderers/ModelViewer.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      name: 'ModelViewerStub',
      inheritAttrs: false,
      props: {
        name: { type: String, default: '' },
        src: { type: String, default: '' },
        interactive: { type: Boolean, default: false },
        fallback: { type: String, default: '' },
      },
      setup(props, { attrs }) {
        return () => h('div', { class: 'model-viewer-stub', ...attrs }, [
          h('span', { 'data-stub-name': props.name, 'data-stub-interactive': String(props.interactive) }),
        ])
      },
    }),
  }
})

const mountedApps: App<Element>[] = []

beforeEach(() => {
  Object.defineProperty(HTMLMediaElement.prototype, 'pause', { configurable: true, value: vi.fn() })
  setRuntimePreloadedConfig({
    manifest: {
      artifact_id: 'artifact-media',
      tenant_id: 'tenant-1',
      preview_kind: 'project',
      owner_scope: { scope_type: 'project', workspace_id: '7' },
      entry_descriptor: { entry_type: 'route', route: '/' },
      modules: {},
      assets: {
        'demo-video': 'video-hash',
        'page-voice': 'voice-hash',
        product: 'model-hash',
      },
      asset_metadata: {
        'demo-video': { file_hash: 'video-hash', render_type: 'video' },
        'page-voice': { file_hash: 'voice-hash', render_type: 'audio' },
        product: { file_hash: 'model-hash', render_type: 'model3d' },
      },
      asset_base_url: '/assets/workspace-7',
    },
  })
})

afterEach(() => {
  for (const app of mountedApps.splice(0)) app.unmount()
  setRuntimePreloadedConfig(undefined)
  resetRuntimeExecutionForTests()
  document.body.innerHTML = ''
})

async function mount(component: unknown, props: Record<string, unknown>): Promise<HTMLElement> {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(component as never, props)
  mountedApps.push(app)
  app.mount(host)
  await nextTick()
  await nextTick()
  return host
}

describe('Scene 资源组件', () => {
  it('视频显式 automatic 用途隐藏控件且等待 Scene 播放', async () => {
    const host = await mount(AssetVideoV1, { name: 'demo-video', controls: true, autoplay: true, purpose: 'automatic' })

    const root = host.querySelector<HTMLElement>('[data-runtime-kit-media-kind="video"]')
    const video = host.querySelector<HTMLVideoElement>('video')
    expect(root?.dataset.runtimeKitMotion).toBeUndefined()
    expect(root?.dataset.runtimeAssetName).toBe('demo-video')
    expect(video?.getAttribute('src')).toBe('/assets/workspace-7/video-hash')
    expect(video?.controls).toBe(false)
    expect(video?.autoplay).toBe(false)
    expect(video?.loop).toBe(false)
  })

  it('音频旁白用途保留在 v1，拒绝 autoplay 且默认隐藏控件', async () => {
    const host = await mount(AssetAudioV1, {
      name: 'page-voice',
      purpose: 'narration',
      autoplay: true,
      controls: false,
    })

    const root = host.querySelector<HTMLElement>('[data-runtime-kit-media-kind="audio"]')
    const audio = host.querySelector<HTMLAudioElement>('audio')
    expect(root?.dataset.runtimeKitMotion).toBeUndefined()
    expect(root?.dataset.runtimeAssetName).toBe('page-voice')
    expect(audio?.controls).toBe(false)
    expect(audio?.hasAttribute('autoplay')).toBe(false)
    expect(audio?.dataset.runtimeMediaPurpose).toBe('narration')
  })

  it('Scene 模型固定关闭交互且不声明旧时间轴目标', async () => {
    const host = await mount(AssetModelV3, { name: 'product', interactive: true })

    const stub = host.querySelector<HTMLElement>('.model-viewer-stub')
    expect(stub?.dataset.runtimeKitMotion).toBeUndefined()
    expect(stub?.dataset.runtimeAssetName).toBe('product')
    expect(stub?.querySelector('[data-stub-interactive]')?.getAttribute('data-stub-interactive')).toBe('false')
  })
})
