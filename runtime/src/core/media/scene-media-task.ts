/** 文件功能：把显式自动媒体接为 Scene 任务，以 ended 实际完成；播放受阻只接受观众窗口本地重试。 */
import { watch } from 'vue'
import { SceneSessionError, type SceneTask, type SceneTaskContext } from '@/core/scene/types'
import { getRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { isStaticSceneRoot } from '@/core/scene/scene-scope'
import { runtimeAudioBus } from '@/core/audio/runtime-audio-bus'
import type { AudioBus, AudioLease } from '@/core/audio/audio-bus'
import { readSceneMediaRegistration } from './scene-media-registration'

export interface SceneMediaTaskOptions extends Pick<SceneTask, 'id' | 'role' | 'startMs' | 'afterTrack' | 'offsetMs'> {
  target(): HTMLMediaElement | null | undefined
}
const primaryMedia = new WeakMap<AbortSignal, Set<HTMLMediaElement>>()

/** 首轮每个 Scene 最多一个自动发声主媒体，静音视频不占名额。 */
function acquirePrimary(signal: AbortSignal, element: HTMLMediaElement, audible: boolean): () => void {
  if (!audible) return () => {}
  let elements = primaryMedia.get(signal)
  if (!elements) { elements = new Set(); primaryMedia.set(signal, elements) }
  if (elements.size && !elements.has(element)) throw new SceneSessionError('SCENE_MEDIA_PRIMARY_LIMIT', '每页最多一个自动发声主媒体，其余自动视频必须静音。')
  elements.add(element)
  return () => { elements!.delete(element) }
}

/** 工厂只登记，prepare 才认领，run 才 play；不使用 duration 预估完成。 */
export function createSceneMediaTask(options: SceneMediaTaskOptions, bus: AudioBus = runtimeAudioBus): SceneTask {
  const spec = { ...options }
  let element: HTMLMediaElement | null = null, lease: AudioLease | null = null, context: SceneTaskContext | null = null
  let started = false, settled = false, suspended = false, playing = false, request = 0, source = ''
  let blocked: 'permission' | 'buffer' | null = null
  let resolve!: () => void, reject!: (error: unknown) => void, result: Promise<void> | null = null
  let releasePrimary = () => {}, stopWatch = () => {}, unregister = () => {}
  const listeners: Array<[string, EventListener]> = []

  /** 无论成功、失败或取消，清理都不依赖原生媒体 Promise 合作结束。 */
  function cleanup(): void {
    request += 1; settled = true; started = false
    stopWatch(); unregister(); releasePrimary()
    for (const [type, listener] of listeners.splice(0)) element?.removeEventListener(type, listener)
    if (lease) { bus.setRetry(lease, null); lease.release() }
    if (element) { try { element.currentTime = 0 } catch { /* 尚无可定位数据时保持停止。 */ } }
    resolve?.()
  }
  /** 错误有界化后交给 Scene，不能把资源 URL 或浏览器堆栈投影到跨窗口状态。 */
  function fail(code: string, message: string): void {
    if (settled) return
    reject?.(new SceneSessionError(code, message, spec.id)); cleanup()
  }
  /** 受阻原因由真实事件决定；仅 blocking 会冻结其它任务的有效时钟。 */
  function setBlocked(value: typeof blocked): void {
    blocked = value
    context?.setBlocked(value === 'permission' ? '自动媒体播放受阻，请在当前窗口点击允许播放。' : value === 'buffer' ? '媒体正在缓冲。' : null)
  }
  /** 在调用栈内立即发起原生 play，迟到回执和离页后的重试都不再改变当前 Scene。 */
  async function attempt(): Promise<void> {
    if (!started || settled || !lease || !element || context?.signal.aborted || document.hidden || bus.state.value.suspended || (suspended && !blocked)) return
    const token = ++request
    const outcome = await lease.play()
    if (token !== request || settled || context?.signal.aborted) return
    if (outcome === 'played') { playing = true; bus.setRetry(lease, null); setBlocked(null) }
    else if (outcome === 'blocked') { playing = false; setBlocked('permission'); bus.setRetry(lease, attempt) }
    else if (outcome === 'failed') fail('SCENE_MEDIA_PLAY_FAILED', '媒体解码或播放失败。')
  }
  /** 只对已登记的这一个媒体安装事件，不寻找其它页面或旁白。 */
  function listen(type: string, listener: () => void): void { listeners.push([type, listener]); element!.addEventListener(type, listener) }

  return { id: spec.id, role: spec.role, startMs: spec.startMs, afterTrack: spec.afterTrack, offsetMs: spec.offsetMs,
    // prepare 前只能用声明判断有限性；原生 loop 在 prepare 复核后由 getter 向任务图提供。
    get finite() { const target = spec.target(); return target ? !readSceneMediaRegistration(target)?.loop : true },
    prepare(value) {
      context = value; element = spec.target() ?? null
      if (!(element instanceof HTMLMediaElement) || !element.isConnected || !getRuntimeExecutionPolicy().allowMediaPlayback || isStaticSceneRoot(element)) {
        throw new SceneSessionError('SCENE_MEDIA_UNAVAILABLE', '媒体目标未挂载或当前执行策略为静态。', spec.id)
      }
      const registration = readSceneMediaRegistration(element)
      if (!registration || registration.purpose === 'content' || registration.signal.aborted) throw new SceneSessionError('SCENE_MEDIA_PURPOSE_REQUIRED', '自动媒体必须显式声明 narration 或 automatic 用途。', spec.id)
      if ((registration.loop || element.loop) && spec.role === 'blocking') throw new SceneSessionError('SCENE_MEDIA_LOOP_BLOCKING', '循环媒体只能作为 ambient。', spec.id)
      releasePrimary = acquirePrimary(value.signal, element, !registration.muted)
      value.onCleanup(cleanup)
      source = element.getAttribute('src') ?? ''
      if (!source || element.error) throw new SceneSessionError('SCENE_MEDIA_UNAVAILABLE', '媒体资源缺失或已加载失败。', spec.id)
      lease = bus.claim(element, { owner: 'scene', group: registration.purpose === 'narration' || !registration.muted ? 'narration' : 'content', gain: registration.gain, muted: registration.muted })
      result = new Promise<void>((yes, no) => { resolve = yes; reject = no }); void result.catch(() => {})
      listen('ended', () => { if (!settled && started) { settled = true; playing = false; bus.setRetry(lease!, null); setBlocked(null); resolve() } })
      listen('error', () => fail('SCENE_MEDIA_PLAY_FAILED', '媒体资源加载或解码失败。'))
      listen('waiting', () => { if (started && !settled) { playing = false; setBlocked('buffer') } })
      listen('stalled', () => { if (started && !settled) { playing = false; setBlocked('buffer') } })
      listen('playing', () => { if (started && !settled) { playing = true; bus.setRetry(lease!, null); setBlocked(null) } })
      listen('canplay', () => { if (blocked === 'buffer' && started && !settled) void attempt() })
      listen('loadstart', () => { if (element?.getAttribute('src') !== source) fail('SCENE_MEDIA_REPLACED', '播放期间媒体资源已替换。') })
      const invalidated = () => fail('SCENE_MEDIA_REPLACED', '媒体组件已经卸载或用途/资源发生变化。')
      registration.signal.addEventListener('abort', invalidated, { once: true })
      unregister = () => registration.signal.removeEventListener('abort', invalidated)
      stopWatch = watch(() => bus.state.value.suspended, value => { if (!value && blocked === 'buffer') void attempt() }, { flush: 'sync' })
    },
    run() {
      if (!result || settled || !element || element.getAttribute('src') !== source) throw new SceneSessionError('SCENE_MEDIA_UNAVAILABLE', '媒体任务尚未准备或资源已经失效。', spec.id)
      started = true; void attempt(); return result
    },
    setSuspended(value) {
      suspended = value
      if (value && !blocked) { playing = false; request += 1; lease?.pause() }
      else if (!value && started && !playing && blocked !== 'permission') void attempt()
    },
  }
}
