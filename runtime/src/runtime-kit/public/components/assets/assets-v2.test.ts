// @vitest-environment jsdom
/**
 * 文件功能：验证 Asset*.v2 固定受控属性、目标标记与 v1 兼容边界。
 */

import { createApp, nextTick, type App } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { setRuntimePreloadedConfig } from '@/core/utils/path'

import AssetAudioV2 from './AssetAudio.v2.vue'
import AssetModelV2 from './AssetModel.v2.vue'
import AssetVideoV2 from './AssetVideo.v2.vue'

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

describe('Asset*.v2', () => {
  it('视频固定隐藏控件、禁止自动播放并声明时间轴目标', async () => {
    const host = await mount(AssetVideoV2, { name: 'demo-video', controls: true })

    const root = host.querySelector<HTMLElement>('[data-runtime-kit-media-kind="video"]')
    const video = host.querySelector<HTMLVideoElement>('video')
    expect(root?.dataset.runtimeKitMotion).toBe('timeline')
    expect(root?.dataset.runtimeAssetName).toBe('demo-video')
    expect(video?.getAttribute('src')).toBe('/assets/workspace-7/video-hash')
    expect(video?.controls).toBe(false)
    expect(video?.autoplay).toBe(false)
    expect(video?.loop).toBe(false)
  })

  it('音频固定隐藏控件、拒绝 autoplay 且保留旁白用途', async () => {
    const host = await mount(AssetAudioV2, {
      name: 'page-voice',
      purpose: 'narration',
      autoplay: true,
      controls: true,
    })

    const root = host.querySelector<HTMLElement>('[data-runtime-kit-media-kind="audio"]')
    const audio = host.querySelector<HTMLAudioElement>('audio')
    expect(root?.dataset.runtimeKitMotion).toBe('timeline')
    expect(root?.dataset.runtimeAssetName).toBe('page-voice')
    expect(audio?.controls).toBe(false)
    expect(audio?.hasAttribute('autoplay')).toBe(false)
    expect(audio?.dataset.runtimeMediaPurpose).toBe('narration')
  })

  it('模型固定关闭交互并声明时间轴目标', async () => {
    const host = await mount(AssetModelV2, { name: 'product', interactive: true })

    const stub = host.querySelector<HTMLElement>('.model-viewer-stub')
    expect(stub?.dataset.runtimeKitMotion).toBe('timeline')
    expect(stub?.dataset.runtimeAssetName).toBe('product')
    expect(stub?.querySelector('[data-stub-interactive]')?.getAttribute('data-stub-interactive')).toBe('false')
  })
})
