// @vitest-environment jsdom
/** 文件功能：验证 VideoViewer 暴露受控 video 实例并转发播放、暂停、结束、错误与重置事件。 */
import { createApp, h, nextTick, ref, type App } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import VideoViewer from './VideoViewer.vue'

const mountedApps: App<Element>[] = []

afterEach(() => {
  for (const app of mountedApps.splice(0)) app.unmount()
  document.body.innerHTML = ''
})

/** 挂载带事件监听的 VideoViewer，返回受控实例与事件记录。 */
async function mountViewer() {
  const events: Array<{ type: string; payload?: unknown }> = []
  const viewer = ref<InstanceType<typeof VideoViewer> | null>(null)
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({
    render: () => h(VideoViewer, {
      src: '/demo.mp4',
      ref: viewer,
      onPlay: (event: Event) => events.push({ type: 'play', payload: event }),
      onPause: (event: Event) => events.push({ type: 'pause', payload: event }),
      onEnded: (event: Event) => events.push({ type: 'ended', payload: event }),
      onError: (event: Event) => events.push({ type: 'error', payload: event }),
      onMediaReady: (element: HTMLVideoElement) => events.push({ type: 'media-ready', payload: element }),
      onMediaUnmounted: () => events.push({ type: 'media-unmounted' }),
      onMediaReset: () => events.push({ type: 'media-reset' }),
    }),
  })
  mountedApps.push(app)
  app.mount(host)
  await nextTick()
  await nextTick()
  return { viewer, events }
}

describe('VideoViewer media events', () => {
  it('暴露实际 video 元素并转发原生媒体事件', async () => {
    const { viewer, events } = await mountViewer()
    const element = viewer.value?.getMediaElement()
    expect(element).toBeInstanceOf(HTMLVideoElement)
    expect(events).toContainEqual({ type: 'media-ready', payload: element })

    element?.dispatchEvent(new Event('play'))
    element?.dispatchEvent(new Event('pause'))
    element?.dispatchEvent(new Event('ended'))
    element?.dispatchEvent(new Event('error'))
    element?.dispatchEvent(new Event('loadstart'))

    expect(events.map(event => event.type)).toEqual(
      expect.arrayContaining(['play', 'pause', 'ended', 'error', 'media-reset']),
    )
  })

  it('src 被清空时通知宿主注销受控实例', async () => {
    const { viewer, events } = await mountViewer()
    expect(viewer.value?.getMediaElement()).toBeInstanceOf(HTMLVideoElement)

    const host = document.createElement('div')
    document.body.append(host)
    const src = ref('/demo.mp4')
    const app = createApp({
      render: () => h(VideoViewer, {
        src: src.value,
        onMediaUnmounted: () => events.push({ type: 'media-unmounted' }),
      }),
    })
    mountedApps.push(app)
    app.mount(host)
    await nextTick()
    src.value = ''
    await nextTick()
    await nextTick()

    expect(events).toContainEqual({ type: 'media-unmounted' })
  })
})
