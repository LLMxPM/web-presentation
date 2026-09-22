/**
 * 文件用途：提供 Runtime 内部资源比例测量接口，为 Backend 回填 Formula/Mermaid 近似比例。
 */

import type { IncomingMessage, ServerResponse } from 'http'
import { createRemoteJWKSet, jwtVerify, type JWTPayload } from 'jose'
import type { Plugin } from 'vite'

import { renderLatexToString } from '../../runtime-kit/internal/renderers/latex'
import {
  formatAspectRatio,
  resolveMathJaxStackedSvgAspectRatio,
  resolveSingleSvgAspectRatio,
} from '../utils/svg-aspect-ratio'
import { logRuntimeServer } from '../utils/runtime-logger'

interface RuntimeAssetRenderHintMeasurerOptions {
  endpointPath?: string
  serviceTokenHeaderName?: string
  jwksUrl?: string
  serviceAudience?: string
}

interface RuntimeServiceClaims extends JWTPayload {
  sub?: string
  scope?: string
}

interface MeasureRequestBody {
  asset_type?: string
  content?: string
  options?: {
    theme?: string
  }
}

type RuntimeNodeResponse = Pick<ServerResponse, 'statusCode' | 'setHeader' | 'end'>

const DEFAULT_ENDPOINT = '/__runtime_internal/v1/assets/render-hints/measure'
const DEFAULT_RUNTIME_SERVICE_TOKEN_HEADER = 'x-runtime-service-token'
const DEFAULT_SERVICE_AUDIENCE = 'runtime-backend'
const SVG_NUMBER_RE = /[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?/gi

/**
 * 注册资源比例测量内部接口。
 * @param options 插件配置
 * @returns Vite 插件
 */
export default function runtimeAssetRenderHintMeasurer(options: RuntimeAssetRenderHintMeasurerOptions = {}): Plugin {
  const endpointPath = options.endpointPath || DEFAULT_ENDPOINT
  const serviceTokenHeaderName = (options.serviceTokenHeaderName || DEFAULT_RUNTIME_SERVICE_TOKEN_HEADER).toLowerCase()

  return {
    name: 'runtime-asset-render-hint-measurer',
    apply: 'serve',

    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const requestPath = (req.url || '').split('?')[0]
        if (requestPath !== endpointPath) {
          return next()
        }
        if (req.method !== 'POST') {
          return sendJson(res, 405, {
            ok: false,
            code: 'METHOD_NOT_ALLOWED',
            message: '资源比例测量入口仅支持 POST。',
          })
        }
        try {
          await verifyRuntimeServiceToken(String(req.headers[serviceTokenHeaderName] || ''), {
            jwksUrl: options.jwksUrl || process.env.RUNTIME_PREVIEW_JWKS_URL || '',
            audience: options.serviceAudience || process.env.RUNTIME_SERVICE_TOKEN_AUDIENCE || DEFAULT_SERVICE_AUDIENCE,
          })
          const payload = await readJsonBody<MeasureRequestBody>(req)
          const result = await measureAssetRenderHint(payload)
          sendJson(res, 200, result)
        } catch (error) {
          logRuntimeServer('error', 'runtime.asset_render_hint.measure.failed', 'Runtime 资源比例测量失败。', {
            module: 'runtime.asset_render_hint',
            error,
            requestUrl: req.url,
          })
          sendMeasureError(res, error)
        }
      })
    },
  }
}

export async function measureAssetRenderHint(payload: MeasureRequestBody): Promise<Record<string, unknown>> {
  const assetType = String(payload.asset_type || '').trim().toLowerCase()
  const content = String(payload.content || '').trim()
  if (!content) {
    throw new RuntimeMeasureError(400, 'ASSET_RENDER_HINT_CONTENT_EMPTY', '资源内容不能为空。')
  }
  const ratio = assetType === 'formula'
    ? await measureFormulaAspectRatio(content)
    : assetType === 'mermaid'
      ? await measureMermaidAspectRatio(content, payload.options?.theme)
      : null
  if (!ratio) {
    throw new RuntimeMeasureError(422, 'ASSET_RENDER_HINT_RATIO_UNRESOLVED', '未能从渲染结果中解析资源比例。')
  }
  const formatted = formatAspectRatio(ratio)
  if (!formatted) {
    throw new RuntimeMeasureError(422, 'ASSET_RENDER_HINT_RATIO_INVALID', '资源比例测量结果不合法。')
  }
  return {
    ok: true,
    aspect_ratio: formatted.aspectRatio,
    aspect_ratio_value: formatted.aspectRatioValue,
    source: 'runtime-svg',
  }
}

