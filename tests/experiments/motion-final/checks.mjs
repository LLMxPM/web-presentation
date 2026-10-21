// 文件功能：开发加载和离线构建共用的独立行为检查，覆盖线性中间态、真实模型/媒体和生命周期。
import assert from 'node:assert/strict'
/** 统一调用夹具，不让评分逻辑进入候选源码。 */
export const call = (page, method, ...args) => page.evaluate(async ({ method, args }) => window.finalResearch[method](...args), { method, args })

/** 校验指定候选；失败提供有界字段，不给模型修复补丁。 */
export async function checkCandidate(page, candidate, detail, callouts = false) {
  const failures = [], samples = [], checks = {}
  const fail = (code, fieldPath, expected, actual) => { if (!failures.some(item => item.code === code && item.fieldPath === fieldPath)) failures.push({ code, fieldPath, expected, actual }) }
  const mounted = await call(page, 'mount', candidate)
  if (!mounted.ready) return { failures: [{ code: 'PREPARE_FAILED', fieldPath: 'factory', expected: 'ready', actual: mounted.error }], checks, samples }
  const untouched = await call(page, 'sample', 0); await call(page, 'addProbe')
  /** 从任务的线性定义直接求期望值，同时验证透明度与位移。 */
  function style(actual, ms, start, duration, y, field) {
    const alpha = Math.min(1, Math.max(0, (ms - start) / duration))
    if (Math.abs(actual.opacity - alpha) > 0.002) fail('VISUAL_OPACITY', field, { ms, opacity: alpha }, actual)
    if (Math.abs(actual.y - y * (1 - alpha)) > 0.03) fail('VISUAL_TRANSLATE_Y', field, { ms, y: y * (1 - alpha) }, actual)
  }
  const points = [...new Set([0, 200, 750, 950, 1100, detail + 200, detail + 2400, detail + 4200, ...(callouts ? [detail + 150, detail + 270, detail + 390, detail + 2350, detail + 2470] : [])])]
  for (const ms of points) {
    const sample = await call(page, 'sample', ms), { state, styles } = sample
    style(styles.title, ms, 0, 400, 32, 'title'); styles.cards.forEach((card, i) => style(card, ms, 600 + i * 100, 300, 24, `card${i + 1}`))
    style(styles.clipCaption, ms, detail, 400, 0, 'clip-caption'); style(styles.demoCaption, ms, detail + 2200, 400, 32, 'demo-caption')
    if (callouts) for (const [name, start] of [['calloutModel', detail + 100], ['calloutDemo', detail + 2300]]) styles[name].forEach((chip, i) => style(chip, ms, start + i * 80, 200, 12, `${name}.${i}`))
    for (const [id, start] of [['voice', 0], ['model', detail], ['demo', detail + 2200]]) if (state.tracks.find(track => track.id === id)?.startMs !== start) fail('RESOURCE_START', id, start, state.tracks)
    if (state.durationMs !== detail + 4200) fail('PLAN_DURATION', 'durationMs', detail + 4200, state.durationMs)
    if (state.tracks.find(track => track.id === 'voice').endMs !== 4000) fail('VOICE_CHANGED', 'voice.endMs', 4000, state.tracks)
    const sourceTime = 1000 + Math.min(2000, Math.max(0, ms - detail - 2200))
    if (Math.abs(state.video.ms - sourceTime) > 1) fail('VIDEO_TIME', 'video.ms', sourceTime, state.video.ms)
    if (!state.video.paused || !state.video.muted || !state.audio.paused || !state.audio.muted) fail('STATIC_MEDIA_POLICY', 'media', '暂停且静音', { audio: state.audio, video: state.video })
    if (state.visiblePixels <= 0) fail('MODEL_INVISIBLE', 'model', '>0像素', state.visiblePixels)
    // 固定 GLB 是0/1/2秒的关节旋转；独立求姿态，避免只比较同一个错误状态的重复输出。
    const local = Math.max(0, Math.min(2000, ms - detail))
    for (let i = 0; i < 2; i++) {
      const t = Math.min(2000, local + i * 500) / 1000, angle = Math.PI / 2 * (t <= 1 ? t : 2 - t)
      const expected = [0, 0, Math.sin(angle / 2), Math.cos(angle / 2)]
      if (expected.some((value, j) => Math.abs(value - state.bones[i][j]) > 0.00001)) fail('MODEL_POSE', `model.${i}`, expected, state.bones[i])
    }
    if (JSON.stringify(sample.rightStyles) !== JSON.stringify(untouched.rightStyles)) fail('SCOPE_LEAK', 'right', untouched.rightStyles, sample.rightStyles)
    if (sample.probe.parent || sample.probe.child) fail('CALLBACK_SIDE_EFFECT', 'sample', { parent: 0, child: 0 }, sample.probe)
    samples.push({ ms, styles, bones: state.bones, video: state.video })
  }
  const first = await call(page, 'sample', detail + 200)
  await call(page, 'sample', detail + 4200); await call(page, 'sample', 0)
  const restored = await call(page, 'sample', detail + 200)
  try { assert.deepEqual(restored, first); checks.reverseRestore = 'passed' } catch { fail('REVERSE_RESTORE', 'snapshot', first, restored) }
  const direct = await page.screenshot({ animations: 'allow' }); const frozen = await call(page, 'freeze')
  const capture = await page.screenshot({ animations: 'disabled' })
  if (!frozen.frozen || !direct.equals(capture)) fail('FREEZE_CAPTURE', 'freeze', '固定状态PNG一致', frozen)
  else checks.freezeCapture = 'identical-png'
  const disposed = await call(page, 'dispose')
  if (!disposed.visualDisposed || !disposed.state.disposed || disposed.state.rafActive || !disposed.state.audio.paused || !disposed.state.video.paused) fail('DISPOSE_FAILED', 'dispose', '全部释放', disposed)
  else checks.dispose = 'passed'
  const stale = await call(page, 'mount', candidate, { badClip: true })
  if (stale.error?.code !== 'MODEL_ANIMATION_REFERENCE_STALE') fail('STALE_CLIP', 'clipRef', 'MODEL_ANIMATION_REFERENCE_STALE', stale)
  else checks.staleClip = 'passed'
  await call(page, 'unmount')
  return { failures, checks, samples }
}
