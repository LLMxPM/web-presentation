// 文件功能：完整 SFC 研究夹具的窄类型边界，不作为 Runtime Kit 公共契约。
export type Engine = 'gsap' | 'anime'
export interface ClipRef { index: number; signature: string }
export interface ClipInfo extends ClipRef { name: string; durationMs: number }
export interface Elements { root: HTMLElement; audio: HTMLAudioElement; video: HTMLVideoElement; canvas: HTMLCanvasElement }
export type Start = { atMs: number } | { atLabel: string } | { after: string; offsetMs?: number }
export interface Draft {
  id: string; type: 'voice' | 'clip' | 'video' | 'enter'; target: string; start: Start
  durationMs?: number; clipRef?: ClipRef; inMs?: number; outMs?: number; fromY?: number
}
export interface Track extends Draft { startMs: number; durationMs: number; endMs: number }
export interface Plan { tracks: Track[]; durationMs: number; get(id: string): Track }
export interface Visual { sample(ms: number): void; freeze(): void; dispose(): void }
export interface Assets {
  elements: Elements; clip: ClipInfo; voiceDurationMs: number; videoDurationMs: number
  model: { sample(ms: number): void; state(): number[][]; visiblePixels(): number; dispose(): void }
  dispose(): void
}
export interface StoryProps { detailStartMs?: number; modelFile?: string; badClip?: boolean }