export async function measureFormulaAspectRatio(content: string): Promise<number | null> {
  const renderedHtml = await renderLatexToString(content)
  return resolveMathJaxStackedSvgAspectRatio(renderedHtml)
}

export async function measureMermaidAspectRatio(content: string, theme?: string): Promise<number | null> {
  await ensureMermaidDomEnvironment()
  const mermaidModule = await import('mermaid')
  const mermaid = mermaidModule.default
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme: normalizeMermaidTheme(theme),
    flowchart: {
      htmlLabels: false,
    },
  })
  const id = `measure-${Date.now()}-${Math.random().toString(36).slice(2)}`
  const { svg } = await mermaid.render(id, content)
  return resolveSingleSvgAspectRatio(svg)
}

let mermaidDomReady = false

async function ensureMermaidDomEnvironment(): Promise<void> {
  if (mermaidDomReady && typeof document !== 'undefined') return
  const { JSDOM } = await import('jsdom')
  const dom = new JSDOM('<!doctype html><html><body></body></html>')
  const globalRecord = globalThis as unknown as Record<string, unknown>
  globalRecord.window = dom.window
  globalRecord.document = dom.window.document
  Object.defineProperty(globalThis, 'navigator', {
    value: dom.window.navigator,
    configurable: true,
  })
  globalRecord.Element = dom.window.Element
  globalRecord.SVGElement = dom.window.SVGElement
  globalRecord.CSSStyleSheet = class RuntimeMeasureCSSStyleSheet {
    cssRules: Array<{ cssText: string }> = []

    replaceSync(): void {
      this.cssRules = []
    }

    insertRule(rule: string, index = this.cssRules.length): number {
      this.cssRules.splice(index, 0, { cssText: rule })
      return index
    }
  }
  installSvgMeasurementPolyfills(dom.window)
  mermaidDomReady = true
}

function installSvgMeasurementPolyfills(windowObject: { SVGElement: typeof SVGElement }): void {
  const svgPrototype = windowObject.SVGElement.prototype as SVGElement & {
    getBBox?: () => SvgMeasureRect
    getComputedTextLength?: () => number
  }
  svgPrototype.getComputedTextLength = function getComputedTextLength() {
    return estimateTextWidth(this.textContent || '')
  }
  svgPrototype.getBBox = function getBBox() {
    return measureSvgElementBox(this) || { x: 0, y: 0, width: 1, height: 1 }
  }
}

interface SvgMeasureRect {
  x: number
  y: number
  width: number
  height: number
}

function measureSvgElementBox(element: SVGElement): SvgMeasureRect | null {
  const tagName = element.tagName.toLowerCase()
  if (['defs', 'style', 'marker', 'title', 'desc'].includes(tagName)) {
    return null
  }

  let box: SvgMeasureRect | null
  if (tagName === 'svg' || tagName === 'g') {
    box = unionMeasureRects(Array.from(element.children).map(child => measureSvgElementBox(child as SVGElement)))
  } else if (tagName === 'rect' || tagName === 'image' || tagName === 'foreignobject') {
    box = measureSizedSvgElement(element) || measureTextSvgElement(element)
  } else if (tagName === 'text' || tagName === 'tspan') {
    box = measureTextSvgElement(element)
  } else if (tagName === 'polygon' || tagName === 'polyline') {
    box = measurePointListSvgElement(element)
  } else if (tagName === 'circle' || tagName === 'ellipse') {
    box = measureEllipseSvgElement(element)
  } else if (tagName === 'path') {
    box = measurePathSvgElement(element)
  } else {
    box = measureTextSvgElement(element)
  }

  if (!box) return null
  const [translateX, translateY] = parseTranslate(element.getAttribute('transform'))
  return {
    x: box.x + translateX,
    y: box.y + translateY,
    width: box.width,
    height: box.height,
  }
}

