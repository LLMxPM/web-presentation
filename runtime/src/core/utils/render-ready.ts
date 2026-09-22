/**
 * 文件用途：Runtime 强制渲染就绪协议 render-ready.v1 的唯一宿主实现。
 */

export const RENDER_READY_PROTOCOL = 'render-ready.v1'

export interface RenderReadyBridge {
  protocol: string
  artifactId: string | null
  inputDigest: string | null
  runtimeBuildId: string | null
  mounted: boolean
  initFailed: boolean
  message: string | null
  fonts: {
    ready: boolean
    loaded: number
    failed: number
  }
  visualAssets: {
    ready: boolean
    loaded: number
    failed: number
    timedOut: boolean
  }
  scenarios: Array<{ key: string }>
  lastScenarioRequestId: string | null
  lastScenarioAck: { requestId: string; ok: boolean; scenarioKey: string } | null
  contentExceptions: Array<{ code: string; message: string }>
}

declare global {
  interface Window {
    __RENDER_READY__?: RenderReadyBridge
    __RENDER_APPLY_SCENARIO__?: (input: {
      scenarioKey: string
      profileKey: string
      requestId: string
      state?: unknown
      props?: Record<string, unknown> | null
      slots?: Record<string, unknown> | null
      mocks?: Record<string, unknown> | null
    }) => Promise<{ requestId: string; ok: boolean; scenarioKey: string }>
  }
}

/**
 * 初始化 render-ready.v1 宿主桥；禁止用 #app 子节点或固定 sleep 替代协议。
 */
export function initializeRenderReadyHost(meta?: {
  artifactId?: string | null
  inputDigest?: string | null
  runtimeBuildId?: string | null
}): void {
  if (typeof window === 'undefined') {
    return
  }
  window.__RENDER_READY__ = {
    protocol: RENDER_READY_PROTOCOL,
    artifactId: meta?.artifactId ?? null,
    inputDigest: meta?.inputDigest ?? null,
    runtimeBuildId: meta?.runtimeBuildId ?? null,
    mounted: false,
    initFailed: false,
    message: null,
    fonts: { ready: false, loaded: 0, failed: 0 },
    visualAssets: { ready: false, loaded: 0, failed: 0, timedOut: false },
    scenarios: [{ key: 'default' }],
    lastScenarioRequestId: null,
    lastScenarioAck: null,
    contentExceptions: [],
  }
}

/**
 * 更新宿主协议状态。
 */
export function updateRenderReadyHost(patch: Partial<RenderReadyBridge>): void {
  if (typeof window === 'undefined' || !window.__RENDER_READY__) {
    return
  }
  const current = window.__RENDER_READY__
  window.__RENDER_READY__ = {
    ...current,
    ...patch,
    protocol: RENDER_READY_PROTOCOL,
    fonts: { ...current.fonts, ...(patch.fonts ?? {}) },
    visualAssets: { ...current.visualAssets, ...(patch.visualAssets ?? {}) },
  }
}

/**
 * 标记预览内容挂载完成与字体/视觉资源就绪。
 */
export async function markRenderPreviewMounted(options?: {
  artifactId?: string | null
  inputDigest?: string | null
  visualTimeoutMs?: number
}): Promise<void> {
  if (typeof window === 'undefined') {
    return
  }
  if (!window.__RENDER_READY__) {
    initializeRenderReadyHost({
      artifactId: options?.artifactId ?? null,
      inputDigest: options?.inputDigest ?? null,
    })
  }
  const fontsReady = typeof document !== 'undefined' && document.fonts?.ready
    ? await document.fonts.ready.then(() => true).catch(() => false)
    : true
  let visualAssets: RenderReadyBridge['visualAssets'] = {
    ready: true,
    loaded: 0,
    failed: 0,
    timedOut: false,
  }
  const waitForVisualAssets = window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__
  if (typeof waitForVisualAssets === 'function') {
    const result = await waitForVisualAssets({
      timeoutMs: options?.visualTimeoutMs ?? 25000,
    })
    const failed = Array.isArray(result?.failed) ? result.failed.length : 0
    const timedOut = Boolean(result?.timedOut)
    const ok = Boolean(result?.ok)
    visualAssets = {
      ready: ok && !timedOut,
      loaded: typeof result?.total === 'number' ? result.total : 0,
      failed,
      timedOut: timedOut || !ok,
    }
  }
  updateRenderReadyHost({
    mounted: true,
    initFailed: false,
    artifactId: options?.artifactId ?? window.__RENDER_READY__?.artifactId ?? null,
    inputDigest: options?.inputDigest ?? window.__RENDER_READY__?.inputDigest ?? null,
    fonts: { ready: Boolean(fontsReady), loaded: document.fonts?.size ?? 0, failed: 0 },
    visualAssets,
    message: visualAssets.ready ? null : '视觉资源未在限定时间内就绪',
  })
  // 兼容既有 Editor 截图探针。
  window.__EDITOR_RUNTIME_PREVIEW_READY__ = visualAssets.ready
}

/**
 * 记录组件场景切换请求回执。
 */
export function ackRenderScenario(input: {
  requestId: string
  scenarioKey: string
  ok: boolean
}): void {
  updateRenderReadyHost({
    lastScenarioRequestId: input.requestId,
    lastScenarioAck: {
      requestId: input.requestId,
      ok: input.ok,
      scenarioKey: input.scenarioKey,
    },
  })
}

/**
 * 标记宿主初始化失败或内容异常。
 */
export function markRenderReadyFailure(message: string, options?: { content?: boolean }): void {
  const bridge = typeof window !== 'undefined' ? window.__RENDER_READY__ : undefined
  if (options?.content && bridge) {
    updateRenderReadyHost({
      contentExceptions: [
        ...bridge.contentExceptions,
        { code: 'RENDER_CONTENT_ERROR', message },
      ].slice(-20),
    })
    return
  }
  updateRenderReadyHost({
    initFailed: true,
    message,
    mounted: false,
    fonts: { ready: false, loaded: 0, failed: 0 },
    visualAssets: { ready: false, loaded: 0, failed: 0, timedOut: false },
  })
}
