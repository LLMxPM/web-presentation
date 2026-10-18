// @vitest-environment jsdom
/** 文件功能：验证 AssetAudio.v1 只按资源逻辑名解析地址、应用动态控件默认值并阻止 autoplay 旁路。 */
import { createApp, nextTick, type App } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  resetRuntimeExecutionForTests,
} from '@/core/execution/execution-scope'
import { setRuntimePreloadedConfig } from '@/core/utils/path'
import AssetAudio from './AssetAudio.v1.vue'

const mountedApps: App<Element>[] = []

beforeEach(() => {
  Object.defineProperty(HTMLMediaElement.prototype, 'pause', { configurable: true, value: vi.fn() })
  setRuntimePreloadedConfig({
    manifest: {
      artifact_id: 'artifact-audio',
      tenant_id: 'tenant-1',
      preview_kind: 'project',
      owner_scope: { scope_type: 'project', workspace_id: '7' },
      entry_descriptor: { entry_type: 'route', route: '/' },
      modules: {},
      assets: { 'page-voice': 'voice-hash' },
      asset_metadata: {
        'page-voice': { file_hash: 'voice-hash', render_type: 'audio' },
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

/** 挂载公开音频组件并等待内部媒体注册。 */
async function mountAssetAudio(props: Record<string, unknown>) {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(AssetAudio, props)
  mountedApps.push(app)
  app.mount(host)
  await nextTick()
  await nextTick()
  return { host, app }
}

describe('AssetAudio.v1', () => {
  it('name 命中 manifest 时应解析资源地址并应用内容音频默认值', async () => {
    const { host } = await mountAssetAudio({ name: 'page-voice' })
    const audio = host.querySelector<HTMLAudioElement>('audio')

    expect(audio?.getAttribute('src')).toBe('/assets/workspace-7/voice-hash')
    expect(audio?.controls).toBe(true)
    expect(audio?.dataset.runtimeMediaPurpose).toBe('content')
  })

  it('资源加载失败时应回退到 fallback URL，兜底也失败才展示兜底文案', async () => {
    const fallbackUrl = await mountAssetAudio({ name: 'missing', fallback: '/fallback/voice.mp3' })
    const primaryAudio = fallbackUrl.host.querySelector('audio')!
    expect(primaryAudio.getAttribute('src')).toBe('./missing')

    primaryAudio.dispatchEvent(new Event('error'))
    await nextTick()
    const fallbackAudio = fallbackUrl.host.querySelector<HTMLAudioElement>('audio')!
    expect(fallbackAudio.getAttribute('src')).toBe('/fallback/voice.mp3')

    fallbackAudio.dispatchEvent(new Event('error'))
    await nextTick()
    expect(fallbackUrl.host.querySelector('audio')).toBeNull()
    expect(fallbackUrl.host.textContent).toContain('音频资源无法渲染')

    const fallbackMessage = await mountAssetAudio({ name: 'missing', fallback: '请补充旁白资源' })
    fallbackMessage.host.querySelector('audio')!.dispatchEvent(new Event('error'))
    await nextTick()
    expect(fallbackMessage.host.querySelector('audio')).toBeNull()
    expect(fallbackMessage.host.textContent).toContain('请补充旁白资源')
  })

  it('narration+loop 与空 name 应显示有界错误且不渲染 audio', async () => {
    const invalidNarration = await mountAssetAudio({ name: 'page-voice', purpose: 'narration', loop: true })
    expect(invalidNarration.host.querySelector('audio')).toBeNull()
    expect(invalidNarration.host.textContent).toContain('页面旁白不允许循环播放')

    const emptyName = await mountAssetAudio({ name: '' })
    expect(emptyName.host.querySelector('audio')).toBeNull()
    expect(emptyName.host.textContent).toContain('音频资源名不能为空')
  })

  it('autoplay 透传属性不得落到原生 audio 或容器', async () => {
    const { host } = await mountAssetAudio({ name: 'page-voice', autoplay: true })

    expect(host.querySelector('audio')?.hasAttribute('autoplay')).toBe(false)
    expect(host.querySelector('.audio-viewer')?.hasAttribute('autoplay')).toBe(false)
  })
})
