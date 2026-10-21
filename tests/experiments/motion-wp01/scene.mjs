// 文件功能：WP01 两个 DOM 后端共用的内部场景，验证绝对采样、媒体主时钟、骨骼隔离与状态固化。
import { createDom } from '@candidate'
import { loadModel } from './model.mjs'
import { prepare, seekMedia, videoPixels, budgets } from './media.mjs'

document.body.innerHTML = `<main style="width:960px;height:540px;background:#172334;color:white;position:relative;overflow:hidden;font-family:Arial">
  <div id="layout" style="position:absolute;left:50%;transform:translateX(-50%);top:24px"><div id="targets" style="display:grid;grid-template-columns:repeat(8,1fr);width:800px;gap:3px"></div></div>
  <video id="video" muted playsinline style="position:absolute;top:280px;left:50px;width:320px;height:180px"></video>
  <canvas id="model" style="position:absolute;top:270px;left:500px;width:400px;height:200px"></canvas><audio id="voice"></audio></main>`
document.body.style.margin = '0'
const query = new URLSearchParams(location.search)
const source = query.get('assets')
const video = document.querySelector('#video'), voice = document.querySelector('#voice')
const targets = Array.from({ length: 32 }, (_, i) => {
  const target = document.createElement('div'); target.textContent = `标题 ${i + 1}`
  target.style.cssText = 'font-size:18px;height:34px;color:#7dd3fc'
  document.querySelector('#targets').append(target); return target
})
let dom = createDom(targets), model, raf = 0, playing = false, logicalMs = 0, lastCorrection = 0
let handoff = null, corrections = 0, playbackWrites = 0
let decodedFrameId = 0
let latestDecoded = null
const drifts = [], seekRecords = [], pauses = [], samples = []
const cycleWindows = [], frameCosts = []

/** 资源仅取测试源站；无 public fallback，使用 query 票据且匿名 CORS。 */
const asset = name => `${source}/${name}?ticket=wp01-fixture`

/** 等候下一前台绘制机会；用于记录控制命令到可观察状态的延迟。 */
const frame = () => new Promise(resolve => requestAnimationFrame(resolve))

/** 逻辑位置唯一来自主媒体；正常结束后才交给单调时钟继续，缓冲不能走结束分支。 */
function position(now) {
  if (voice.ended) {
    handoff ??= { now, ms: voice.duration * 1000 }
    return handoff.ms + now - handoff.now
  }
  return voice.currentTime * 1000
}

/** 每帧只采样视觉；辅助媒体正常播放，仅在限频检查超过硬阈值时重新定位。 */
function tick(now) {
  if (!playing) return
  const started = performance.now()
  logicalMs = Math.min(6000, position(now)); dom.sample(logicalMs); model.sample(logicalMs)
  if (logicalMs >= 2000) video.pause()
  else if (now - lastCorrection >= budgets.correctionIntervalMs && !video.seeking && !voice.seeking) {
    lastCorrection = now
    const drift = latestDecoded && now - latestDecoded.now < 100 ? latestDecoded.driftMs : (video.currentTime - 1) * 1000 - logicalMs
    drifts.push(Math.abs(drift))
    if (Math.abs(drift) > budgets.driftHardMs) { video.currentTime = 1 + logicalMs / 1000; corrections++; playbackWrites++ }
    else video.playbackRate = Math.abs(drift) > budgets.driftSoftMs ? (drift > 0 ? 0.95 : 1.05) : 1
  }
  if (logicalMs >= 6000) { playing = false; return }
  frameCosts.push(performance.now() - started)
  raf = requestAnimationFrame(tick)
}

/** 规范状态用于判定乱序定位，忽略 GSAP 与浏览器矩阵序列化格式差异。 */
function state() {
  return {
    logicalMs,
    dom: targets.map(target => {
      const style = getComputedStyle(target), matrix = new DOMMatrix(style.transform)
      return [+Number(style.opacity).toFixed(4), +matrix.m42.toFixed(3)]
    }),
    layout: getComputedStyle(document.querySelector('#layout')).transform,
    model: model.state(), videoHash: videoPixels(video), videoSeconds: +video.currentTime.toFixed(6),
  }
}

/** 静音绝对取样不触发 play、不靠事件补放；媒体与模型真实就绪后才返回。 */
async function sample(ms) {
  await pause(); logicalMs = ms
  await Promise.all([seekMedia(voice, Math.min(ms / 1000, 3.999)), seekMedia(video, Math.min(2.966666, 1 + ms / 1000))])
  dom.sample(ms); model.sample(ms); await frame()
  return state()
}

