// 文件功能：验证 G1 媒体时钟、缓冲、自动播放、定位、偏好与所有权。
import assert from 'node:assert/strict'
import { mount, readStyle, readState } from './scenario-common.mjs'

export async function mediaClock(page) {
  await mount(page, 'A06-media-clock')
  await page.evaluate(() => window.probe.prepare())
  const readyState = await page.evaluate(() => document.querySelector('video').readyState)
  assert.ok(readyState >= 2, `播放前必须已取得解码数据，实际 readyState=${readyState}`)

  await page.evaluate(() => {
    const video = document.querySelector('video')
    window.__writes = 0
    const descriptor = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'currentTime')
    Object.defineProperty(video, 'currentTime', {
      configurable: true,
      get: () => descriptor.get.call(video),
      set: value => { window.__writes += 1; descriptor.set.call(video, value) },
    })
  })
  await page.evaluate(() => window.probe.play())
  await page.waitForTimeout(900)
  const observed = await page.evaluate(() => ({
    positionMs: window.probe.state.value.positionMs,
    phase: window.probe.state.value.phase,
    currentTime: document.querySelector('video').currentTime,
    paused: document.querySelector('video').paused,
    writes: window.__writes,
  }))
  assert.equal(observed.paused, false, '主媒体应实际播放')
  assert.ok(Math.abs(observed.positionMs - observed.currentTime * 1000) < 200,
    `逻辑时间应跟随媒体进度：position=${observed.positionMs} media=${observed.currentTime * 1000}`)
  assert.ok(observed.writes <= 2, `稳态播放不得逐帧写 currentTime，实际 ${observed.writes} 次`)

  return { readyState, ...observed, driftMs: Math.abs(observed.positionMs - observed.currentTime * 1000) }
}

export async function bufferPause(page) {
  await mount(page, 'A07-buffer-pause', { slowVideo: true })
  await page.evaluate(() => window.probe.prepare())
  await page.evaluate(() => window.probe.play())
  await page.waitForFunction(() => window.probe.state.value.phase === 'buffering', undefined, { timeout: 25000 })
  const before = await readState(page)
  assert.equal(await page.evaluate(() => document.querySelector('video').paused), true,
    'required 缓冲应暂停媒体以冻结同步集合')

  await page.evaluate(() => window.probe.pause())
  const pausedAt = await readState(page)
  await page.waitForTimeout(1600)
  const after = await readState(page)
  const media = await page.evaluate(() => ({ paused: document.querySelector('video').paused, time: document.querySelector('video').currentTime }))

  assert.equal(after.intent, 'paused', '缓冲结束后不得恢复用户暂停')
  assert.equal(media.paused, true, '用户暂停后媒体不得继续播放')
  assert.ok(Math.abs(after.positionMs - pausedAt.positionMs) < 60,
    `暂停后位置不得推进：${pausedAt.positionMs} -> ${after.positionMs}`)

  return { bufferedAtMs: before.positionMs, pausedAtMs: pausedAt.positionMs, finalMs: after.positionMs, media }
}

/** 可选音频真实加载失败时，主视频和视觉轨道仍应继续。 */
export async function optionalFailure(page) {
  await mount(page, 'A07-optional-failure')
  await page.evaluate(() => window.probe.prepare())
  const prepared = await readState(page)
  assert.equal(prepared.phase, 'ready')
  assert.equal(prepared.errorCode, null)
  const missing = await page.evaluate(() => ({
    networkState: document.querySelector('audio').networkState,
    error: document.querySelector('audio').error?.code ?? null,
  }))
  assert.ok(missing.error, '可选音频必须真实加载失败，不能模拟适配器异常')
  await page.evaluate(() => window.probe.play())
  await page.waitForTimeout(550)
  const playing = await page.evaluate(() => ({
    state: window.probe.state.value,
    videoPaused: document.querySelector('video').paused,
    videoTime: document.querySelector('video').currentTime,
    titleOpacity: window.harness.read('.title').opacity,
  }))
  assert.equal(playing.state.phase, 'ready')
  assert.equal(playing.state.errorCode, null)
  assert.equal(playing.videoPaused, false)
  assert.ok(playing.videoTime > 0.2)
  assert.ok(playing.titleOpacity > 0.1)
  const capture = await page.evaluate(() => window.__RUNTIME_APPLY_MOTION_SNAPSHOT__({
    timelineId: 'optional-failure', atMs: 500,
  }))
  assert.equal(capture.status, 'degraded', '可选资源失败不能伪报完整应用')
  assert.equal(capture.sampledTimeMs, 500)
  assert.match(capture.message, /已跳过 1 个失败的可选轨道/)
  return { prepared, missing, playing, capture }
}

