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
  it('正式离屏出口向资源探针传静态视频选项和目标节点', async () => {
    const stage = createOffscreenPageStage()
    const pending = stage.preparePage('/static-page')
    const { win, doc } = mountStaticPage(document.querySelector('iframe')!, '/static-page', 'ready')
    const probe = vi.fn().mockResolvedValue({ ok: true, failed: [], pending: [] })
    Object.assign(win, { __EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__: probe })
    const prepared = await pending
    expect(probe).toHaveBeenCalledWith(expect.objectContaining({ root: doc.querySelector('.runtime-page-print-source'), staticMedia: true, includeAnimations: false }))
    prepared.cleanup()
    stage.dispose()
  })

  it.each(['resource', 'model'])('%s 失败整体中止并保留页码和原因', async reason => {
    const stage = createOffscreenPageStage()
    const pending = stage.preparePage('/static-page', { pageLabel: '第 3 页「三维视频」' })
    const { win, doc } = mountStaticPage(document.querySelector('iframe')!, '/static-page', 'ready')
    Object.assign(win, { __EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__: vi.fn().mockResolvedValue({ ok: reason !== 'resource', failed: [{ message: '视频海报加载失败' }], pending: [] }) })
    if (reason === 'model') doc.querySelector('.runtime-page-print-source')!.innerHTML = '<div data-runtime-kit-media="v1" data-runtime-kit-media-kind="model3d"><canvas /></div>'
    await expect(pending).rejects.toThrow('第 3 页「三维视频」')
    await expect(pending).rejects.toThrow(reason === 'resource' ? '视频海报加载失败' : 'MODEL_STATIC_FRAME_UNAVAILABLE')
    stage.dispose()
  })
  it('旧 JavaScript 调用显式传入时刻选择器时明确拒绝', async () => {
    const stage = createOffscreenPageStage()
    const obsolete = { motionSnapshot: { atMs: 300 } }
    await expect(stage.preparePage('/page', obsolete as never)).rejects.toThrow('不再支持指定动画时刻')
    await expect(stage.capture('/page', obsolete as never)).rejects.toThrow('不再支持指定动画时刻')
    stage.dispose()
  })
  it('默认准备不等待或快进文档动画，也不调用旧采样桥', async () => {
    const stage = createOffscreenPageStage()
    const frame = document.querySelector('iframe')!
    const pending = stage.preparePage('/static-page')
    const { win, doc } = mountStaticPage(frame, '/static-page', 'ready')
    const sample = vi.fn()
    const finish = vi.fn()
    Object.assign(win, { __RUNTIME_APPLY_MOTION_SNAPSHOT__: sample })
    Object.defineProperty(doc, 'getAnimations', { value: () => [{ finish, finished: new Promise(() => {}) }] })
    const prepared = await pending
    expect(sample).not.toHaveBeenCalled()
    expect(finish).not.toHaveBeenCalled()
    prepared.cleanup()
    stage.dispose()
  })

  it.each(['unsupported', 'failed'] as const)('静态 %s 立即中断并携带页码与原因', async status => {
    const stage = createOffscreenPageStage()
    const frame = document.querySelector('iframe')!
    const pending = stage.preparePage('/static-page', { pageLabel: '第 2 页「图表」' })
    mountStaticPage(frame, '/static-page', status)
    await expect(pending).rejects.toThrow('第 2 页「图表」')
    await expect(pending).rejects.toThrow('示例静态原因')
    stage.dispose()
  })

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
      Object.assign(curWin, { __RENDER_READY__: { mounted: true, staticPresentation: { status: 'ready' } } })
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

/** 在当前导航票据内装配就绪桥，模拟 iframe 已完成目标页面静态准备。 */
function mountStaticPage(frame: HTMLIFrameElement, route: string, status: 'ready' | 'unsupported' | 'failed') {
  const doc = frame.contentDocument!
  doc.open()
  doc.write('<!doctype html><html><head></head><body></body></html>')
  doc.close()
  const win = frame.contentWindow!
  const page = doc.createElement('section')
  page.className = 'runtime-page-print-source'
  page.dataset.runtimeRoutePath = route
  page.dataset.runtimeCaptureTicket = new URLSearchParams(new URL(frame.src).hash.split('?')[1]).get('runtimeCaptureTicket')!
  doc.body.append(page)
  Object.assign(win, {
    __EDITOR_RUNTIME_PREVIEW_READY__: status === 'ready',
    __RENDER_READY__: { mounted: true, staticPresentation: { status, code: status === 'unsupported' ? 'STATIC_PRESENTATION_UNAVAILABLE' : 'STATIC_PRESENTATION_FAILED', message: '示例静态原因' } },
  })
  return { win, doc }
}
