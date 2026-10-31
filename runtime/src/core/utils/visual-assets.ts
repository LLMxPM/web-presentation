/**
 * 文件用途：提供编辑器截图前的视觉资源就绪探针，等待页面组件、图片、背景图和字体完成渲染。
 */
import { getRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { isStaticExecution } from '@/core/static-presentation/types'
import { collectVisualAssetTasks, type VisualAssetTask } from './visual-asset-images'
import { collectStaticVideoTasks } from './visual-asset-media'
import { createVisualAssetWaitScope, type VisualAssetWaitScope } from './visual-asset-wait'
export { extractCssUrls } from './visual-asset-images'

export interface EditorVisualAssetWaitOptions {
  /** 最长等待时间，单位毫秒。 */
  timeoutMs?: number
  /** 限定检查根节点；默认整个 document，供整页截图使用。 */
  root?: ParentNode
  /** 是否等待有限动画结束；放映页就绪由过渡信号负责时可关闭。 */
  includeAnimations?: boolean
  /** 静态宿主显式启用视频海报/首帧准备；交互预览默认不改变媒体状态。 */
  staticMedia?: boolean
  /** 离页或退出时撤销探测；取消以 AbortError 拒绝，不记为资源失败。 */
  signal?: AbortSignal
}

export interface EditorVisualAssetIssue {
  /** 资源类型，用于 Backend 压缩错误详情。 */
  type: 'view-preview' | 'drawio' | 'mermaid' | 'model3d' | 'image' | 'background' | 'font' | 'video'
  /** 资源地址；非 URL 类问题可为空。 */
  url?: string
  /** 面向诊断的简短信息。 */
  message: string
}

export interface EditorVisualAssetWaitResult {
  /** 是否所有视觉资源均已就绪。 */
  ok: boolean
  /** 是否触发了等待超时。 */
  timedOut: boolean
  /** 本次检查到的视觉资源总数。 */
  total: number
  /** 成功加载的视觉资源数。 */
  loaded: number
  /** 明确失败的视觉资源。 */
  failed: EditorVisualAssetIssue[]
  /** 超时仍未完成的视觉资源。 */
  pending: EditorVisualAssetIssue[]
  /** 实际等待耗时。 */
  waitedMs: number
}

type TaskStatus = 'pending' | 'loaded' | 'failed'
type RuntimeDiagramType = Extract<EditorVisualAssetIssue['type'], 'drawio' | 'mermaid' | 'model3d'>

interface RuntimeDiagramProbe {
  type: RuntimeDiagramType
  stateSelector: string
  stateDatasetKey: keyof DOMStringMap
  messageDatasetKey: keyof DOMStringMap
  failedMessage: string
  timeoutMessage: string
}

const DEFAULT_VISUAL_READY_TIMEOUT_MS = 25000
const ANIMATION_SETTLE_TIMEOUT_MS = 5000
const VIEW_PREVIEW_STATE_SELECTOR = '[data-runtime-view-preview-state]'
const DRAWIO_STATE_SELECTOR = '[data-runtime-drawio-state]'
const MERMAID_STATE_SELECTOR = '[data-runtime-mermaid-state]'
const MODEL_STATE_SELECTOR = '[data-runtime-model-state]'
const RUNTIME_DIAGRAM_PROBES: RuntimeDiagramProbe[] = [
  {
    type: 'drawio',
    stateSelector: DRAWIO_STATE_SELECTOR,
    stateDatasetKey: 'runtimeDrawioState',
    messageDatasetKey: 'runtimeDrawioMessage',
    failedMessage: 'Draw.io 图表渲染失败。',
    timeoutMessage: 'Draw.io 图表渲染超时。',
  },
  {
    type: 'mermaid',
    stateSelector: MERMAID_STATE_SELECTOR,
    stateDatasetKey: 'runtimeMermaidState',
    messageDatasetKey: 'runtimeMermaidMessage',
    failedMessage: 'Mermaid 图表渲染失败。',
    timeoutMessage: 'Mermaid 图表渲染超时。',
  },
  {
    type: 'model3d',
    stateSelector: MODEL_STATE_SELECTOR,
    stateDatasetKey: 'runtimeModelState',
    messageDatasetKey: 'runtimeModelMessage',
    failedMessage: '三维模型渲染失败。',
    timeoutMessage: '三维模型渲染超时。',
  },
]

/**
 * 注册浏览器全局截图资源等待函数，供 Backend Playwright 截图前调用。
 */
export function registerEditorVisualAssetProbe(): void {
  if (typeof window === 'undefined') {
    return
  }

  window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__ = waitForEditorVisualAssets
}

/**
 * 等待文档内有限次动画自然结束；无限循环动画不会阻塞调用方。
 * @param timeoutMs 动画等待上限，默认 5 秒
 */
export async function waitForFiniteDocumentAnimations(timeoutMs = ANIMATION_SETTLE_TIMEOUT_MS): Promise<void> {
  const normalizedTimeout = Math.max(0, Math.round(Number(timeoutMs) || 0))
  const scope = createVisualAssetWaitScope()
  try { await waitForFiniteAnimationsSettled(Date.now() + normalizedTimeout, scope, normalizedTimeout) }
  finally { scope.dispose() }
}

/**
 * 等待当前文档中的关键视觉资源加载完成。
 * @param options 等待配置
 * @returns 结构化等待结果，调用方据此决定是否允许截图
 */
export async function waitForEditorVisualAssets(
  options: EditorVisualAssetWaitOptions = {},
): Promise<EditorVisualAssetWaitResult> {
  const scope = createVisualAssetWaitScope(options.signal)
  try { return await waitForVisualAssetsInScope(options, scope) }
  finally { scope.dispose() }
}

/** 整轮探测共享取消域，未胜出的超时和离页后的资源监听均在出口释放。 */
async function waitForVisualAssetsInScope(options: EditorVisualAssetWaitOptions, scope: VisualAssetWaitScope): Promise<EditorVisualAssetWaitResult> {
  scope.check()
  const startedAt = Date.now()
  const timeoutMs = normalizeTimeout(options.timeoutMs)
  const root = options.root ?? document
  const deadlineAt = startedAt + timeoutMs
  const failed: EditorVisualAssetIssue[] = []
  const pending: EditorVisualAssetIssue[] = []
  let timedOut = false

  const viewPreviewResult = await waitForViewPreviewReady(deadlineAt, root, scope)
  failed.push(...viewPreviewResult.failed)
  pending.push(...viewPreviewResult.pending)
  timedOut = timedOut || viewPreviewResult.timedOut

  let diagramTotal = 0
  let diagramLoaded = 0
  for (const probe of RUNTIME_DIAGRAM_PROBES) {
    const diagramResult = await waitForRuntimeDiagramReady(deadlineAt, probe, root, scope)
    diagramTotal += diagramResult.total
    diagramLoaded += diagramResult.loaded
    failed.push(...diagramResult.failed)
    pending.push(...diagramResult.pending)
    timedOut = timedOut || diagramResult.timedOut
  }

  const tasks = [...collectVisualAssetTasks(root), ...(options.staticMedia ?? isStaticExecution(getRuntimeExecutionPolicy().kind)
    ? collectStaticVideoTasks(root) : [])]
  const taskResult = await waitForTasks(tasks, deadlineAt, scope)
  failed.push(...taskResult.failed)
  pending.push(...taskResult.pending)
  timedOut = timedOut || taskResult.timedOut

  const fontResult = await waitForFontsReady(deadlineAt, scope)
  failed.push(...fontResult.failed)
  pending.push(...fontResult.pending)
  timedOut = timedOut || fontResult.timedOut

  if (options.includeAnimations !== false && !isStaticExecution(getRuntimeExecutionPolicy().kind)) {
    await waitForFiniteAnimationsSettled(deadlineAt, scope)
  }

  await scope.frame()
  await scope.frame()

  return {
    ok: failed.length === 0 && pending.length === 0 && !timedOut,
    timedOut,
    total: tasks.length + diagramTotal,
    loaded: taskResult.loaded + diagramLoaded,
    failed,
    pending,
    waitedMs: Date.now() - startedAt,
  }
}

/**
 * 规范化等待超时时间。
 * @param timeoutMs 原始超时时间
 * @returns 有效的毫秒数
 */
function normalizeTimeout(timeoutMs: number | undefined): number {
  const normalized = Number(timeoutMs)
  if (!Number.isFinite(normalized) || normalized <= 0) {
    return DEFAULT_VISUAL_READY_TIMEOUT_MS
  }
  return Math.max(100, Math.round(normalized))
}

/**
 * 等待单页预览组件完成异步模块加载。
 * @param deadlineAt 截止时间戳
 * @returns 等待结果
 */
async function waitForViewPreviewReady(deadlineAt: number, root: ParentNode, scope: VisualAssetWaitScope): Promise<{
  failed: EditorVisualAssetIssue[]
  pending: EditorVisualAssetIssue[]
  timedOut: boolean
}> {
  while (Date.now() < deadlineAt) {
    scope.check()
    const elements = Array.from(root.querySelectorAll<HTMLElement>(VIEW_PREVIEW_STATE_SELECTOR))
    if (elements.length === 0) {
      return { failed: [], pending: [], timedOut: false }
    }

    const failedElement = elements.find(element => element.dataset.runtimeViewPreviewState === 'error')
    if (failedElement) {
      return {
        failed: [{
          type: 'view-preview',
          message: failedElement.dataset.runtimeViewPreviewMessage || '单页预览组件加载失败。',
        }],
        pending: [],
        timedOut: false,
      }
    }

    if (elements.every(element => element.dataset.runtimeViewPreviewState === 'ready')) {
      return { failed: [], pending: [], timedOut: false }
    }

    await scope.delay(Math.min(50, Math.max(0, deadlineAt - Date.now())))
  }

  return {
    failed: [],
    pending: [{
      type: 'view-preview',
      message: '单页预览组件加载超时。',
    }],
    timedOut: true,
  }
}

/**
 * 等待 Runtime 图表组件完成 SVG 输出与缩放。
 * @param deadlineAt 截止时间戳
 * @param probe 图表探针配置
 * @returns 等待结果
 */
async function waitForRuntimeDiagramReady(deadlineAt: number, probe: RuntimeDiagramProbe, root: ParentNode, scope: VisualAssetWaitScope): Promise<{
  total: number
  loaded: number
  failed: EditorVisualAssetIssue[]
  pending: EditorVisualAssetIssue[]
  timedOut: boolean
}> {
  let latestElements: HTMLElement[] = []
  while (Date.now() < deadlineAt) {
    scope.check()
    latestElements = Array.from(root.querySelectorAll<HTMLElement>(probe.stateSelector))
    if (latestElements.length === 0) {
      return { total: 0, loaded: 0, failed: [], pending: [], timedOut: false }
    }

    const failedElement = latestElements.find(element => element.dataset[probe.stateDatasetKey] === 'error')
    if (failedElement) {
      return {
        total: latestElements.length,
        loaded: latestElements.filter(element => element.dataset[probe.stateDatasetKey] === 'ready').length,
        failed: [{
          type: probe.type,
          message: failedElement.dataset[probe.messageDatasetKey] || probe.failedMessage,
        }],
        pending: [],
        timedOut: false,
      }
    }

    if (latestElements.every(element => element.dataset[probe.stateDatasetKey] === 'ready')) {
      return {
        total: latestElements.length,
        loaded: latestElements.length,
        failed: [],
        pending: [],
        timedOut: false,
      }
    }

    await scope.delay(Math.min(50, Math.max(0, deadlineAt - Date.now())))
  }

  const elements = latestElements.length > 0
    ? latestElements
    : Array.from(root.querySelectorAll<HTMLElement>(probe.stateSelector))
  return {
    total: elements.length,
    loaded: elements.filter(element => element.dataset[probe.stateDatasetKey] === 'ready').length,
    failed: [],
    pending: elements
      .filter(element => element.dataset[probe.stateDatasetKey] !== 'ready')
      .map((element): EditorVisualAssetIssue => ({
        type: probe.type,
        message: element.dataset[probe.messageDatasetKey] || probe.timeoutMessage,
      })),
    timedOut: elements.some(element => element.dataset[probe.stateDatasetKey] !== 'ready'),
  }
}

/**
 * 等待一组视觉资源任务，直至全部完成或达到截止时间。
 * @param tasks 任务列表
 * @param deadlineAt 截止时间戳
 * @returns 聚合结果
 */
async function waitForTasks(tasks: VisualAssetTask[], deadlineAt: number, scope: VisualAssetWaitScope): Promise<{
  loaded: number
  failed: EditorVisualAssetIssue[]
  pending: EditorVisualAssetIssue[]
  timedOut: boolean
}> {
  if (tasks.length === 0) {
    return { loaded: 0, failed: [], pending: [], timedOut: false }
  }

  const statuses: TaskStatus[] = tasks.map(() => 'pending')
  const failed: EditorVisualAssetIssue[] = []
  const remainingMs = Math.max(0, deadlineAt - Date.now())
  if (remainingMs === 0) {
    return { loaded: 0, failed: [], pending: tasks.map(({ type, url, message }) => ({ type, url, message })), timedOut: true }
  }
  let timedOut = false

  const allTasks = Promise.all(tasks.map((task, index) => (
    task.wait(scope)
      .then(() => {
        scope.check()
        statuses[index] = 'loaded'
      })
      .catch((error) => {
        scope.check()
        statuses[index] = 'failed'
        failed.push({
          type: task.type,
          url: task.url,
          message: error instanceof Error ? error.message : task.message,
        })
      })
  )))

  await Promise.race([
    allTasks,
    scope.delay(remainingMs).then(() => {
      timedOut = statuses.some(status => status === 'pending')
    }),
  ])

  const pending = tasks
    .filter((_, index) => statuses[index] === 'pending')
    .map((task): EditorVisualAssetIssue => ({
      type: task.type,
      url: task.url,
      message: task.message,
    }))

  return {
    loaded: statuses.filter(status => status === 'loaded').length,
    failed,
    pending,
    timedOut: timedOut || pending.length > 0,
  }
}

/**
 * 等待字体加载完成。
 * @param deadlineAt 截止时间戳
 * @returns 字体等待结果
 */
async function waitForFontsReady(deadlineAt: number, scope: VisualAssetWaitScope): Promise<{
  failed: EditorVisualAssetIssue[]
  pending: EditorVisualAssetIssue[]
  timedOut: boolean
}> {
  if (!document.fonts?.ready) {
    return { failed: [], pending: [], timedOut: false }
  }

  const remainingMs = Math.max(0, deadlineAt - Date.now())
  let timedOut = remainingMs <= 0
  let failed: EditorVisualAssetIssue | null = null
  let completed = false

  if (!timedOut) {
    await Promise.race([
      scope.wait(document.fonts.ready)
        .then(() => {
          completed = true
        })
        .catch((error) => {
          scope.check()
          failed = {
            type: 'font',
            message: error instanceof Error ? error.message : '字体资源加载失败。',
          }
        }),
      scope.delay(remainingMs).then(() => {
        timedOut = !completed && !failed
      }),
    ])
  }

  if (failed) {
    return { failed: [failed], pending: [], timedOut: false }
  }
  if (timedOut) {
    return {
      failed: [],
      pending: [{ type: 'font', message: '字体资源加载超时。' }],
      timedOut: true,
    }
  }
  return { failed: [], pending: [], timedOut: false }
}

/**
 * 尽力等待文档中有限次动画自然结束，让入场动画和 animationend 链路跑完。
 * 无限循环动画直接跳过；超时不计入失败，静态捕获不会调用本等待。
 * @param deadlineAt 整体截止时间戳
 */
async function waitForFiniteAnimationsSettled(
  deadlineAt: number,
  scope: VisualAssetWaitScope,
  settleTimeoutMs = ANIMATION_SETTLE_TIMEOUT_MS,
): Promise<void> {
  if (typeof document.getAnimations !== 'function') {
    return
  }

  // 动画等待单独设较短上限，避免超长动画拖慢截图队列吞吐。
  const settleDeadlineAt = Math.min(deadlineAt, Date.now() + settleTimeoutMs)
  const awaited = new WeakSet<Animation>()

  while (Date.now() < settleDeadlineAt) {
    scope.check()
    // 循环重新收集，覆盖交错动画链中等待期间新启动的动画。
    const running = document.getAnimations().filter(
      animation => !awaited.has(animation) && isWaitableFiniteAnimation(animation),
    )
    if (running.length === 0) {
      return
    }
    running.forEach(animation => awaited.add(animation))

    const remainingMs = Math.max(0, settleDeadlineAt - Date.now())
    await Promise.race([
      // 动画被取消时 finished 会 reject，这里视为已结束。
      Promise.all(running.map(animation => animation.finished.catch(() => undefined))),
      scope.delay(remainingMs),
    ])
  }
}

/**
 * 判断动画是否为值得等待的有限次运行中动画。
 * @param animation Web Animations 对象
 * @returns 是否应等待其 finished
 */
function isWaitableFiniteAnimation(animation: Animation): boolean {
  if (animation.playState === 'finished' || animation.playState === 'idle') {
    return false
  }
  const timing = animation.effect?.getTiming()
  if (!timing) {
    return false
  }
  return Number.isFinite(Number(timing.iterations ?? 1))
}
