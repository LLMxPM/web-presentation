/** 文件用途：验证导出取消覆盖响应正文、舞台等待和下载之前的异步期限。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PPTXImageDataResolver } from '../pptx/PPTXImageDataResolver'
import { PPTXSvgSerializer } from '../pptx/PPTXSvgSerializer'
import { PPTXCssParser } from '../pptx/PPTXCssParser'
import { createOffscreenPageStage } from './OffscreenPageStage'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); document.body.innerHTML = '' })

describe('导出取消与期限', () => {
  it('图片响应头返回后正文挂起，取消仍终止网络并返回取消错误', async () => {
    const controller = new AbortController()
    let networkSignal: AbortSignal | undefined
    vi.stubGlobal('fetch', vi.fn(async (_url, init) => {
      networkSignal = init.signal
      return { ok: true, headers: new Headers({ 'content-type': 'image/png' }), arrayBuffer: () => new Promise(() => {}) }
    }))
    const pending = new PPTXImageDataResolver().resolve('https://example.test/image.png', controller.signal)
    await Promise.resolve()
    controller.abort()
    await expect(pending).rejects.toThrow('用户取消导出')
    expect(networkSignal?.aborted).toBe(true)
  })

  it('SVG 正文读取受同一个超时信号控制', async () => {
    vi.useFakeTimers()
    let networkSignal: AbortSignal | undefined
    vi.stubGlobal('fetch', vi.fn(async (_url, init) => {
      networkSignal = init.signal
      return { ok: true, text: () => new Promise(() => {}) }
    }))
    const serializer = new PPTXSvgSerializer(new PPTXCssParser(), () => ({ width: 1, height: 1 }))
    const pending = serializer.resolveSvgSource('https://example.test/image.svg')
    await vi.advanceTimersByTimeAsync(10000)
    expect(await pending).toBe('')
    expect(networkSignal?.aborted).toBe(true)
  })

  it('页面准备期间取消立即拒绝，舞台由调用方 finally 释放', async () => {
    const controller = new AbortController()
    const stage = createOffscreenPageStage()
    const pending = stage.preparePage('/waiting', { signal: controller.signal })
    controller.abort()
    await expect(pending).rejects.toThrow('用户取消导出')
    stage.dispose()
    expect(document.querySelector('iframe')).toBeNull()
  })
})
