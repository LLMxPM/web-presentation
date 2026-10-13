// @vitest-environment jsdom

/**
 * 文件用途：验证 6 个内部 viewer 根节点都声明了 PPTX 显式导出契约，且契约与类名兜底都能被转换器识别。
 *
 * 说明：本文件是生产者与消费者之间的防漂移门禁。viewer 侧的属性名、取值与
 * PPTXRuntimeKitExportDom 中的常量在此直接对拍，任一侧单独改动都会失败。
 */

import { createApp, nextTick, type App, type Component } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DrawioViewer from './DrawioViewer.vue'
import EchartsViewer from './EchartsViewer.vue'
import ImageViewer from './ImageViewer.vue'
import LatexViewer from './LatexViewer.vue'
import MermaidViewer from './MermaidViewer.vue'
import VideoViewer from './VideoViewer.vue'
import {
  isLegacyMediaViewerElement,
  isMediaViewerElement,
  resolveRuntimeKitMediaSourceType,
  RUNTIME_KIT_EXPORT_DOM_VERSION,
  RUNTIME_KIT_MEDIA_ATTR,
  RUNTIME_KIT_MEDIA_KIND_ATTR,
} from '@/core/services/pptx/PPTXRuntimeKitExportDom'
import type { RuntimeKitMediaKind } from '@/core/services/pptx/PPTXRuntimeKitExportDom'

vi.mock('mermaid', () => ({
  default: {
    initialize: () => undefined,
    render: async () => ({ svg: '<svg viewBox="0 0 200 100"></svg>' }),
  },
}))

vi.mock('echarts', () => ({
  init: () => ({
    setOption: () => undefined,
    resize: () => undefined,
    dispose: () => undefined,
  }),
}))

interface ViewerContractCase {
  /** 用例名，取自组件文件名 */
  label: string
  /** viewer 组件 */
  component: Component
  /** viewer 根节点历史样式类名 */
  rootSelector: string
  /** 期望声明的媒体类型 */
  kind: RuntimeKitMediaKind
}

const VIEWER_CONTRACT_CASES: ViewerContractCase[] = [
  { label: 'MermaidViewer', component: MermaidViewer, rootSelector: '.mermaid-viewer', kind: 'mermaid' },
  { label: 'DrawioViewer', component: DrawioViewer, rootSelector: '.drawio-viewer', kind: 'drawio' },
  { label: 'LatexViewer', component: LatexViewer, rootSelector: '.latex-viewer', kind: 'formula' },
  { label: 'EchartsViewer', component: EchartsViewer, rootSelector: '.echarts-viewer', kind: 'chart' },
  { label: 'VideoViewer', component: VideoViewer, rootSelector: '.video-viewer', kind: 'video' },
  { label: 'ImageViewer', component: ImageViewer, rootSelector: '.image-viewer', kind: 'image' },
]

const mountedApps: App<Element>[] = []

/**
 * 挂载 viewer 并返回其根节点。
 * @param testCase viewer 契约用例
 * @returns viewer 根元素
 */
async function mountViewerRoot(testCase: ViewerContractCase): Promise<HTMLElement> {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp(testCase.component)
  mountedApps.push(app)
  app.mount(host)
  await nextTick()

  const root = host.querySelector<HTMLElement>(testCase.rootSelector)
  if (!root) {
    throw new Error(`${testCase.label} 未渲染出根节点 ${testCase.rootSelector}`)
  }
  return root
}

afterEach(() => {
  for (const app of mountedApps.splice(0)) {
    app.unmount()
  }
  document.body.innerHTML = ''
})

describe('viewer 显式导出契约', () => {
  it.each(VIEWER_CONTRACT_CASES)('$label 根节点应声明带版本的媒体导出契约', async (testCase) => {
    const root = await mountViewerRoot(testCase)

    expect(root.getAttribute(RUNTIME_KIT_MEDIA_ATTR)).toBe(RUNTIME_KIT_EXPORT_DOM_VERSION)
    expect(root.getAttribute(RUNTIME_KIT_MEDIA_KIND_ATTR)).toBe(testCase.kind)
  })

  it.each(VIEWER_CONTRACT_CASES)('$label 应被转换器按显式契约识别为媒体并解析出源类型', async (testCase) => {
    const root = await mountViewerRoot(testCase)

    expect(isMediaViewerElement(root)).toBe(true)
    expect(resolveRuntimeKitMediaSourceType(root)).toBe(testCase.kind)
  })

  it.each(VIEWER_CONTRACT_CASES)('$label 移除契约属性后仍应可由历史类名兜底识别', async (testCase) => {
    const root = await mountViewerRoot(testCase)

    root.removeAttribute(RUNTIME_KIT_MEDIA_ATTR)
    root.removeAttribute(RUNTIME_KIT_MEDIA_KIND_ATTR)

    expect(isLegacyMediaViewerElement(root)).toBe(true)
    expect(isMediaViewerElement(root)).toBe(true)
    expect(resolveRuntimeKitMediaSourceType(root)).toBe(testCase.kind)
  })
})
