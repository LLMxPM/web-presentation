// 文件功能：WP01 异步媒体定位、解码帧确认与单媒体主时钟的受控实验。
export const budgets = Object.freeze({ driftSoftMs: 30, driftHardMs: 80, seekTimeoutMs: 1000, correctionIntervalMs: 100 })

/** 等待可移除的媒体事件；期限与错误均释放监听，防止失败路径积累。 */
export function waitEvent(element, event, timeoutMs = budgets.seekTimeoutMs) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => finish(new Error(`TIMEOUT:${event}`)), timeoutMs)
    const success = () => finish()
    const failure = () => finish(new Error(`MEDIA_ERROR:${element.error?.code}`))
    /** 本次操作唯一收敛点，事件和定时器一起释放。 */
    function finish(error) {
      clearTimeout(timer); element.removeEventListener(event, success); element.removeEventListener('error', failure)
      if (error) reject(error); else resolve()
    }
    element.addEventListener(event, success, { once: true }); element.addEventListener('error', failure, { once: true })
  })
}

/** 准备 metadata 与首帧；VOD 时长必须有限，MediaRecorder WebM 先经末尾探测建立时长。 */
export async function prepare(element, url) {
  const loaded = waitEvent(element, 'loadeddata', 5000)
  element.crossOrigin = 'anonymous'; element.src = url; element.preload = 'auto'; element.load()
  await loaded
  if (!Number.isFinite(element.duration)) {
    const ended = waitEvent(element, 'seeked', 5000); element.currentTime = 1e6; await ended
  }
  await seekMedia(element, 0)
}

/** 暂停定位，等待 seeked；视频必须由 rVFC 确认可呈现帧，不能只等 currentTime 属性写入。 */
export async function seekMedia(element, seconds) {
  element.pause()
  if (Math.abs(element.currentTime - seconds) < 0.00001 && element.readyState >= 2) return
  let frameId
  let timeout
  const frame = element.tagName === 'VIDEO' ? new Promise((resolve, reject) => {
    timeout = setTimeout(() => reject(new Error('FRAME_TIMEOUT')), budgets.seekTimeoutMs)
    frameId = element.requestVideoFrameCallback((_now, metadata) => resolve(metadata))
  }) : Promise.resolve(null)
  const seeked = waitEvent(element, 'seeked')
  element.currentTime = seconds
  try { await seeked; return await frame }
  finally { clearTimeout(timeout); if (frameId) element.cancelVideoFrameCallback(frameId) }
}

/** 以已解码画面读取像素 hash；CORS 失败会抛出，不能用不可读 canvas 伪通过截图。 */
export function videoPixels(video) {
  const canvas = document.createElement('canvas'); canvas.width = 320; canvas.height = 180
  const context = canvas.getContext('2d'); context.drawImage(video, 0, 0, 320, 180)
  const pixels = context.getImageData(0, 0, 320, 180).data
  let hash = 2166136261
  for (const byte of pixels) hash = Math.imul(hash ^ byte, 16777619)
  return hash >>> 0
}
