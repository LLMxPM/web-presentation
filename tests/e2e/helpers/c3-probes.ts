/**
 * 文件功能：为 C3 集中实机验收提供浏览器侧观测探针，包含输入 guard、RAF 间隔、事件监听器与堆采样、
 * WebGL 上下文登记、浏览器进程信息和 Renderer 服务槽位读取。
 *
 * 这些探针只观测、不驱动业务逻辑；加入页面前必须先调用 installC3Probes，重置计数使用 resetC3Probes。
 */
import { execFile } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

import type { CDPSession, Frame, Page, TestInfo } from '@playwright/test'

const execFileAsync = promisify(execFile)
const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const evidenceRoot = resolve(repoRoot, '.tmp/c3-evidence')

/** 浏览器侧探针的累积计数结构，字段全部可 JSON 序列化。 */
export interface C3PageFacts {
  /** 采样窗口内累计的真实输入事件数，作为 noExternalInput 的判据。 */
  input: { pointer: number; key: number; wheel: number; touch: number; total: number }
  /** RAF 间隔统计：样本数、中位数、P95、最大间隔与超过 50ms 的掉帧数。 */
  raf: { samples: number; p50: number; p95: number; max: number; dropped: number }
  /** 页面媒体元素与画布数量。 */
  media: { audios: number; videos: number; canvases: number }
  /** WebGL 上下文生命周期计数。 */
  gl: { created: number; lost: number; restored: number; alive: number }
  /** 采样时是否有可见的运行时错误覆盖层。 */
  errorOverlay: boolean
}

/** CDP 侧计数，覆盖 DOM 节点、文档、事件监听器和 JS 堆。 */
export interface C3CdpCounters {
  documents: number | null
  nodes: number | null
  jsEventListeners: number | null
  jsHeapUsedBytes: number | null
  rendererProcesses: number | null
}

/** Renderer 服务槽位状态；服务不可达时返回 null。 */
export interface C3RendererHealth {
  slot_state: string
  worker_id: string
  worker_epoch: string
  self_check_ok: boolean
}

/**
 * 安装浏览器侧探针：输入 guard、RAF 间隔采样与 WebGL 上下文登记。
 *
 * RAF 只保留最近 600 个间隔用于分位数，累计计数单独保存，避免长稳期间自身造成内存增长。
 */
export async function installC3Probes(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const state = {
      input: { pointer: 0, key: 0, wheel: 0, touch: 0 },
      raf: { samples: 0, max: 0, dropped: 0, last: 0, ring: [] as number[] },
      gl: { created: 0, lost: 0, restored: 0 },
    }
    ;(window as unknown as { __c3: typeof state }).__c3 = state

    const bumpInput = (key: keyof typeof state.input) => () => {
      state.input[key] += 1
    }
    window.addEventListener('pointerdown', bumpInput('pointer'), { capture: true, passive: true })
    window.addEventListener('keydown', bumpInput('key'), { capture: true, passive: true })
    window.addEventListener('wheel', bumpInput('wheel'), { capture: true, passive: true })
    window.addEventListener('touchstart', bumpInput('touch'), { capture: true, passive: true })

    const nativeRaf = window.requestAnimationFrame.bind(window)
    window.requestAnimationFrame = (callback: FrameRequestCallback): number =>
      nativeRaf((timestamp: number) => {
        if (state.raf.last > 0) {
          const delta = timestamp - state.raf.last
          state.raf.samples += 1
          if (delta > state.raf.max) state.raf.max = delta
          if (delta > 50) state.raf.dropped += 1
          state.raf.ring.push(delta)
          if (state.raf.ring.length > 600) state.raf.ring.shift()
        }
        state.raf.last = timestamp
        callback(timestamp)
      })

    const registry: WebGLRenderingContext[] = []
    ;(window as unknown as { __c3Gl: WebGLRenderingContext[] }).__c3Gl = registry
    const nativeGetContext = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function patchedGetContext(
      this: HTMLCanvasElement,
      contextId: string,
      ...rest: unknown[]
    ) {
      const context = (nativeGetContext as (...args: unknown[]) => unknown).call(this, contextId, ...rest)
      if (context && /webgl/i.test(contextId)) {
        const gl = context as WebGLRenderingContext
        state.gl.created += 1
        gl.canvas.addEventListener('webglcontextlost', () => {
          state.gl.lost += 1
        })
        gl.canvas.addEventListener('webglcontextrestored', () => {
          state.gl.restored += 1
        })
        registry.push(gl)
      }
      return context
    } as typeof HTMLCanvasElement.prototype.getContext
  })
}

/** 进入采样窗口前清零输入与 RAF 计数，避免把准备阶段的点击计入 noExternalInput 判据。 */
export async function resetC3Probes(target: Page | Frame): Promise<void> {
  await target.evaluate(() => {
    const state = (window as unknown as { __c3?: Record<string, unknown> }).__c3
    if (!state) return
    const input = state.input as Record<string, number>
    for (const key of Object.keys(input)) input[key] = 0
    const raf = state.raf as { samples: number; max: number; dropped: number; last: number; ring: number[] }
    raf.samples = 0
    raf.max = 0
    raf.dropped = 0
    raf.last = 0
    raf.ring.length = 0
  })
}