/** 慢速次要视频在主视频播放期间真实缓冲，验证同步集合冻结。 */
export async function secondaryBuffer(page) {
  await mount(page, 'A07-secondary-buffer')
  await page.evaluate(() => window.probe.prepare())
  await page.evaluate(() => window.probe.play())
  await page.waitForFunction(() => window.probe.state.value.phase === 'buffering', undefined, { timeout: 12000 })
  const state = await readState(page)
  const media = await page.evaluate(() => ({
    videoPaused: document.querySelector('video').paused,
    secondaryReadyState: document.querySelector('video.secondary').readyState,
    secondaryBufferedEnd: document.querySelector('video.secondary').buffered.length
      ? document.querySelector('video.secondary').buffered.end(document.querySelector('video.secondary').buffered.length - 1) : 0,
  }))
  assert.equal(media.videoPaused, true, 'required 次要媒体缓冲应暂停主视频')
  await page.waitForTimeout(300)
  const later = await readState(page)
  assert.ok(Math.abs(later.positionMs - state.positionMs) < 50, '缓冲期间同步位置应冻结')
  return { state, media, later }
}

export async function autoplayRefusal(page) {
  await page.waitForTimeout(1000)
  const first = await page.evaluate(() => window.autoplayFirst)
  assert.ok(first, '页面加载后应自行完成无手势播放尝试')
  assert.equal(first.phase, 'blocked', `无声源自动播放应被拒绝，实际 ${JSON.stringify(first)}`)
  const refused = await page.evaluate(() => ({ paused: document.querySelector('audio').paused, time: document.querySelector('audio').currentTime }))
  assert.equal(refused.paused, true)

  await page.click('.title')
  const recovered = await page.evaluate(async () => {
    const ok = await window.probe.play()
    await new Promise(resolveDelay => setTimeout(resolveDelay, 600))
    return {
      ok,
      phase: window.probe.state.value.phase,
      paused: document.querySelector('audio').paused,
      time: document.querySelector('audio').currentTime,
    }
  })
  assert.equal(recovered.paused, false, '用户手势后应可播放')
  assert.ok(recovered.time > 0.15, `手势恢复后应有实际进度，实际 ${recovered.time}`)

  return { first, refused, recovered }
}

