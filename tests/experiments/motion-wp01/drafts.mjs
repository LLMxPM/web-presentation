// 文件功能：WP01 八个自编创作草案的结构与局部修改实验；不冒充 G2 真实模型创作基准。
import assert from 'node:assert/strict'

/** 仅验证草案的时间依赖可局部变更；WP02 再实现正式严格 Schema 和完整编译器。 */
function starts(tracks) {
  const output = {}
  /** 按标识求依赖的结束时间，草案限制无环且已知目标。 */
  function resolve(track) {
    const start = track.start.afterTrack ? resolve(tracks.find(item => item.id === track.start.afterTrack)) + tracks.find(item => item.id === track.start.afterTrack).durationMs + (track.start.offsetMs ?? 0) : track.start.atMs
    output[track.id] = start; return start
  }
  tracks.forEach(resolve); return output
}

/** 草案级错误反馈实验：只检查本题的属性区间和查询动作身份，不代替 WP02 完整校验。 */
function validateDraft(tracks, queriedSignature) {
  const errors = [], absolute = starts(tracks)
  tracks.forEach((track, index) => {
    if (track.clipRef && track.clipRef.signature !== queriedSignature) errors.push({ code: 'MODEL_ANIMATION_REFERENCE_STALE', trackId: track.id, fieldPath: `tracks[${index}].clipRef.signature` })
    tracks.slice(0, index).forEach(other => {
      if (track.target && track.target === other.target && track.property === other.property && absolute[track.id] < absolute[other.id] + other.durationMs && absolute[other.id] < absolute[track.id] + track.durationMs) errors.push({ code: 'TIMELINE_PROPERTY_CONFLICT', trackId: track.id, fieldPath: `tracks[${index}].target` })
    })
  })
  return errors
}

/** 检查八题草案及预期错误；说明草案审查覆盖面，不计入模型首轮通过率。 */
export function checkDrafts() {
  const cases = []
  const b01 = [0, 150, 300, 450].map((atMs, i) => ({ id: `enter-${i}`, type: 'enter', start: { atMs }, durationMs: 400 }))
  assert.deepEqual(Object.values(starts(b01)), [0, 150, 300, 450]); cases.push({ id: 'B01', tracks: b01, result: '错峰与终态海报可表达' })
  const b02 = [{ id: 'voice', type: 'media', start: { atMs: 0 }, durationMs: 4000 }, ...[0, 2000].map((atMs, i) => ({ id: `cue-${i}`, type: 'text-cue', start: { atMs }, durationMs: 2000 }))]
  assert.equal(starts(b02)['cue-1'], 2000); cases.push({ id: 'B02', tracks: b02, clock: { source: 'media', trackId: 'voice' } })
  const b03 = [{ id: 'model', type: 'model-clip', clipRef: { index: 0, signature: 'fixture-query-signature' }, start: { atMs: 0 }, durationMs: 2000 }, { id: 'title', type: 'enter', start: { atMs: 0 }, durationMs: 400 }]
  assert.equal(starts(b03).model, starts(b03).title); cases.push({ id: 'B03', tracks: b03 })
  const b04 = [...b03, { id: 'video', type: 'media', start: { afterTrack: 'model', offsetMs: 200 }, inMs: 1000, outMs: 3000, muted: true, durationMs: 2000 }]
  assert.equal(starts(b04).video, 2200); cases.push({ id: 'B04', tracks: b04 })
  const b05 = structuredClone(b04); b05[0].start.atMs = 500
  assert.equal(starts(b05).video, 2700); assert.deepEqual(b05.slice(1), b04.slice(1)); cases.push({ id: 'B05', changedField: 'tracks[0].start.atMs', before: starts(b04), after: starts(b05), unrelatedTracksUnchanged: true })
  cases.push({ id: 'B06', bindings: ['modelLeft', 'modelRight'], sampleMs: [500, 1000], result: '浏览器实验验证独立骨骼与指定姿态' })
  const b07 = [{ id: 'title', target: 'title', property: 'opacity', start: { atMs: 0 }, durationMs: 400 }, { id: 'title-2', target: 'title', property: 'opacity', start: { atMs: 200 }, durationMs: 400 }, { id: 'model', target: 'model', start: { atMs: 0 }, durationMs: 2000, clipRef: { index: 0, signature: 'stale' } }]
  const errors = validateDraft(b07, 'fixture-query-signature')
  assert.equal(errors.length, 2)
  b07[1].start.atMs = 400; b07[2].clipRef.signature = 'fixture-query-signature'
  assert.deepEqual(validateDraft(b07, 'fixture-query-signature'), [])
  cases.push({ id: 'B07', errors, repaired: true, repair: '冲突轨道改起点；过期动作重新查询 index/signature，不按名称兜底' })
  cases.push({ id: 'B08', cases: { reduced: '视觉静态姿态，媒体许可独立', blocked: 'play Promise 拒绝', buffering: 'required 等待，不当 ended', capture: '静音绝对取样，不推进完成' }, result: '字段表达性审查，真实 blocked/buffering 留给 WP05' })
  return { kind: '作者自编草案，非独立模型评测', count: cases.length, cases }
}
