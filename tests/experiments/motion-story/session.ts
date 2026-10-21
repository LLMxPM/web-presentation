// 文件功能：给三种创作写法提供相同的资源语义桥接与静态取帧；仅用于受控研发夹具。
import { seekMedia, videoPixels } from '../motion-wp01/media.mjs'
import type { Assets, Plan, Visual } from './types'

/** 由媒体主时钟采样 DOM/骨骼，正常 ended 后续走；不通过原生动画回调调度音视频。 */
export function createSession(assets: Assets, plan: Plan, visual: Visual) {
  const { audio, video, root } = assets.elements
  const clip = plan.get('model'), demo = plan.get('demo')
  let logicalMs = 0, playing = false, disposed = false, frozen = false, raf = 0, revision = 0
  let handoff = false, anchor = 0, videoActive = false, settling = false, playbackError: string | null = null
  const clamp = (value: number, end: number) => Math.max(0, Math.min(end, value))
  /** 绝对采样不依赖历史增量，骨骼轨道前后分别保持首尾姿态。 */
  function draw(ms: number) {
    logicalMs = clamp(ms, plan.durationMs)
    visual.sample(logicalMs)
    assets.model.sample(clamp(logicalMs - clip.startMs, clip.durationMs))
  }
  /** 暂停只终止自有 transport；原生动画始终处于受控采样状态。 */
  function pause() {
    revision++; playing = false; cancelAnimationFrame(raf); raf = 0
    audio.pause(); video.pause(); videoActive = false
  }
  /** 先暂停静音，再等待音频定位及视频解码帧；失效回执不得提交逻辑时间。 */
  async function sample(ms: number) {
    if (disposed || frozen) throw new Error('SESSION_CLOSED')
    pause(); const operation = revision
    audio.muted = true; video.muted = true
    const target = clamp(ms, plan.durationMs)
    await Promise.all([
      seekMedia(audio, clamp(target, assets.voiceDurationMs) / 1000),
      seekMedia(video, ((demo.inMs ?? 0) + clamp(target - demo.startMs, demo.durationMs)) / 1000),
    ])
    if (disposed || operation !== revision) return
    draw(target)
  }
  /** 只在旁白真实 ended 时交接；暂停、等待和播放失败均不会被当成正常结束。 */
  function ended() {
    if (!playing) return
    handoff = true; anchor = performance.now(); draw(assets.voiceDurationMs)
  }
  audio.addEventListener('ended', ended)
  /** 帧循环只推进 DOM 与骨骼；视频正常播放期间不逐帧改写 currentTime。 */
  function tick() {
    if (!playing || disposed) return
    const ms = handoff ? assets.voiceDurationMs + performance.now() - anchor : audio.currentTime * 1000
    draw(ms)
    const inVideo = ms >= demo.startMs && ms < demo.endMs
    if (inVideo && !videoActive) {
      videoActive = true; const operation = revision
      void video.play().then(() => { if (operation !== revision || disposed) video.pause() }).catch(error => { if (operation === revision && !disposed) { playbackError = String(error); pause() } })
    } else if (!inVideo && videoActive) { video.pause(); videoActive = false }
    if (ms >= plan.durationMs) {
      // 正常结束也要等待裁切终帧；暂停发生在本轮，解码完成才报告可捕获。
      settling = true
      void sample(plan.durationMs).catch(error => { if (!disposed) playbackError = String(error) }).finally(() => { settling = false })
      return
    }
    raf = requestAnimationFrame(tick)
  }
  /** 夹具的显式播放入口从头开始；产品 autoplay/buffering 协议仍留待后续工作包。 */
  async function play() {
    await sample(0)
    if (disposed) return
    playing = true; handoff = false; playbackError = null; audio.muted = false
    const operation = revision
    try { await audio.play() } catch (error) { playbackError = String(error); pause(); return }
    if (operation !== revision || disposed) { audio.pause(); return }
    raf = requestAnimationFrame(tick)
  }
  /** 固定可见状态供捕获；撤销初始样式只能在最终 dispose 时执行。 */
  function freeze() { pause(); visual.freeze(); frozen = true }
  /** 释放 RAF、事件、原生作用域、媒体与 WebGL；允许卸载时重复调用。 */
  function dispose() {
    if (disposed) return
    pause(); disposed = true; audio.removeEventListener('ended', ended)
    visual.dispose(); assets.dispose()
  }
  /** 读取实际 DOM、媒体、模型及视频像素，而非仅报告计划对象。 */
  function state() {
    const opacity = (selector: string) => +Number(getComputedStyle(root.querySelector(selector)!).opacity).toFixed(5)
    return {
      logicalMs: +logicalMs.toFixed(3), durationMs: plan.durationMs, playing, disposed, frozen, settling, rafActive: raf !== 0, handoff, playbackError,
      clip: assets.clip, tracks: plan.tracks,
      title: opacity('.title'), cards: [1, 2, 3].map(i => opacity(`.card:nth-child(${i})`)),
      clipCaption: opacity('.clip-caption'), demoCaption: opacity('.demo-caption'),
      bones: assets.model.state(), visiblePixels: disposed ? 0 : assets.model.visiblePixels(),
      audio: { ms: +((audio.currentTime || 0) * 1000).toFixed(3), paused: audio.paused, muted: audio.muted },
      video: { ms: +((video.currentTime || 0) * 1000).toFixed(3), paused: video.paused, muted: video.muted, pixels: disposed ? 0 : videoPixels(video) },
    }
  }
  return { sample, play, pause, freeze, dispose, state }
}
export type Session = ReturnType<typeof createSession>