export async function seekHandover(page) {
  await mount(page, 'A09-seek-handover')
  await page.evaluate(() => window.probe.prepare())
  await page.evaluate(() => {
    const video = document.querySelector('video')
    window.__writes = []
    const descriptor = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'currentTime')
    Object.defineProperty(video, 'currentTime', {
      configurable: true,
      get: () => descriptor.get.call(video),
      set: value => { window.__writes.push(Number(value.toFixed(3))); descriptor.set.call(video, value) },
    })
  })
  await page.evaluate(() => window.probe.play())

  await page.evaluate(() => { window.__writes.length = 0 })
  await page.evaluate(() => window.probe.seek(450))
  const forward = await page.evaluate(() => ({ time: document.querySelector('video').currentTime, writes: window.__writes.slice() }))
  assert.ok(Math.abs(forward.time - 0.45) < 0.08, `正向定位应落在 0.45s，实际 ${forward.time}`)
  // 定位只允许落点写入；连续小步进说明在拖动中补帧/补声音。
  assert.ok(forward.writes.length <= 3, `定位不得产生逐帧写入，实际 ${JSON.stringify(forward.writes)}`)

  await page.evaluate(() => { window.__writes.length = 0 })
  await page.evaluate(() => window.probe.seek(100))
  const backward = await page.evaluate(() => ({ time: document.querySelector('video').currentTime, writes: window.__writes.slice() }))
  assert.ok(Math.abs(backward.time - 0.1) < 0.08, `反向定位应落在 0.1s，实际 ${backward.time}`)

  await page.evaluate(() => window.probe.seek(1500))
  const tail = await page.evaluate(() => ({
    opacity: window.harness.read('.tail').opacity,
    paused: document.querySelector('video').paused,
    positionMs: window.probe.state.value.positionMs,
  }))
  assert.ok(tail.opacity > 0.7 && tail.opacity < 0.95, `跨过主媒体末尾后收尾轨道应继续推进，实际 ${tail.opacity}`)
  assert.equal(tail.paused, true)

  await page.evaluate(() => window.probe.seek(100))
  const reset = await readStyle(page, '.tail')
  assert.ok(reset.opacity < 0.05, `回拖后不得保留完成状态，实际 ${reset.opacity}`)

  await page.evaluate(() => window.probe.restart())
  await page.waitForFunction(() => window.probe.state.value.phase === 'completed', undefined, { timeout: 15000 })
  const completed = await page.evaluate(() => ({
    opacity: window.harness.read('.tail').opacity,
    paused: document.querySelector('video').paused,
    completed: window.probe.state.value.completedTrackIds.slice(),
  }))
  assert.ok(completed.opacity > 0.95)
  assert.equal(completed.paused, true)
  assert.ok(completed.completed.includes('tail'))

  return { forward, backward, tail, resetOpacity: reset.opacity, completed }
}

/** 有声媒体在连续正反拖动中只定位、不调用播放或补播跨越的片段。 */
export async function audibleSeek(page) {
  await mount(page, 'A08-autoplay')
  await page.evaluate(() => window.probe.prepare())
  await page.evaluate(() => {
    const audio = document.querySelector('audio')
    window.__audioPlayCalls = 0
    const original = audio.play.bind(audio)
    audio.play = () => {
      window.__audioPlayCalls += 1
      return original()
    }
  })
  await page.evaluate(async () => {
    await window.probe.seek(1400)
    await window.probe.seek(250)
    await window.probe.seek(1100)
  })
  const result = await page.evaluate(() => ({
    time: document.querySelector('audio').currentTime,
    paused: document.querySelector('audio').paused,
    muted: document.querySelector('audio').muted,
    playCalls: window.__audioPlayCalls,
    positionMs: window.probe.state.value.positionMs,
  }))
  assert.ok(Math.abs(result.time - 1.1) < 0.08)
  assert.equal(result.paused, true)
  assert.equal(result.muted, false)
  assert.equal(result.playCalls, 0, '拖动过程不得补播声音')
  assert.equal(result.positionMs, 1100)
  return result
}

