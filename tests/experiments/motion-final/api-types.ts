// 文件功能：GSAP 收口原型的窄创作上下文，仅包含目标与资源摘要，不暴露原生媒体或骨骼控制。
import type { gsap } from 'gsap'
import type { ClipInfo, ClipRef, Plan, Start } from '../motion-story/types'
export type ResourceSummary = Readonly<{ clip: Readonly<ClipInfo>; voiceDurationMs: number; videoDurationMs: number }>
export interface ResourceBuilder {
  voice(id: string): ResourceBuilder
  clip(id: string, clipRef: ClipRef, start: Start): ResourceBuilder
  video(id: string, trim: { inMs: number; outMs: number }, start: Start): ResourceBuilder
  build(): Plan
}
export interface AuthorContext { readonly root: HTMLElement; readonly assets: ResourceSummary; resources(): ResourceBuilder }
export interface StoryDefinition { plan: Plan; visual(timeline: gsap.core.Timeline): void }
export type { StoryProps } from '../motion-story/types'