function measureSizedSvgElement(element: SVGElement): SvgMeasureRect | null {
  const width = parseSvgNumber(element.getAttribute('width'))
  const height = parseSvgNumber(element.getAttribute('height'))
  if (!isPositiveMeasurement(width) || !isPositiveMeasurement(height) || width >= 1000 || height >= 1000) {
    return null
  }
  return {
    x: parseSvgNumber(element.getAttribute('x')) || 0,
    y: parseSvgNumber(element.getAttribute('y')) || 0,
    width,
    height,
  }
}

function measureTextSvgElement(element: SVGElement): SvgMeasureRect {
  const lines = splitMeasureText(element.textContent || '')
  const width = Math.max(...lines.map(estimateTextWidth)) + 4
  return {
    x: parseSvgNumber(element.getAttribute('x')) || 0,
    y: (parseSvgNumber(element.getAttribute('y')) || 0) - 14,
    width: Math.max(24, width),
    height: Math.max(18, lines.length * 18),
  }
}

function measurePointListSvgElement(element: SVGElement): SvgMeasureRect | null {
  const numbers = parseSvgNumbers(element.getAttribute('points'))
  return buildBoxFromCoordinateNumbers(numbers)
}

function measureEllipseSvgElement(element: SVGElement): SvgMeasureRect | null {
  const radiusX = parseSvgNumber(element.getAttribute('rx')) || parseSvgNumber(element.getAttribute('r'))
  const radiusY = parseSvgNumber(element.getAttribute('ry')) || parseSvgNumber(element.getAttribute('r'))
  if (!isPositiveMeasurement(radiusX) || !isPositiveMeasurement(radiusY)) return null
  const centerX = parseSvgNumber(element.getAttribute('cx')) || 0
  const centerY = parseSvgNumber(element.getAttribute('cy')) || 0
  return {
    x: centerX - radiusX,
    y: centerY - radiusY,
    width: radiusX * 2,
    height: radiusY * 2,
  }
}

function measurePathSvgElement(element: SVGElement): SvgMeasureRect | null {
  const numbers = parseSvgNumbers(element.getAttribute('d'))
  return buildBoxFromCoordinateNumbers(numbers)
}

function buildBoxFromCoordinateNumbers(numbers: number[]): SvgMeasureRect | null {
  const xs: number[] = []
  const ys: number[] = []
  for (let index = 0; index < numbers.length - 1; index += 2) {
    xs.push(numbers[index])
    ys.push(numbers[index + 1])
  }
  if (xs.length === 0 || ys.length === 0) return null
  const minX = Math.min(...xs)
  const minY = Math.min(...ys)
  const maxX = Math.max(...xs)
  const maxY = Math.max(...ys)
  return {
    x: minX,
    y: minY,
    width: Math.max(1, maxX - minX),
    height: Math.max(1, maxY - minY),
  }
}

function unionMeasureRects(boxes: Array<SvgMeasureRect | null>): SvgMeasureRect | null {
  const validBoxes = boxes.filter((box): box is SvgMeasureRect => Boolean(box))
  if (validBoxes.length === 0) return null
  const minX = Math.min(...validBoxes.map(box => box.x))
  const minY = Math.min(...validBoxes.map(box => box.y))
  const maxX = Math.max(...validBoxes.map(box => box.x + box.width))
  const maxY = Math.max(...validBoxes.map(box => box.y + box.height))
  return {
    x: minX,
    y: minY,
    width: Math.max(1, maxX - minX),
    height: Math.max(1, maxY - minY),
  }
}

