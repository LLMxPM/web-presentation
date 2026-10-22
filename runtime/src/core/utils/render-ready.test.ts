// @vitest-environment jsdom
/** 文件功能：验证 render-ready 桥记录的静态执行上下文与目标路由，供 Renderer 硬核对。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  initializeRenderReadyHost,
  markRenderPreviewMounted,
  RENDER_READY_PROTOCOL,
  RENDER_READY_PROTOCOL_V2,
} from './render-ready'

afterEach(() => {
  document.body.innerHTML = ''
  vi.useRealTimers()
  delete window.__RENDER_READY__
  delete window.__EDITOR_RUNTIME_PREVIEW_READY__
})

describe('render-ready 静态捕获信息', () => {
  it.each(['error', 'empty'])('主预览模块 %s 时不能把空画布标记为成功', async state => {
    document.body.innerHTML = `<main class="standalone-preview-view"><div data-runtime-view-preview-state="${state}" data-runtime-view-preview-message="模块不存在"></div></main>`
    await markRenderPreviewMounted()
    expect(window.__RENDER_READY__?.contentExceptions).toEqual([{ code: 'PAGE_PREVIEW_LOAD_FAILED', message: '模块不存在' }])
    expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(false)
  })

  it('主预览加载超过限定时间返回错误，不无限等待', async () => {
    vi.useFakeTimers()
    document.body.innerHTML = '<main class="standalone-preview-view"><div data-runtime-view-preview-state="loading"></div></main>'
    const completion = markRenderPreviewMounted({ visualTimeoutMs: 50 })
    await vi.advanceTimersByTimeAsync(50)
    await completion
    expect(window.__RENDER_READY__?.contentExceptions[0].code).toBe('PAGE_PREVIEW_LOAD_TIMEOUT')
    expect(window.__EDITOR_RUNTIME_PREVIEW_READY__).toBe(false)
  })

  it('初始化时记录执行上下文与入口路径', () => {
    initializeRenderReadyHost({
      artifactId: 'rt_1',
      inputDigest: 'digest-1',
      executionContext: 'capture',
      entryPath: '/cover',
    })

    expect(window.__RENDER_READY__).toMatchObject({
      protocol: RENDER_READY_PROTOCOL,
      artifactId: 'rt_1',
      inputDigest: 'digest-1',
      executionContext: 'capture',
      entryPath: '/cover',
      routePath: null,
      mounted: false,
    })
  })

  it('捕获协议 v2 记录双版本能力与时间轴回执位置', () => {
    initializeRenderReadyHost({
      executionContext: 'capture',
      entryPath: '/cover',
      protocol: RENDER_READY_PROTOCOL_V2,
    })

    expect(window.__RENDER_READY__).toMatchObject({
      protocol: RENDER_READY_PROTOCOL_V2,
      protocolVersions: [RENDER_READY_PROTOCOL, RENDER_READY_PROTOCOL_V2],
      motion: null,
    })
  })

  it('挂载完成后写入稳定路由且保留捕获上下文', async () => {
    initializeRenderReadyHost({ executionContext: 'capture', entryPath: '/cover' })
    await markRenderPreviewMounted({
      artifactId: 'rt_1',
      inputDigest: 'digest-1',
      executionContext: 'capture',
      entryPath: '/cover',
      routePath: '/cover',
    })

    expect(window.__RENDER_READY__).toMatchObject({
      mounted: true,
      executionContext: 'capture',
      entryPath: '/cover',
      routePath: '/cover',
      fonts: { ready: true },
      visualAssets: { ready: true },
    })
  })
})