/** 读取浏览器侧累积指标；页面未安装探针时返回 null 字段而不是抛错。 */
export async function readC3Facts(target: Page | Frame): Promise<C3PageFacts> {
  return target.evaluate(() => {
    const state = (window as unknown as { __c3?: Record<string, unknown> }).__c3 ?? {}
    const input = (state.input ?? {}) as Record<string, number>
    const raf = (state.raf ?? {}) as { samples: number; max: number; dropped: number; ring: number[] }
    const gl = (state.gl ?? {}) as Record<string, number>
    const ring = [...(raf.ring ?? [])].sort((a, b) => a - b)
    const pick = (ratio: number) => (ring.length ? ring[Math.min(ring.length - 1, Math.floor(ring.length * ratio))] : 0)
    const registry = (window as unknown as { __c3Gl?: WebGLRenderingContext[] }).__c3Gl ?? []
    const alive = registry.filter(context => !context.isContextLost()).length
    return {
      input: {
        pointer: input.pointer ?? 0,
        key: input.key ?? 0,
        wheel: input.wheel ?? 0,
        touch: input.touch ?? 0,
        total: (input.pointer ?? 0) + (input.key ?? 0) + (input.wheel ?? 0) + (input.touch ?? 0),
      },
      raf: {
        samples: raf.samples ?? 0,
        p50: pick(0.5),
        p95: pick(0.95),
        max: raf.max ?? 0,
        dropped: raf.dropped ?? 0,
      },
      media: {
        audios: document.querySelectorAll('audio').length,
        videos: document.querySelectorAll('video').length,
        canvases: document.querySelectorAll('canvas').length,
      },
      gl: {
        created: gl.created ?? 0,
        lost: gl.lost ?? 0,
        restored: gl.restored ?? 0,
        alive,
      },
      errorOverlay: Boolean(document.querySelector('[data-runtime-error], .runtime-error-overlay')),
    }
  })
}

/** 打开 CDP 会话并启用采样所需域。 */
export async function openCdp(page: Page): Promise<CDPSession> {
  const session = await page.context().newCDPSession(page)
  await session.send('Performance.enable').catch(() => undefined)
  await session.send('Runtime.enable').catch(() => undefined)
  return session
}

/** 读取 DOM 计数、事件监听器与 JS 堆；单项失败降级为 null，不影响其余指标。 */
export async function readCdpCounters(session: CDPSession): Promise<C3CdpCounters> {
  const counters: C3CdpCounters = {
    documents: null,
    nodes: null,
    jsEventListeners: null,
    jsHeapUsedBytes: null,
    rendererProcesses: null,
  }
  try {
    const dom = (await session.send('Memory.getDOMCounters')) as {
      documents: number
      nodes: number
      jsEventListeners: number
    }
    counters.documents = dom.documents
    counters.nodes = dom.nodes
    counters.jsEventListeners = dom.jsEventListeners
  } catch {
    // 某些上下文在导航瞬间无法读取 DOM 计数，保留 null 由调用方标注缺口。
  }
  try {
    const heap = (await session.send('Runtime.getHeapUsage')) as { usedSize: number }
    counters.jsHeapUsedBytes = heap.usedSize
  } catch {
    // 未启用 Runtime 域时忽略。
  }
  try {
    const info = (await session.send('SystemInfo.getProcessInfo')) as { processInfo: { type: string }[] }
    counters.rendererProcesses = info.processInfo.filter(process => process.type === 'renderer').length
  } catch {
    // 浏览器进程信息只在部分平台可用。
  }
  return counters
}

/** 触发一次强制 GC，用于区分真实保留与待回收对象。 */
export async function forceGc(session: CDPSession): Promise<void> {
  await session.send('HeapProfiler.collectGarbage').catch(() => undefined)
}

/** 读取 Renderer 服务槽位状态；服务不可达返回 null。 */
export async function readRendererHealth(): Promise<C3RendererHealth | null> {
  const base = process.env.E2E_RENDER_URL || 'http://127.0.0.1:7400'
  try {
    const response = await fetch(`${base.replace(/\/$/, '')}/readyz`)
    if (!response.ok) return null
    const payload = (await response.json()) as {
      slot_state?: string
      worker_id?: string
      worker_epoch?: string
      self_check?: { ok?: boolean }
    }
    return {
      slot_state: payload.slot_state ?? 'unknown',
      worker_id: payload.worker_id ?? '',
      worker_epoch: payload.worker_epoch ?? '',
      self_check_ok: payload.self_check?.ok === true,
    }
  } catch {
    return null
  }
}

/** 统计本机 Renderer 服务进程数；失败返回 null，不把平台差异当成通过。 */
export async function countRendererProcesses(): Promise<number | null> {
  try {
    if (process.platform === 'win32') {
      const script = "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*wp_renderer*' } | Measure-Object | Select-Object -ExpandProperty Count"
      const { stdout } = await execFileAsync('powershell', ['-NoProfile', '-Command', script], { timeout: 15_000 })
      const value = Number.parseInt(stdout.trim(), 10)
      return Number.isFinite(value) ? value : null
    }
    const { stdout } = await execFileAsync('pgrep', ['-fc', 'wp_renderer'], { timeout: 15_000 })
    const value = Number.parseInt(stdout.trim(), 10)
    return Number.isFinite(value) ? value : null
  } catch {
    return null
  }
}

/**
 * 归档一份 C3 证据：写入测试附件，并在 `.tmp/c3-evidence/` 留一份可直接引用的 JSON。
 * 返回落盘路径，供完成记录引用。
 */
export async function writeEvidence(testInfo: TestInfo, name: string, payload: unknown): Promise<string> {
  const serialized = JSON.stringify(payload, null, 2)
  await mkdir(evidenceRoot, { recursive: true })
  const filePath = resolve(evidenceRoot, `${name}.json`)
  await writeFile(filePath, serialized, 'utf8')
  await testInfo.attach(name, { body: serialized, contentType: 'application/json' })
  return filePath
}

/** 把字节数转成 MiB，保留一位小数，便于直接写入报告。 */
export function toMib(bytes: number | null): number | null {
  return bytes === null ? null : Math.round((bytes / 1024 / 1024) * 10) / 10
}