/** 暂停立即撤销唯一 RAF，同时暂停媒体；下一帧记录可观察停播位置。 */
async function pause() {
  const start = performance.now()
  playing = false; cancelAnimationFrame(raf); raf = 0; voice.pause(); video.pause()
  await frame(); pauses.push(performance.now() - start)
}

/** 进入播放前从零准备，play Promise 真实完成后才启动统一采样。 */
async function play() {
  await sample(0); handoff = null; lastCorrection = 0; latestDecoded = null; video.playbackRate = 1
  await Promise.all([voice.play(), video.play()]); playing = true; raf = requestAnimationFrame(tick)
}

/** 100 次重建 DOM 执行器与重播；每次检查资源控制者与本实验 RAF 均归零。 */
async function cycles(count = 100) {
  const counts = []
  for (let i = 0; i < count; i++) {
    dom.dispose(); dom = createDom(targets)
    await play(); await pause(); model.sample(i * 13)
    dom.dispose()
    counts.push({ raf, animations: document.getAnimations().length, players: [voice, video].filter(element => !element.paused).length, engine: dom.count() })
    if ((i + 1) % 20 === 0) cycleWindows.push({ cycle: cycleWindows.length * 20 + 20, heap: performance.memory?.usedJSHeapSize })
  }
  dom = createDom(targets)
  return counts
}

/** 验证模型反例和同名片段按索引选择；不把反例交给业务资源库。 */
async function negatives() {
  const results = {}
  for (const name of ['none', 'missing', 'duplicate']) {
    try {
      const fixture = await loadModel(asset(`${name}.glb`), document.createElement('canvas'))
      results[name] = { clips: fixture.clipCount }; fixture.dispose()
    } catch (error) { results[name] = { error: error.message } }
  }
  return results
}

window.spike = {
  async init() {
    const start = performance.now()
    await Promise.all([prepare(voice, asset('voice.wav')), prepare(video, asset('clock.webm'))])
    model = await loadModel(asset('animated.glb'), document.querySelector('#model'))
    decodedFrameId = video.requestVideoFrameCallback(function decoded(now, metadata) {
      if (playing && logicalMs < 1900) {
        const videoMs = (metadata.mediaTime - 1) * 1000
        const masterMs = voice.currentTime * 1000 + Math.max(0, metadata.expectedDisplayTime - now)
        latestDecoded = { now, driftMs: videoMs - masterMs }
        samples.push({ videoMs, masterMs, callbackMasterMs: voice.currentTime * 1000, expectedDisplayDeltaMs: metadata.expectedDisplayTime - now, phase: voice.currentTime < 0.25 ? 'startup' : video.seeking ? 'seeking' : 'steady' })
      }
      decodedFrameId = video.requestVideoFrameCallback(decoded)
    })
    return { coldReadyMs: performance.now() - start, duration: video.duration, isolated: model.isolated, reduce: matchMedia('(prefers-reduced-motion: reduce)').matches, modelVisiblePixels: model.visiblePixels(), visibility: document.visibilityState, webgl: model.device() }
  },
  async sample(ms) { const start = performance.now(); const result = await sample(ms); seekRecords.push(performance.now() - start); return result },
  state, play, pause, cycles, negatives,
  async freeze(ms) { await sample(ms); dom.freeze(); await frame(); return state() },
  metrics() { return { drifts, decodedFrames: samples, seeks: seekRecords, pauses, corrections, playbackWrites, logicalMs, handoff, raf, nativeAnimations: document.getAnimations().length, mediaPlaying: [voice, video].filter(element => !element.paused).length, heap: performance.memory?.usedJSHeapSize, cycleWindows, frameCosts } },
  async reduced() { await sample(1500); dom.sample(2000); model.sample(2000); return { opacity: getComputedStyle(targets[0]).opacity, reduced: matchMedia('(prefers-reduced-motion: reduce)').matches, mediaPaused: voice.paused } },
  async dispose() { await pause(); video.cancelVideoFrameCallback(decodedFrameId); decodedFrameId = 0; dom.dispose(); model.dispose(); for (const media of [voice, video]) { media.removeAttribute('src'); media.load() } return { raf, decodedFrameId, nativeAnimations: document.getAnimations().length, engine: dom.count() } },
}
