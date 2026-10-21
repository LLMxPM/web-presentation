/** 文件功能：提供有限资源编排 builder；复用统一编译器，不复制 GSAP 视觉语法。 */
import type { MediaMotionTrackDefinition, ModelClipReference, ModelMotionTrackDefinition, MotionTrackDefinition } from './types'

type MediaOptions = Omit<MediaMotionTrackDefinition, 'type' | 'id'>
type ClipOptions = Omit<ModelMotionTrackDefinition, 'type' | 'id' | 'clip'>

export interface MotionResourceBuilder {
  voice(id: string, options: MediaOptions): MotionResourceBuilder
  audio(id: string, options: MediaOptions): MotionResourceBuilder
  video(id: string, options: MediaOptions): MotionResourceBuilder
  clip(id: string, clip: ModelClipReference, options: ClipOptions): MotionResourceBuilder
  build(): MotionTrackDefinition[]
}

/** 返回独立 builder；真实动作和时长必须来自查询，最终由统一编译器/适配器复核。 */
export function createMotionResourceBuilder(): MotionResourceBuilder {
  const tracks: MotionTrackDefinition[] = []
  const builder: MotionResourceBuilder = {
    voice(id, options) { tracks.push({ ...options, type: 'audio', id, role: 'primary', startMs: 0 }); return builder },
    audio(id, options) { tracks.push({ ...options, type: 'audio', id }); return builder },
    video(id, options) { tracks.push({ muted: true, ...options, type: 'video', id }); return builder },
    clip(id, clip, options) { tracks.push({ ...options, type: 'model3d', id, clip: { ...clip } }); return builder },
    build() { return tracks.map(track => structuredClone(track)) },
  }
  return builder
}
