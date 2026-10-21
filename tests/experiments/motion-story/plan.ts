// 文件功能：研究夹具共享的资源依赖解析；仅比较输入形状，不提前实现生产 Schema。
import type { Assets, ClipRef, Draft, Plan, Start, Track } from './types'
const allowedTargets = ['title', 'card1', 'card2', 'card3', 'clip-caption', 'demo-caption', 'voice', 'model', 'video']

/** 提供有界错误位置，供局部修正实验使用。 */
export function fail(code: string, fieldPath: string, trackId: string): never {
  throw Object.assign(new Error(`${code}: ${fieldPath}`), { code, fieldPath, trackId })
}

/** 解析绝对/标签/后继依赖；拒绝无效目标、循环和过期 clip，时长来自实际媒体。 */
export function compile(assets: Pick<Assets, 'clip' | 'voiceDurationMs' | 'videoDurationMs'>, drafts: Draft[], labels: Record<string, number> = {}): Plan {
  const byId = new Map<string, Draft>(), resolved = new Map<string, Track>(), visiting = new Set<string>()
  drafts.forEach((draft, index) => {
    if (byId.has(draft.id)) fail('TIMELINE_DUPLICATE_ID', `tracks[${index}].id`, draft.id)
    if (!allowedTargets.includes(draft.target)) fail('TIMELINE_TARGET_INVALID', `tracks[${index}].target`, draft.id)
    if (draft.type === 'clip' && (!draft.clipRef || draft.clipRef.index !== assets.clip.index || draft.clipRef.signature !== assets.clip.signature)) fail('MODEL_ANIMATION_REFERENCE_STALE', `tracks[${index}].clipRef`, draft.id)
    byId.set(draft.id, draft)
  })
  /** 按稳定 id 递归解析，源数组插入顺序不改变 after 的含义。 */
  function resolve(id: string): Track {
    if (resolved.has(id)) return resolved.get(id)!
    if (visiting.has(id)) fail('TIMELINE_DEPENDENCY_CYCLE', `tracks.${id}.start`, id)
    const draft = byId.get(id)
    if (!draft) fail('TIMELINE_DEPENDENCY_MISSING', `tracks.${id}`, id)
    visiting.add(id)
    const start = draft.start
    const startMs = 'atMs' in start ? start.atMs : 'atLabel' in start ? labels[start.atLabel] : resolve(start.after).endMs + (start.offsetMs ?? 0)
    if (!Number.isFinite(startMs) || startMs < 0) fail('TIMELINE_START_INVALID', `tracks.${id}.start`, id)
    const durationMs = draft.type === 'voice' ? assets.voiceDurationMs : draft.type === 'clip' ? assets.clip.durationMs : draft.type === 'video' ? (draft.outMs ?? assets.videoDurationMs) - (draft.inMs ?? 0) : draft.durationMs!
    if (!Number.isFinite(durationMs) || durationMs <= 0) fail('TIMELINE_DURATION_INVALID', `tracks.${id}`, id)
    if (draft.type === 'video' && ((draft.inMs ?? 0) < 0 || (draft.outMs ?? assets.videoDurationMs) > assets.videoDurationMs)) fail('TIMELINE_MEDIA_RANGE_INVALID', `tracks.${id}.outMs`, id)
    const track = { ...draft, startMs, durationMs, endMs: startMs + durationMs }
    resolved.set(id, track); visiting.delete(id); return track
  }
  const tracks = drafts.map(draft => resolve(draft.id))
  return { tracks, durationMs: Math.max(...tracks.map(track => track.endMs)), get: id => resolve(id) }
}

/** 受控 builder 只命名资源关系；DOM 仍交给原生库，不复制库的插值 API。 */
export function storyBuilder(assets: Assets) {
  const drafts: Draft[] = []
  const builder = {
    voice(id: string) { drafts.push({ id, type: 'voice', target: 'voice', start: { atMs: 0 } }); return builder },
    clip(id: string, clipRef: ClipRef, start: Start) { drafts.push({ id, type: 'clip', target: 'model', clipRef, start }); return builder },
    video(id: string, trim: { inMs: number; outMs: number }, start: Start) { drafts.push({ id, type: 'video', target: 'video', ...trim, start }); return builder },
    build() { return compile(assets, drafts) },
  }
  return builder
}