export async function preference(page) {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await mount(page, 'A08-autoplay')
  const system = await page.evaluate(async () => {
    const handle = document.querySelector('[data-runtime-page-motion]').__runtimePageMotionV1
    const sample = await window.probe.sampleAt(0)
    return { mode: handle.visualMode, sampleMode: sample.visualMode, opacity: window.harness.read('.title').opacity,
      muted: document.querySelector('audio').muted }
  })
  assert.equal(system.mode, 'reduced')
  assert.equal(system.sampleMode, 'reduced')
  assert.equal(system.opacity, 1)
  assert.equal(system.muted, false, '视觉降动效不得静音旁白')

  await page.click('.title')
  await page.evaluate(() => window.probe.play())
  await page.waitForTimeout(300)
  const playing = await page.evaluate(() => ({
    muted: document.querySelector('audio').muted,
    paused: document.querySelector('audio').paused,
    time: document.querySelector('audio').currentTime,
    completed: window.probe.state.value.completedTrackIds,
  }))
  assert.equal(playing.muted, false)
  assert.equal(playing.paused, false)
  assert.ok(playing.time > 0.1)
  assert.deepEqual(playing.completed, [], '降动效不得提前触发完成')

  await mount(page, 'A08-autoplay', { visualMode: 'full' })
  const explicit = await page.evaluate(async () => {
    const handle = document.querySelector('[data-runtime-page-motion]').__runtimePageMotionV1
    const sample = await window.probe.sampleAt(0)
    return { mode: handle.visualMode, sampleMode: sample.visualMode, opacity: window.harness.read('.title').opacity }
  })
  assert.equal(explicit.mode, 'full')
  assert.equal(explicit.sampleMode, 'full')
  assert.equal(explicit.opacity, 0)

  await page.evaluate(() => { window.harness.unmount(); window.harness.setExecution('capture') })
  await mount(page, 'A08-autoplay', { visualMode: 'full' })
  await page.click('.title')
  await page.evaluate(() => window.probe.play())
  await page.waitForTimeout(200)
  const staticResult = await page.evaluate(() => ({
    paused: document.querySelector('audio').paused,
    time: document.querySelector('audio').currentTime,
  }))
  assert.equal(staticResult.paused, true, '静态捕获上下文不能播放媒体')
  assert.equal(staticResult.time, 0)

  await page.evaluate(() => { window.harness.unmount(); window.harness.setExecution('presentation') })
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await mount(page, 'A08-autoplay')
  const systemFull = await page.evaluate(async () => {
    const handle = document.querySelector('[data-runtime-page-motion]').__runtimePageMotionV1
    const sample = await window.probe.sampleAt(0)
    return { mode: handle.visualMode, sampleMode: sample.visualMode, opacity: window.harness.read('.title').opacity }
  })
  assert.equal(systemFull.mode, 'full')
  assert.equal(systemFull.sampleMode, 'full')
  assert.equal(systemFull.opacity, 0)

  await mount(page, 'A08-autoplay', { visualMode: 'reduced' })
  const explicitReduced = await page.evaluate(async () => {
    const handle = document.querySelector('[data-runtime-page-motion]').__runtimePageMotionV1
    const sample = await window.probe.sampleAt(0)
    return { mode: handle.visualMode, sampleMode: sample.visualMode, opacity: window.harness.read('.title').opacity }
  })
  assert.equal(explicitReduced.mode, 'reduced')
  assert.equal(explicitReduced.sampleMode, 'reduced')
  assert.equal(explicitReduced.opacity, 1)
  return { system, playing, explicit, staticResult, systemFull, explicitReduced }
}

export async function mediaOwnership(page) {
  await mount(page, 'A10-media-ownership')
  await page.evaluate(() => window.probe.prepare())
  const targets = await page.evaluate(() => window.harness.createLegacyMediaSession())
  assert.equal(targets.targets.length, 1, '旧媒体会话只应收集独立内容媒体')
  assert.equal(targets.targets[0].purpose, 'content')

  await page.evaluate(() => window.probe.play())
  await page.waitForTimeout(250)
  const before = await page.evaluate(() => ({
    timelineTime: document.querySelector('video').currentTime,
    timelinePaused: document.querySelector('video').paused,
    independentPaused: document.querySelector('audio').paused,
  }))
  assert.equal(before.timelinePaused, false)
  assert.equal(before.independentPaused, true, '独立内容媒体仍需手动播放')

  await page.click('.title')
  const manual = await page.evaluate(() => window.legacySession.play())
  assert.equal(manual.failed, false)
  await page.waitForTimeout(250)
  const pausedCount = await page.evaluate(() => window.legacySession.pause())
  const after = await page.evaluate(() => ({
    timelineTime: document.querySelector('video').currentTime,
    timelinePaused: document.querySelector('video').paused,
    independentPaused: document.querySelector('audio').paused,
  }))
  assert.equal(pausedCount, 1, '旧会话只暂停独立媒体')
  assert.equal(after.independentPaused, true)
  assert.equal(after.timelinePaused, false, '旧会话不得暂停已归时间轴所有的视频')
  assert.ok(after.timelineTime > before.timelineTime + 0.15)

  await page.evaluate(() => window.legacySession.dispose())
  const afterDispose = await page.evaluate(() => ({ paused: document.querySelector('video').paused,
    time: document.querySelector('video').currentTime }))
  assert.equal(afterDispose.paused, false, '旧会话释放不得归零或暂停时间轴媒体')
  assert.ok(afterDispose.time > before.timelineTime)
  await page.evaluate(() => window.probe.pause())
  return { targets, before, manual, pausedCount, after, afterDispose }
}
