// @vitest-environment jsdom

/**
 * 文件用途：验证 Runtime 独立捕获地址保留页面查询参数，并覆盖离屏舞台的静态帧准备与清理。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { MODEL_STATIC_FRAME_HANDLE_KEY, MODEL_STATIC_FRAME_IMG_ATTR } from '@/core/shared/model-static-frame-contract'

import { clearDefaultModelStaticFrameCache } from './model-static-frames'
import { createOffscreenPageStage, pauseOffscreenMedia, resolveRuntimeCaptureRoute } from './OffscreenPageStage'

afterEach(() => {
  document.body.innerHTML = ''
  clearDefaultModelStaticFrameCache()
})

describe('resolveRuntimeCaptureRoute', () => {
  it('应保留页面查询参数并覆盖 Runtime 捕获标记', () => {
    const result = resolveRuntimeCaptureRoute(
      '/sales?period=2026&runtimeMode=display&runtimeCapture=0',
      'https://runtime.example/preview#/origin',
    )
    const query = new URLSearchParams(result.hash.split('?')[1])

    expect(result.path).toBe('/sales')
    expect(query.get('period')).toBe('2026')
    expect(query.get('runtimeMode')).toBe('normal')
    expect(query.get('runtimeCapture')).toBe('1')
  })
})

describe('OffscreenPageStage 静态帧准备', () => {
  it('capture 应把取消信号传入离屏准备，取消后立即终止', async () => {
    const stage = createOffscreenPageStage()
    const controller = new AbortController()
    controller.abort()

    await expect(stage.capture('/page', { signal: controller.signal })).rejects.toThrow('用户取消导出')

    stage.dispose()
    expect(document.querySelector('iframe')).toBeNull()
  })

  it('preparePage 应同时把捕获标记写入 search 与 hash 路由', async () => {
    const stage = createOffscreenPageStage()
    const iframe = document.querySelector('iframe') as HTMLIFrameElement
    const controller = new AbortController()

    const pending = stage.preparePage('/cover', { signal: controller.signal })
    const url = new URL(iframe.src)

    expect(url.searchParams.get('runtimeCapture')).toBe('1')
    expect(url.searchParams.get('runtimeMode')).toBe('normal')
    expect(url.hash).toContain('/cover?')
    expect(url.hash).toContain('runtimeCapture=1')
    expect(url.hash).toContain('runtimeCaptureTicket=')

    controller.abort()
    await expect(pending).rejects.toThrow('用户取消导出')
    stage.dispose()
  })

  it('pauseOffscreenMedia 应暂停原生媒体且不自动恢复播放', () => {
    const root = document.createElement('div')
    root.innerHTML = '<video autoplay></video><audio autoplay></audio>'
    const pause = vi.fn()
    for (const media of Array.from(root.querySelectorAll('video, audio'))) {
      Object.defineProperty(media, 'pause', { value: pause, configurable: true })
    }

    pauseOffscreenMedia(root)

    expect(pause).toHaveBeenCalledTimes(2)
    expect(root.querySelector('video')?.hasAttribute('autoplay')).toBe(false)
    expect(root.querySelector('audio')?.hasAttribute('autoplay')).toBe(false)
  })

  it('preparePage 应通过页面桥应用指定时间轴状态后再准备静态帧', async () => {
    const stage = createOffscreenPageStage()
    const iframe = document.querySelector('iframe') as HTMLIFrameElement
    const calls: unknown[] = []

    const pending = stage.preparePage('/motion-page', {
      motionSnapshot: { timelineId: 'intro', atMs: 500, visualMode: 'reduced' },
    })
    setTimeout(() => {
      const curDoc = iframe.contentDocument!
      curDoc.open()
      curDoc.write('<!doctype html><html><head></head><body></body></html>')
      curDoc.close()
      const curWin = iframe.contentWindow as unknown as {
        __EDITOR_RUNTIME_PREVIEW_READY__: boolean
        __RUNTIME_APPLY_MOTION_SNAPSHOT__: (request: unknown) => Promise<unknown>
      }
      const page = curDoc.createElement('div')
      page.className = 'runtime-page-print-source'
      page.dataset.runtimeRoutePath = '/motion-page'
      page.dataset.runtimeCaptureTicket = new URLSearchParams(iframe.contentWindow!.location.hash.split('?')[1]).get('runtimeCaptureTicket') || ''
      curDoc.body.appendChild(page)
      curWin.__RUNTIME_APPLY_MOTION_SNAPSHOT__ = async request => {
        calls.push(request)
        return { status: 'applied', timelineId: 'intro', sampledTimeMs: 500 }
      }
      curWin.__EDITOR_RUNTIME_PREVIEW_READY__ = true
    }, 20)

    await pending
    expect(calls).toEqual([{ timelineId: 'intro', atMs: 500, visualMode: 'reduced' }])
    stage.dispose()
  })

  it('preparePage 应准备覆盖图，cleanup 后 iframe 页面无残留', async () => {
    const stage = createOffscreenPageStage()
    const iframe = document.querySelector('iframe') as HTMLIFrameElement
    const captures = { count: 0 }

    const pending = stage.preparePage('/model-page')
    setTimeout(() => {
      const curDoc = iframe.contentDocument!
      curDoc.open()
      curDoc.write('<!doctype html><html><head></head><body></body></html>')
      curDoc.close()
      const curWin = iframe.contentWindow as unknown as { __EDITOR_RUNTIME_PREVIEW_READY__: boolean }
      const page = curDoc.createElement('div')
      page.className = 'runtime-page-print-source'
      page.dataset.runtimeRoutePath = '/model-page'
      page.dataset.runtimeCaptureTicket = new URLSearchParams(iframe.contentWindow!.location.hash.split('?')[1]).get('runtimeCaptureTicket') || ''
      page.style.width = '1920px'
      page.style.height = '1080px'

      const modelRoot = curDoc.createElement('div')
      modelRoot.setAttribute('data-runtime-kit-media', 'v1')
      modelRoot.setAttribute('data-runtime-kit-media-kind', 'model3d')
      modelRoot.style.cssText = 'position: relative; width: 360px; height: 240px;'
      const canvas = curDoc.createElement('canvas')
      canvas.width = 360
      canvas.height = 240
      modelRoot.appendChild(canvas)
      ;(modelRoot as unknown as Record<string, unknown>)[MODEL_STATIC_FRAME_HANDLE_KEY] = {
        describe: () => ({
          resourceName: 'product',
          resourceSrc: 'product.glb',
          viewKey: 'vk',
          frameWidth: 360,
          frameHeight: 240,
        }),
        capture: () => {
          captures.count += 1
          return {
            resourceName: 'product',
            resourceSrc: 'product.glb',
            viewKey: 'vk',
            frameWidth: 360,
            frameHeight: 240,
            dataUrl: 'data:image/png;base64,stage-frame',
          }
        },
      }
      page.appendChild(modelRoot)
      curDoc.body.appendChild(page)
      curWin.__EDITOR_RUNTIME_PREVIEW_READY__ = true
    }, 20)

    const prepared = await pending
    const modelRoot = prepared.element.querySelector('[data-runtime-kit-media-kind="model3d"]') as HTMLElement

    expect(captures.count).toBe(1)
    expect(modelRoot.querySelector(`img[${MODEL_STATIC_FRAME_IMG_ATTR}]`)).not.toBeNull()
    expect(modelRoot.querySelector('canvas')?.style.visibility).toBe('hidden')

    prepared.cleanup()
    expect(modelRoot.querySelector(`img[${MODEL_STATIC_FRAME_IMG_ATTR}]`)).toBeNull()
    expect(modelRoot.querySelector('canvas')?.style.visibility).toBe('')

    // cleanup 幂等
    expect(() => prepared.cleanup()).not.toThrow()

    stage.dispose()
    expect(document.querySelector('iframe')).toBeNull()
  })
})
