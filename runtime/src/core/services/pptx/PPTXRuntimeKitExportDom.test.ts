// @vitest-environment jsdom

/**
 * 文件用途：验证 Runtime Kit 显式导出 DOM 契约的识别、类型词汇、类名兜底顺序、连接线守卫与转换器分派。
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  hasRuntimeKitMediaMarker,
  isConnectorSvg,
  isLegacyMediaViewerElement,
  isMediaViewerElement,
  isRuntimeKitConnectorSvg,
  isRuntimeKitMediaKind,
  LEGACY_MEDIA_VIEWER_SELECTOR,
  resolveRuntimeKitMediaKind,
  resolveRuntimeKitMediaSourceType,
  RUNTIME_KIT_CONNECTOR_ATTR,
  RUNTIME_KIT_EXPORT_DOM_VERSION,
  RUNTIME_KIT_MEDIA_ATTR,
  RUNTIME_KIT_MEDIA_KINDS,
  RUNTIME_KIT_MEDIA_KIND_ATTR,
} from './PPTXRuntimeKitExportDom'
import { convert, createSlideMock } from './PPTXDomConverter.test-support'

/**
 * 按 HTML 片段构造单个脱离文档的元素，便于批量生成正反例。
 * @param html 单节点 HTML 片段
 * @returns 片段中的首个元素
 */
function createElement(html: string): Element {
  const host = document.createElement('div')
  host.innerHTML = html.trim()
  const element = host.firstElementChild
  if (!element) {
    throw new Error(`测试片段未产生元素：${html}`)
  }
  return element
}

/**
 * 构造声明了媒体导出契约的节点。
 * @param kind 媒体类型取值
 * @param extra 额外属性片段，用于构造版本冲突等反例
 */