function splitMeasureText(text: string): string[] {
  const lines = String(text || '')
    .split(/\\n|\n/)
    .map(line => line.trim())
    .filter(Boolean)
  return lines.length > 0 ? lines : ['']
}

function estimateTextWidth(text: string): number {
  const width = Array.from(String(text || '').trim()).reduce((total, char) => {
    return total + (/[\u0100-\uFFFF]/.test(char) ? 14 : 8)
  }, 0)
  return Math.max(20, width)
}

function parseSvgNumber(value: string | null): number | null {
  const numbers = parseSvgNumbers(value)
  return numbers[0] ?? null
}

function parseSvgNumbers(value: string | null): number[] {
  SVG_NUMBER_RE.lastIndex = 0
  return Array.from(String(value || '').matchAll(SVG_NUMBER_RE)).map(item => Number(item[0]))
}

function parseTranslate(value: string | null): [number, number] {
  const match = String(value || '').match(/translate\(([-+\d.eE]+)(?:[ ,]+([-+\d.eE]+))?\)/)
  if (!match) return [0, 0]
  return [Number(match[1]) || 0, Number(match[2]) || 0]
}

function isPositiveMeasurement(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
}

async function verifyRuntimeServiceToken(token: string, options: { jwksUrl: string; audience: string }): Promise<RuntimeServiceClaims> {
  if (!token) {
    throw new RuntimeMeasureError(401, 'RUNTIME_SERVICE_TOKEN_REQUIRED', '缺少 Runtime 服务令牌。')
  }
  if (!options.jwksUrl) {
    throw new RuntimeMeasureError(503, 'JWKS_URL_MISSING', 'Runtime 未配置 JWKS 地址。')
  }
  const jwks = createRemoteJWKSet(new URL(options.jwksUrl))
  const { payload } = await jwtVerify(token, jwks, {
    audience: options.audience,
  })
  const claims = payload as RuntimeServiceClaims
  if (claims.sub !== 'runtime-service' || claims.scope !== 'runtime-artifact-read') {
    throw new RuntimeMeasureError(401, 'RUNTIME_SERVICE_TOKEN_INVALID', 'Runtime 服务令牌缺少必需声明。')
  }
  return claims
}

function normalizeMermaidTheme(theme?: string): 'default' | 'dark' | 'forest' | 'neutral' | 'base' {
  const normalized = String(theme || '').trim().toLowerCase()
  if (['default', 'dark', 'forest', 'neutral', 'base'].includes(normalized)) {
    return normalized as 'default' | 'dark' | 'forest' | 'neutral' | 'base'
  }
  return 'default'
}

function readJsonBody<T>(req: IncomingMessage): Promise<T> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = []
    req.on('data', chunk => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)))
    req.on('end', () => {
      try {
        const rawBody = Buffer.concat(chunks).toString('utf-8').trim()
        resolve(rawBody ? JSON.parse(rawBody) as T : {} as T)
      } catch (error) {
        reject(new RuntimeMeasureError(400, 'REQUEST_BODY_INVALID', '请求体不是合法 JSON。', error))
      }
    })
    req.on('error', reject)
  })
}

function sendJson(res: RuntimeNodeResponse, statusCode: number, payload: unknown): void {
  res.statusCode = statusCode
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.end(JSON.stringify(payload))
}

function sendMeasureError(res: RuntimeNodeResponse, error: unknown): void {
  if (error instanceof RuntimeMeasureError) {
    sendJson(res, error.statusCode, {
      ok: false,
      code: error.code,
      message: error.message,
    })
    return
  }
  sendJson(res, 500, {
    ok: false,
    code: 'RUNTIME_ASSET_RENDER_HINT_MEASURE_FAILED',
    message: error instanceof Error ? error.message : 'Runtime 资源比例测量失败。',
  })
}

class RuntimeMeasureError extends Error {
  statusCode: number
  code: string

  constructor(statusCode: number, code: string, message: string, cause?: unknown) {
    super(message, { cause })
    this.name = 'RuntimeMeasureError'
    this.statusCode = statusCode
    this.code = code
  }
}
