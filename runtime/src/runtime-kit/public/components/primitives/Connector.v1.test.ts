// @vitest-environment jsdom

/**
 * 文件用途：验证 Connector 根 SVG 声明了 PPTX 显式导出契约，且契约与历史类名兜底都能被连接线守卫识别。
 */

import { createApp, nextTick, type App } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import Connector from './Connector.v1.vue'
import {
  isConnectorSvg,
  isRuntimeKitConnectorSvg,
  LEGACY_CONNECTOR_CLASS,
  RUNTIME_KIT_CONNECTOR_ATTR,
  RUNTIME_KIT_EXPORT_DOM_VERSION,
  RUNTIME_KIT_MEDIA_ATTR,
} from '@/core/services/pptx/PPTXRuntimeKitExportDom'

const mountedApps: App<Element>[] = []

/**
 * 在带两个锚点节点的舞台上挂载 Connector，并返回其根 SVG。
 * @returns 连接线根 SVG 元素
 */
async function mountConnectorSvg(): Promise<SVGSVGElement> {
  document.body.innerHTML = `
    <div id="stage" style="position: relative; width: 600px; height: 300px;">
      <div id="node-a" style="position: absolute; left: 0; top: 0; width: 80px; height: 40px;"></div>
      <div id="node-b" style="position: absolute; left: 400px; top: 200px; width: 80px; height: 40px;"></div>
    </div>
  `
  const host = document.createElement('div')
  document.getElementById('stage')?.appendChild(host)

  const app = createApp(Connector, { from: '#node-a', to: '#node-b', arrow: 'end' })
  mountedApps.push(app)
  app.mount(host)
  await nextTick()

  const svg = host.querySelector('svg')
  if (!svg) {
    throw new Error('Connector 未渲染出根 SVG')
  }
  return svg
}

afterEach(() => {
  for (const app of mountedApps.splice(0)) {
    app.unmount()
  }
  document.body.innerHTML = ''
})

describe('Connector 显式导出契约', () => {
  it('根 SVG 应声明带版本的连接线导出契约', async () => {
    const svg = await mountConnectorSvg()

    expect(svg.getAttribute(RUNTIME_KIT_CONNECTOR_ATTR)).toBe(RUNTIME_KIT_EXPORT_DOM_VERSION)
    expect(isRuntimeKitConnectorSvg(svg)).toBe(true)
    expect(isConnectorSvg(svg)).toBe(true)
  })

  it('移除契约属性后仍应可由历史类名兜底识别', async () => {
    const svg = await mountConnectorSvg()

    svg.removeAttribute(RUNTIME_KIT_CONNECTOR_ATTR)

    expect(svg.classList.contains(LEGACY_CONNECTOR_CLASS)).toBe(true)
    expect(isRuntimeKitConnectorSvg(svg)).toBe(false)
    expect(isConnectorSvg(svg)).toBe(true)
  })

  it('连接线契约不应与媒体契约混用同一属性', async () => {
    const svg = await mountConnectorSvg()

    expect(svg.hasAttribute(RUNTIME_KIT_MEDIA_ATTR)).toBe(false)
  })
})