function createMediaNode(kind: string, extra = ''): Element {
  return createElement(
    `<div ${RUNTIME_KIT_MEDIA_ATTR}="${RUNTIME_KIT_EXPORT_DOM_VERSION}" ${RUNTIME_KIT_MEDIA_KIND_ATTR}="${kind}"${extra}></div>`,
  )
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('媒体契约标记识别', () => {
  it('当前版本标记应被识别', () => {
    const element = createMediaNode('mermaid')

    expect(hasRuntimeKitMediaMarker(element)).toBe(true)
    expect(isMediaViewerElement(element)).toBe(true)
  })

  it('缺失标记、空值与未知版本都不应被识别', () => {
    expect(hasRuntimeKitMediaMarker(createElement('<div></div>'))).toBe(false)
    expect(hasRuntimeKitMediaMarker(createElement(`<div ${RUNTIME_KIT_MEDIA_ATTR}=""></div>`))).toBe(false)
    expect(hasRuntimeKitMediaMarker(createElement(`<div ${RUNTIME_KIT_MEDIA_ATTR}="v2"></div>`))).toBe(false)
    expect(hasRuntimeKitMediaMarker(createElement(`<div ${RUNTIME_KIT_MEDIA_ATTR}="1"></div>`))).toBe(false)
  })

  it('未知版本即使类型合法也不应被识别，交由类名兜底', () => {
    const element = createElement(
      `<div class="mermaid-viewer" ${RUNTIME_KIT_MEDIA_ATTR}="v2" ${RUNTIME_KIT_MEDIA_KIND_ATTR}="mermaid"></div>`,
    )

    expect(hasRuntimeKitMediaMarker(element)).toBe(false)
    expect(resolveRuntimeKitMediaKind(element)).toBeNull()
    expect(isMediaViewerElement(element)).toBe(true)
    expect(resolveRuntimeKitMediaSourceType(element)).toBe('mermaid')
  })

  it('仅声明类型而未声明标记的节点不应被识别', () => {
    const element = createElement(`<div ${RUNTIME_KIT_MEDIA_KIND_ATTR}="mermaid"></div>`)

    expect(hasRuntimeKitMediaMarker(element)).toBe(false)
    expect(resolveRuntimeKitMediaKind(element)).toBeNull()
    expect(isMediaViewerElement(element)).toBe(false)
    expect(resolveRuntimeKitMediaSourceType(element)).toBeNull()
  })
})

describe('媒体类型词汇与映射', () => {
  it.each([...RUNTIME_KIT_MEDIA_KINDS])('应把 %s 类型映射为同名报告源类型', (kind) => {
    const element = createMediaNode(kind)

    expect(isRuntimeKitMediaKind(kind)).toBe(true)
    expect(resolveRuntimeKitMediaKind(element)).toBe(kind)
    expect(resolveRuntimeKitMediaSourceType(element)).toBe(kind)
  })

  it('词汇表外的类型取值应回退到类名与标签名兜底', () => {
    expect(isRuntimeKitMediaKind('hologram')).toBe(false)
    expect(isRuntimeKitMediaKind(null)).toBe(false)

    const element = createMediaNode('hologram')
    expect(resolveRuntimeKitMediaKind(element)).toBeNull()
    expect(resolveRuntimeKitMediaSourceType(element)).toBeNull()
  })

  it('声明了标记但缺少类型属性时应回退到兜底路径', () => {
    const element = createElement(`<div class="drawio-viewer" ${RUNTIME_KIT_MEDIA_ATTR}="v1"></div>`)

    expect(hasRuntimeKitMediaMarker(element)).toBe(true)
    expect(resolveRuntimeKitMediaKind(element)).toBeNull()
    expect(resolveRuntimeKitMediaSourceType(element)).toBe('drawio')
  })

  it('显式契约应优先于相互冲突的历史类名', () => {
    const element = createMediaNode('image', ' class="mermaid-viewer"')

    expect(resolveRuntimeKitMediaSourceType(element)).toBe('image')
  })
})

describe('媒体识别的类名兜底', () => {
  it('兜底选择器应保持历史 MEDIA_SELECTORS 的完整类名集合', () => {
    expect(LEGACY_MEDIA_VIEWER_SELECTOR).toBe(
      '.mermaid-viewer,.drawio-viewer,.latex-viewer,.echarts-viewer,.video-viewer,.image-viewer',
    )
  })

  it.each([
    ['mermaid-viewer', 'mermaid'],
    ['drawio-viewer', 'drawio'],
    ['latex-viewer', 'formula'],
    ['echarts-viewer', 'chart'],
    ['video-viewer', 'video'],
    ['image-viewer', 'image'],
  ])('仅有 %s 类名时应识别为媒体并解析出 %s', (className, sourceType) => {
    const element = createElement(`<div class="${className}"></div>`)

    expect(isLegacyMediaViewerElement(element)).toBe(true)
    expect(isMediaViewerElement(element)).toBe(true)
    expect(resolveRuntimeKitMediaSourceType(element)).toBe(sourceType)
  })

  it.each([
    ['<canvas class="image-viewer"></canvas>', 'canvas'],
    ['<svg class="image-viewer"></svg>', 'svg'],
    ['<video class="image-viewer"></video>', 'video'],
    ['<canvas class="video-viewer"></canvas>', 'video'],
    ['<video></video>', 'video'],
    ['<canvas></canvas>', 'canvas'],
    ['<svg></svg>', 'svg'],
    ['<img src="data:image/png;base64,AAA=" />', 'image'],
  ])('无契约时 %s 应保持引入契约前的判定结果 %s', (html, sourceType) => {
    expect(resolveRuntimeKitMediaSourceType(createElement(html))).toBe(sourceType)
  })

  it('既无契约也无媒体类名或标签的普通节点不应被识别', () => {
    const element = createElement('<div class="runtime-card"><span>正文</span></div>')

    expect(isLegacyMediaViewerElement(element)).toBe(false)
    expect(isMediaViewerElement(element)).toBe(false)
    expect(resolveRuntimeKitMediaSourceType(element)).toBeNull()
  })

  it('仅带契约、不带任何 viewer 类名的节点也应被识别为媒体', () => {
    const element = createMediaNode('chart')

    expect(isLegacyMediaViewerElement(element)).toBe(false)
    expect(isMediaViewerElement(element)).toBe(true)
  })
})

describe('连接线契约守卫', () => {
  it('显式契约标记应通过守卫', () => {
    const svg = createElement(`<svg ${RUNTIME_KIT_CONNECTOR_ATTR}="v1"></svg>`)

    expect(isRuntimeKitConnectorSvg(svg)).toBe(true)
    expect(isConnectorSvg(svg)).toBe(true)
  })

  it('仅有历史 connector-svg 类名时应继续通过守卫', () => {
    const svg = createElement('<svg class="connector-svg"></svg>')

    expect(isRuntimeKitConnectorSvg(svg)).toBe(false)
    expect(isConnectorSvg(svg)).toBe(true)
  })

  it('未知版本标记不得通过契约守卫，但仍可由类名兜底', () => {
    const onlyAttribute = createElement(`<svg ${RUNTIME_KIT_CONNECTOR_ATTR}="v2"></svg>`)
    const withLegacyClass = createElement(`<svg class="connector-svg" ${RUNTIME_KIT_CONNECTOR_ATTR}="v2"></svg>`)

    expect(isRuntimeKitConnectorSvg(onlyAttribute)).toBe(false)
    expect(isConnectorSvg(onlyAttribute)).toBe(false)
    expect(isConnectorSvg(withLegacyClass)).toBe(true)
  })

  it('普通 SVG 不应被误判为连接线', () => {
    expect(isConnectorSvg(createElement('<svg viewBox="0 0 10 10"></svg>'))).toBe(false)
  })

  it('连接线不应进入媒体类型词汇，避免与报告源类型混淆', () => {
    expect(RUNTIME_KIT_MEDIA_KINDS).not.toContain('connector')
    expect(resolveRuntimeKitMediaSourceType(createElement(`<svg ${RUNTIME_KIT_CONNECTOR_ATTR}="v1"></svg>`))).toBe('svg')
  })
})

describe('PPTX 转换器分派', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  /**
   * 构造只含单个媒体节点的页面。
   * @param attributes 媒体根节点属性片段
   */
  function renderMediaPage(attributes: string): void {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background: #ffffff;">
        <div ${attributes} style="position: absolute; left: 100px; top: 80px; width: 320px; height: 200px;">
          <img src="data:image/png;base64,iVBORw0KGgo=" alt="媒体节点" style="width: 320px; height: 200px;" />
        </div>
      </div>
    `
  }

  it('仅带显式契约、不带 viewer 类名的节点应导出为图片块而非文本', async () => {
    renderMediaPage(`${RUNTIME_KIT_MEDIA_ATTR}="v1" ${RUNTIME_KIT_MEDIA_KIND_ATTR}="image"`)
    const slide = createSlideMock()

    const report = await convert(slide)

    expect(slide.addImage).toHaveBeenCalledTimes(1)
    expect(slide.addText).not.toHaveBeenCalled()
    expect(report.items.every(item => item.sourceType === 'image')).toBe(true)
  })

  it('缺失契约时应继续按历史类名导出为图片块', async () => {
    renderMediaPage('class="image-viewer"')
    const slide = createSlideMock()

    await convert(slide)

    expect(slide.addImage).toHaveBeenCalledTimes(1)
    expect(slide.addText).not.toHaveBeenCalled()
  })

  it('显式契约声明的类型应决定报告源类型', async () => {
    renderMediaPage(`${RUNTIME_KIT_MEDIA_ATTR}="v1" ${RUNTIME_KIT_MEDIA_KIND_ATTR}="chart"`)
    const slide = createSlideMock()

    const report = await convert(slide)

    expect(report.items.some(item => item.sourceType === 'chart')).toBe(true)
  })
})
