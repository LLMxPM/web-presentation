// @vitest-environment jsdom
/** 文件功能：验证 render-ready 桥记录的静态执行上下文与目标路由，供 Renderer 硬核对。 */
import { afterEach, describe, expect, it } from 'vitest'
import {
  initializeRenderReadyHost,
  markRenderPreviewMounted,
  RENDER_READY_PROTOCOL,
} from './render-ready'

afterEach(() => {
  delete window.__RENDER_READY__
  delete window.__EDITOR_RUNTIME_PREVIEW_READY__
})

describe('render-ready 静态捕获信息', () => {
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
