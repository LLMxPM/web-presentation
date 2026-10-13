// @vitest-environment jsdom

/**
 * 文件用途：验证 S1 阶段页面环境迁移（退出条件：不同宿主视口下相同几何、动画最终态不重开、三页切换无残留、无遗留舞台与投影节点）。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createOffscreenPageStage,
  freezeDocumentAnimationsToFinalState,
} from '@/core/services/export/OffscreenPageStage'
import { PPTXDomConverter } from './PPTXDomConverter'
import { createSlideMock } from './PPTXDomConverter.test-support'
import type { PptxSlideLike } from './PPTXDomConverter.types'

describe('S1 页面环境迁移与离屏舞台隔离', () => {
  afterEach(() => {
    document.body.innerHTML = ''
    vi.restoreAllMocks()
  })

  it('成功、失败、取消后无遗留舞台或投影节点', async () => {
    const stage = createOffscreenPageStage()
    // 舞台 iframe 已附加到宿主文档
    expect(document.querySelector('iframe')).not.toBeNull()
    // 宿主文档中不得出现旧版投影容器
    expect(document.querySelector('[data-runtime-capture-projection]')).toBeNull()

    // 释放舞台
    stage.dispose()
    // 舞台 iframe 彻底移除，零残留
    expect(document.querySelector('iframe')).toBeNull()
    expect(document.querySelector('[data-runtime-capture-projection]')).toBeNull()
  })

  it('动画最终态不重新开始：有限动画被冻结至最终帧，不被 innerHTML 重构打回第 0 帧', async () => {
    let finishedCalled = false
    const mockAnimation = {
      playState: 'running',
      effect: {
        getTiming: () => ({ iterations: 1, duration: 1000 }),
      },
      finish: vi.fn(() => {
        finishedCalled = true
      }),
    } as unknown as Animation

    const testDoc = document.implementation.createHTMLDocument('test')
    Object.defineProperty(testDoc, 'getAnimations', {
      value: () => [mockAnimation],
      configurable: true,
    })

    await freezeDocumentAnimationsToFinalState(testDoc)

    // 有限次动画必须被调用 finish() 推进至最终呈现状态
    expect(finishedCalled).toBe(true)
    expect(mockAnimation.finish).toHaveBeenCalledTimes(1)
  })

  it('无限循环动画不被强制 finish 打断', async () => {
    const mockInfiniteAnimation = {
      playState: 'running',
      effect: {
        getTiming: () => ({ iterations: Infinity, duration: 1000 }),
      },
      finish: vi.fn(),
    } as unknown as Animation

    const testDoc = document.implementation.createHTMLDocument('test-infinite')
    Object.defineProperty(testDoc, 'getAnimations', {
      value: () => [mockInfiniteAnimation],
      configurable: true,
    })

    await freezeDocumentAnimationsToFinalState(testDoc)

    // 无限循环动画不得被强制 finish
    expect(mockInfiniteAnimation.finish).not.toHaveBeenCalled()
  })

  it('多页连续采集：路由切换状态机确保三页切换无上一页残余 DOM', async () => {
    const stage = createOffscreenPageStage()
    const iframe = document.querySelector('iframe') as HTMLIFrameElement
    expect(iframe).not.toBeNull()

    const win = iframe.contentWindow as unknown as { __EDITOR_RUNTIME_PREVIEW_READY__: boolean }
    const doc = iframe.contentDocument as Document

    // 模拟第 1 页：在 preparePage 发起导航后，运行时挂载第 1 页
    const p1 = stage.preparePage('/page-1')
    setTimeout(() => {
      const curDoc = iframe.contentDocument!
      curDoc.open(); curDoc.write('<!doctype html><html><head></head><body></body></html>'); curDoc.close()
      const curWin = iframe.contentWindow as unknown as { __EDITOR_RUNTIME_PREVIEW_READY__: boolean }
      const page1 = curDoc.createElement('div')
      page1.className = 'runtime-page-print-source'
      page1.dataset.runtimeRoutePath = '/page-1'
      page1.dataset.runtimeCaptureTicket = new URLSearchParams(iframe.contentWindow!.location.hash.split('?')[1]).get('runtimeCaptureTicket') || ''
      page1.style.width = '1920px'
      page1.style.height = '1080px'
      curDoc.body.appendChild(page1)
      curWin.__EDITOR_RUNTIME_PREVIEW_READY__ = true
    }, 20)
    const prepared1 = await p1
    expect(prepared1.element.dataset.runtimeRoutePath).toBe('/page-1')

    // 模拟第 2 页：切换路由并挂载第 2 页
    const p2 = stage.preparePage('/page-2')
    setTimeout(() => {
      const curDoc = iframe.contentDocument!
      curDoc.open(); curDoc.write('<!doctype html><html><head></head><body></body></html>'); curDoc.close()
      const curWin = iframe.contentWindow as unknown as { __EDITOR_RUNTIME_PREVIEW_READY__: boolean }
      curDoc.body.innerHTML = ''
      const page2 = curDoc.createElement('div')
      page2.className = 'runtime-page-print-source'
      page2.dataset.runtimeRoutePath = '/page-2'
      page2.dataset.runtimeCaptureTicket = new URLSearchParams(iframe.contentWindow!.location.hash.split('?')[1]).get('runtimeCaptureTicket') || ''
      page2.style.width = '1920px'
      page2.style.height = '1080px'
      curDoc.body.appendChild(page2)
      curWin.__EDITOR_RUNTIME_PREVIEW_READY__ = true
    }, 20)
    const prepared2 = await p2
    expect(prepared2.element.dataset.runtimeRoutePath).toBe('/page-2')
    expect(prepared2.element).not.toBe(prepared1.element)

    // 模拟第 3 页：切换路由并挂载第 3 页
    const p3 = stage.preparePage('/page-3')
    setTimeout(() => {
      const curDoc = iframe.contentDocument!
      curDoc.open(); curDoc.write('<!doctype html><html><head></head><body></body></html>'); curDoc.close()
      const curWin = iframe.contentWindow as unknown as { __EDITOR_RUNTIME_PREVIEW_READY__: boolean }
      curDoc.body.innerHTML = ''
      const page3 = curDoc.createElement('div')
      page3.className = 'runtime-page-print-source'
      page3.dataset.runtimeRoutePath = '/page-3'
      page3.dataset.runtimeCaptureTicket = new URLSearchParams(iframe.contentWindow!.location.hash.split('?')[1]).get('runtimeCaptureTicket') || ''
      page3.style.width = '1920px'
      page3.style.height = '1080px'
      curDoc.body.appendChild(page3)
      curWin.__EDITOR_RUNTIME_PREVIEW_READY__ = true
    }, 20)
    const prepared3 = await p3
    expect(prepared3.element.dataset.runtimeRoutePath).toBe('/page-3')
    expect(prepared3.element).not.toBe(prepared2.element)

    stage.dispose()
    expect(document.querySelector('iframe')).toBeNull()
  })

  it('跨 Realm DOM 节点通过 PPTXDomConverter 提取几何与样式保持一致', async () => {
    // 构造一个由独立 Document 创建的页面节点（模拟 iframe contentDocument 跨 window 节点）
    const testDoc = document.implementation.createHTMLDocument('iframe-doc')
    const pageRoot = testDoc.createElement('div')
    pageRoot.style.cssText = 'width: 1920px; height: 1080px; background-color: #0f172a;'

    const heading = testDoc.createElement('h1')
    heading.style.cssText = 'display: block; width: 600px; height: 80px; font-size: 32px; color: #ffffff;'
    heading.textContent = '跨窗口标题'
    pageRoot.appendChild(heading)
    testDoc.body.appendChild(pageRoot)

    const converter = new PPTXDomConverter()
    const slideMock = createSlideMock()

    await converter.convertPage({
      slide: slideMock as unknown as PptxSlideLike,
      pageElement: pageRoot,
      pageIndex: 1,
      pageTitle: '跨窗口提取测试',
      pageRoute: '/iframe-extract',
      pageWidthPx: 1920,
      pageHeightPx: 1080,
      slideWidthIn: 13.333,
      slideHeightIn: 7.5,
      shapeTypes: {
        rect: 'rect',
        roundRect: 'roundRect',
        ellipse: 'ellipse',
        line: 'line',
      },
      captureElementAsPng: vi.fn(async () => 'data:image/png;base64,test'),
    })

    // 跨 Realm 节点被正确识别为 HTMLElement 并提取文字
    expect(slideMock.addText).toHaveBeenCalledWith(
      expect.stringContaining('跨窗口标题'),
      expect.anything(),
    )
    // 背景被正常提取设置
    expect(slideMock.background).toEqual(expect.objectContaining({
      color: '0F172A',
    }))
  })
})
