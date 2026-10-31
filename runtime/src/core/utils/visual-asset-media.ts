/** 文件功能：统一静态视频的海报解码和有界首帧准备，PNG、缩略图与导出共享且始终不调用 play。 */
import type { VisualAssetTask } from './visual-asset-images'
import type { VisualAssetWaitScope } from './visual-asset-wait'

const preparedPosters = new WeakMap<HTMLVideoElement, string>()

/** 只收集画布内有源或海报的视频；音频没有静态像素，不等待音频网络。 */
export function collectStaticVideoTasks(root: ParentNode): VisualAssetTask[] {
  return Array.from(root.querySelectorAll<HTMLVideoElement>('video')).flatMap(video => {
    const poster = video.getAttribute('poster')?.trim()
    const source = video.currentSrc || video.src || video.querySelector('source')?.src
    if (!poster && !source) return []
    return [{ type: 'video' as const, url: poster || source, message: poster ? '视频海报未就绪。' : '视频首帧未就绪。',
      wait: (scope: VisualAssetWaitScope) => prepareStaticVideo(video, poster || '', scope) }]
  })
}

/** 海报优先；无海报时只加载首帧，不推进时间、不等待媒体结束。 */
async function prepareStaticVideo(video: HTMLVideoElement, poster: string, scope: VisualAssetWaitScope): Promise<void> {
  scope.check()
  video.pause()
  video.autoplay = false
  video.removeAttribute('autoplay')
  video.muted = true
  if (poster) {
    const image = video.ownerDocument.createElement('img')
    await waitForPoster(image, poster, scope)
    scope.check()
    // load 恢复浏览器的 poster 显示标志；同一源重复探测不得反复重置或触发网络。
    const identity = `${video.getAttribute('src') || ''}|${video.querySelector('source')?.src || ''}|${poster}`
    if (preparedPosters.get(video) !== identity) {
      video.preload = 'none'
      video.load()
      preparedPosters.set(video, identity)
    }
    return
  }
  preparedPosters.delete(video)
  if (hasFrame(video)) return
  await new Promise<void>((resolve, reject) => {
    const events = ['loadeddata', 'canplay', 'seeked', 'error']
    const cleanup = () => {
      for (const event of events) video.removeEventListener(event, check)
      scope.signal.removeEventListener('abort', cancel)
    }
    const cancel = () => { cleanup(); reject(new DOMException('视频首帧等待已取消。', 'AbortError')) }
    const check = () => {
      if (video.error) { cleanup(); reject(new Error('视频资源加载失败。')) }
      else if (hasFrame(video)) { cleanup(); resolve() }
    }
    for (const event of events) video.addEventListener(event, check)
    scope.signal.addEventListener('abort', cancel, { once: true })
    try {
      video.preload = 'auto'
      if (video.readyState < 1) video.load()
      check()
    } catch (error) { cleanup(); reject(error) }
    if (scope.signal.aborted) cancel()
  })
  scope.check()
  video.pause()
}

/** 海报必须加载且解码成功；源视频加载失败不影响已经可读的海报。 */
async function waitForPoster(image: HTMLImageElement, url: string, scope: VisualAssetWaitScope): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const cleanup = () => {
      image.removeEventListener('load', loaded)
      image.removeEventListener('error', failed)
      scope.signal.removeEventListener('abort', cancel)
    }
    const loaded = () => { cleanup(); resolve() }
    const failed = () => { cleanup(); reject(new Error('视频海报加载失败。')) }
    const cancel = () => { cleanup(); reject(new DOMException('视频海报等待已取消。', 'AbortError')) }
    image.addEventListener('load', loaded, { once: true })
    image.addEventListener('error', failed, { once: true })
    scope.signal.addEventListener('abort', cancel, { once: true })
    image.src = url
    if (scope.signal.aborted) cancel()
    else if (image.complete) image.naturalWidth > 0 && image.naturalHeight > 0 ? loaded() : failed()
  })
  scope.check()
  if (typeof image.decode === 'function') await scope.wait(image.decode())
}

/** 首帧就绪须同时有解码数据和有效视频尺寸。 */
function hasFrame(video: HTMLVideoElement): boolean {
  return video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0
}
