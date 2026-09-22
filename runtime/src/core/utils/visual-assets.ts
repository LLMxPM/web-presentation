/**
 * 文件用途：提供编辑器截图前的视觉资源就绪探针，等待页面组件、图片、背景图和字体完成渲染。
 */

export interface EditorVisualAssetWaitOptions {
  /** 最长等待时间，单位毫秒。 */
  timeoutMs?: number
}

export interface EditorVisualAssetIssue {
  /** 资源类型，用于 Backend 压缩错误详情。 */
  type: 'view-preview' | 'drawio' | 'mermaid' | 'image' | 'background' | 'font'
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

interface VisualAssetTask {
  type: EditorVisualAssetIssue['type']
  url?: string
  message: string
  wait: () => Promise<void>
}

type TaskStatus = 'pending' | 'loaded' | 'failed'
type RuntimeDiagramType = Extract<EditorVisualAssetIssue['type'], 'drawio' | 'mermaid'>

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
  await waitForFiniteAnimationsSettled(Date.now() + normalizedTimeout, normalizedTimeout)
}

/**
 * 等待当前文档中的关键视觉资源加载完成。
 * @param options 等待配置
 * @returns 结构化等待结果，调用方据此决定是否允许截图
 */
export async function waitForEditorVisualAssets(
  options: EditorVisualAssetWaitOptions = {},
): Promise<EditorVisualAssetWaitResult> {
  const startedAt = Date.now()
  const timeoutMs = normalizeTimeout(options.timeoutMs)
  const deadlineAt = startedAt + timeoutMs
  const failed: EditorVisualAssetIssue[] = []
  const pending: EditorVisualAssetIssue[] = []
  let timedOut = false

  const viewPreviewResult = await waitForViewPreviewReady(deadlineAt)
  failed.push(...viewPreviewResult.failed)
  pending.push(...viewPreviewResult.pending)
  timedOut = timedOut || viewPreviewResult.timedOut

  let diagramTotal = 0
  let diagramLoaded = 0
  for (const probe of RUNTIME_DIAGRAM_PROBES) {
    const diagramResult = await waitForRuntimeDiagramReady(deadlineAt, probe)
    diagramTotal += diagramResult.total
    diagramLoaded += diagramResult.loaded
    failed.push(...diagramResult.failed)
    pending.push(...diagramResult.pending)
    timedOut = timedOut || diagramResult.timedOut
  }

  const tasks = collectVisualAssetTasks(document)
  const taskResult = await waitForTasks(tasks, deadlineAt)
  failed.push(...taskResult.failed)
  pending.push(...taskResult.pending)
  timedOut = timedOut || taskResult.timedOut

  const fontResult = await waitForFontsReady(deadlineAt)
  failed.push(...fontResult.failed)
  pending.push(...fontResult.pending)
  timedOut = timedOut || fontResult.timedOut

  await waitForFiniteAnimationsSettled(deadlineAt)

  await waitForAnimationFrame()
  await waitForAnimationFrame()

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
async function waitForViewPreviewReady(deadlineAt: number): Promise<{
  failed: EditorVisualAssetIssue[]
  pending: EditorVisualAssetIssue[]
  timedOut: boolean
}> {
  while (Date.now() <= deadlineAt) {
    const elements = Array.from(document.querySelectorAll<HTMLElement>(VIEW_PREVIEW_STATE_SELECTOR))
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

    await sleep(Math.min(50, Math.max(0, deadlineAt - Date.now())))
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
async function waitForRuntimeDiagramReady(deadlineAt: number, probe: RuntimeDiagramProbe): Promise<{
  total: number
  loaded: number
  failed: EditorVisualAssetIssue[]
  pending: EditorVisualAssetIssue[]
  timedOut: boolean
}> {
  let latestElements: HTMLElement[] = []
  while (Date.now() <= deadlineAt) {
    latestElements = Array.from(document.querySelectorAll<HTMLElement>(probe.stateSelector))
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

    await sleep(Math.min(50, Math.max(0, deadlineAt - Date.now())))
  }

  const elements = latestElements.length > 0
    ? latestElements
    : Array.from(document.querySelectorAll<HTMLElement>(probe.stateSelector))
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
 * 收集文档中的图片和 CSS 背景图加载任务。
 * @param root 查询根节点
 * @returns 视觉资源任务
 */
function collectVisualAssetTasks(root: Document): VisualAssetTask[] {
  return [
    ...collectImageTasks(root),
    ...collectBackgroundImageTasks(root),
  ]
}

/**
 * 收集 img 元素加载任务。
 * @param root 查询根节点
 * @returns 图片任务列表
 */
function collectImageTasks(root: Document): VisualAssetTask[] {
  return Array.from(root.querySelectorAll<HTMLImageElement>('img'))
    .map((image): VisualAssetTask | null => {
      const url = image.currentSrc || image.src
      if (!url) {
        return null
      }
      return {
        type: 'image',
        url,
        message: `图片资源未加载完成：${url}`,
        wait: () => waitForHtmlImage(image, url),
      }
    })
    .filter((task): task is VisualAssetTask => Boolean(task))
}

/**
 * 收集元素 background-image 中的 URL 加载任务。
 * @param root 查询根节点
 * @returns 背景图任务列表
 */
function collectBackgroundImageTasks(root: Document): VisualAssetTask[] {
  const seenUrls = new Set<string>()
  const tasks: VisualAssetTask[] = []
  const elements = [
    root.documentElement,
    root.body,
    ...Array.from(root.querySelectorAll<HTMLElement>('*')),
  ].filter((element): element is HTMLElement => Boolean(element))

  for (const element of elements) {
    const backgroundImage = window.getComputedStyle(element).backgroundImage
    for (const url of extractCssUrls(backgroundImage)) {
      if (!url || seenUrls.has(url)) {
        continue
      }
      seenUrls.add(url)
      tasks.push({
        type: 'background',
        url,
        message: `背景图资源未加载完成：${url}`,
        wait: () => waitForDetachedImage(url),
      })
    }
  }

  return tasks
}

/**
 * 等待一组视觉资源任务，直至全部完成或达到截止时间。
 * @param tasks 任务列表
 * @param deadlineAt 截止时间戳
 * @returns 聚合结果
 */
async function waitForTasks(tasks: VisualAssetTask[], deadlineAt: number): Promise<{
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
  let timedOut = remainingMs <= 0

  const allTasks = Promise.all(tasks.map((task, index) => (
    task.wait()
      .then(() => {
        statuses[index] = 'loaded'
      })
      .catch((error) => {
        statuses[index] = 'failed'
        failed.push({
          type: task.type,
          url: task.url,
          message: error instanceof Error ? error.message : task.message,
        })
      })
  )))

  if (!timedOut) {
    await Promise.race([
      allTasks,
      sleep(remainingMs).then(() => {
        timedOut = statuses.some(status => status === 'pending')
      }),
    ])
  }

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
 * 等待已有 img 元素完成加载与解码。
 * @param image 图片元素
 * @param url 图片地址
 */
async function waitForHtmlImage(image: HTMLImageElement, url: string): Promise<void> {
  if (!isHtmlImageLoaded(image)) {
    await new Promise<void>((resolve, reject) => {
      const cleanup = () => {
        image.removeEventListener('load', handleLoad)
        image.removeEventListener('error', handleError)
      }
      const handleLoad = () => {
        cleanup()
        resolve()
      }
      const handleError = () => {
        cleanup()
        reject(new Error(`图片资源加载失败：${url}`))
      }
      image.addEventListener('load', handleLoad, { once: true })
      image.addEventListener('error', handleError, { once: true })
    })
  }

  if (!isHtmlImageLoaded(image)) {
    throw new Error(`图片资源加载失败：${url}`)
  }

  if (typeof image.decode === 'function') {
    await image.decode()
  }
}

/**
 * 使用脱离 DOM 的 Image 对象等待背景图 URL 可加载。
 * @param url 背景图地址
 */
async function waitForDetachedImage(url: string): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const image = new Image()
    const cleanup = () => {
      image.removeEventListener('load', handleLoad)
      image.removeEventListener('error', handleError)
    }
    const handleLoad = () => {
      cleanup()
      resolve()
    }
    const handleError = () => {
      cleanup()
      reject(new Error(`背景图资源加载失败：${url}`))
    }
    image.addEventListener('load', handleLoad, { once: true })
    image.addEventListener('error', handleError, { once: true })
    image.src = url
  })
}

/**
 * 判断 img 元素是否已有有效尺寸。
 * @param image 图片元素
 * @returns 是否加载完成
 */
function isHtmlImageLoaded(image: HTMLImageElement): boolean {
  return image.complete && image.naturalWidth > 0 && image.naturalHeight > 0
}

/**
 * 等待字体加载完成。
 * @param deadlineAt 截止时间戳
 * @returns 字体等待结果
 */
async function waitForFontsReady(deadlineAt: number): Promise<{
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
      document.fonts.ready
        .then(() => {
          completed = true
        })
        .catch((error) => {
          failed = {
            type: 'font',
            message: error instanceof Error ? error.message : '字体资源加载失败。',
          }
        }),
      sleep(remainingMs).then(() => {
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
 * 无限循环动画直接跳过；超时不计入失败，由截图侧 animations="disabled" 兜底快进。
 * @param deadlineAt 整体截止时间戳
 */
async function waitForFiniteAnimationsSettled(
  deadlineAt: number,
  settleTimeoutMs = ANIMATION_SETTLE_TIMEOUT_MS,
): Promise<void> {
  if (typeof document.getAnimations !== 'function') {
    return
  }

  // 动画等待单独设较短上限，避免超长动画拖慢截图队列吞吐。
  const settleDeadlineAt = Math.min(deadlineAt, Date.now() + settleTimeoutMs)
  const awaited = new WeakSet<Animation>()

  while (Date.now() <= settleDeadlineAt) {
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
      sleep(remainingMs),
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

/**
 * 从 CSS url(...) 表达式中提取 URL。
 * @param cssValue CSS 属性值
 * @returns URL 列表
 */
export function extractCssUrls(cssValue: string): string[] {
  const urls: string[] = []
  const pattern = /url\((?:"([^"]*)"|'([^']*)'|([^)]*))\)/g
  let match: RegExpExecArray | null
  while ((match = pattern.exec(cssValue || '')) !== null) {
    const rawUrl = (match[1] || match[2] || match[3] || '').trim()
    if (rawUrl) {
      urls.push(rawUrl)
    }
  }
  return urls
}

/**
 * 等待一次浏览器绘制帧。
 */
function waitForAnimationFrame(): Promise<void> {
  return new Promise(resolve => {
    if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(() => resolve())
      return
    }
    window.setTimeout(resolve, 16)
  })
}

/**
 * 延迟指定毫秒。
 * @param ms 延迟时间
 */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => window.setTimeout(resolve, Math.max(0, ms)))
}
