/** 文件功能：收集图片与 CSS 背景图准备任务，取消或超时后撤销图片监听与解码观察。 */
import type { EditorVisualAssetIssue } from './visual-assets'
import type { VisualAssetWaitScope } from './visual-asset-wait'

export interface VisualAssetTask {
  type: EditorVisualAssetIssue['type']
  url?: string
  message: string
  wait(scope: VisualAssetWaitScope): Promise<void>
}

/** 只扫描指定画布，保持图片加载错误和回退占位的既有语义。 */
export function collectVisualAssetTasks(root: ParentNode): VisualAssetTask[] {
  const images = Array.from(root.querySelectorAll<HTMLImageElement>('img')).flatMap(image => {
    const url = image.currentSrc || image.src
    if (!url) return []
    return [{ type: 'image' as const, url, message: `图片资源未加载完成：${url}`,
      wait: (scope: VisualAssetWaitScope) => waitForHtmlImage(image, url, scope) }]
  })
  return [...images, ...collectBackgroundImageTasks(root)]
}

/** 背景图按 URL 去重；临时 Image 仅负责探测，不改页面样式。 */
function collectBackgroundImageTasks(root: ParentNode): VisualAssetTask[] {
  const seen = new Set<string>(), tasks: VisualAssetTask[] = []
  const elements = [
    ...(root instanceof Document ? [root.documentElement, root.body] : [root]),
    ...Array.from(root.querySelectorAll<HTMLElement>('*')),
  ].filter((element): element is HTMLElement => element instanceof HTMLElement)
  for (const element of elements) {
    for (const url of extractCssUrls(window.getComputedStyle(element).backgroundImage)) {
      if (seen.has(url)) continue
      seen.add(url)
      tasks.push({ type: 'background', url, message: `背景图资源未加载完成：${url}`,
        wait: scope => waitForImageLoad(new Image(), url, scope, false, true) })
    }
  }
  return tasks
}

/** 已有图片等待加载与解码；平台的回退占位可以继续显示，取消始终优先。 */
async function waitForHtmlImage(image: HTMLImageElement, url: string, scope: VisualAssetWaitScope): Promise<void> {
  scope.check()
  const fallback = image.dataset.runtimeImageFallback === 'true'
  if (!image.complete) await waitForImageLoad(image, url, scope, fallback)
  scope.check()
  if (!isHtmlImageLoaded(image)) {
    if (fallback) return
    throw new Error(`图片资源加载失败：${url}`)
  }
  if (typeof image.decode === 'function') await scope.wait(image.decode())
}

/** 撤销成功、失败和取消的全部监听；仅背景图探测可给临时图片设置地址。 */
function waitForImageLoad(image: HTMLImageElement, url: string, scope: VisualAssetWaitScope,
  fallback: boolean, detached = false): Promise<void> {
  scope.check()
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      image.removeEventListener('load', loaded)
      image.removeEventListener('error', failed)
      scope.signal.removeEventListener('abort', cancelled)
    }
    const loaded = () => { cleanup(); resolve() }
    const failed = () => {
      cleanup()
      if (fallback) resolve()
      else reject(new Error(`${detached ? '背景图' : '图片'}资源加载失败：${url}`))
    }
    const cancelled = () => { cleanup(); reject(new DOMException('视觉资源等待已取消。', 'AbortError')) }
    image.addEventListener('load', loaded, { once: true })
    image.addEventListener('error', failed, { once: true })
    scope.signal.addEventListener('abort', cancelled, { once: true })
    if (detached) image.src = url
    if (scope.signal.aborted) cancelled()
  })
}

/** 有效图片必须已经完成加载并具有双向尺寸。 */
function isHtmlImageLoaded(image: HTMLImageElement): boolean {
  return image.complete && image.naturalWidth > 0 && image.naturalHeight > 0
}

/** 从 CSS url(...) 提取非空地址，兼容单双引号和无引号形式。 */
export function extractCssUrls(cssValue: string): string[] {
  const urls: string[] = []
  const pattern = /url\((?:"([^"]*)"|'([^']*)'|([^)]*))\)/g
  let match: RegExpExecArray | null
  while ((match = pattern.exec(cssValue || '')) !== null) {
    const url = (match[1] || match[2] || match[3] || '').trim()
    if (url) urls.push(url)
  }
  return urls
}
