/** 文件功能：定义单窗口 Deck 与 Scene 准备阶段之间的窄契约，不包含媒体采样或时间轴控制。 */
import type { PageSceneSession, SceneAdvanceMode, SceneIssue, SceneSnapshot } from '@/core/scene/types'

export type DeckState = 'stopped' | 'preparing' | 'playing' | 'blocked' | 'failed' | 'ended'
export interface DeckAdvance {
  mode: SceneAdvanceMode
  delayMs: number
  /** 全部 blocking 实际完成后停留，默认 300 毫秒。 */
  completionDelayMs?: number
}
export interface DeckPage { path: string; advance: DeckAdvance; hidden?: boolean }
export interface DeckSnapshot {
  state: DeckState
  path: string
  index: number
  total: number
  loop: boolean
  held: boolean
  suspended: boolean
  advanceMode: SceneAdvanceMode
  remainingMs: number
  waitingForScene: boolean
  scene: SceneSnapshot | null
  issue: SceneIssue | null
}
export interface DeckClock {
  now(): number
  setTimeout(callback: () => void, delayMs: number): unknown
  clearTimeout(handle: unknown): void
}
export interface DeckSceneStage {
  prepare(input: { path: string; execution: 'presentation'; advanceMode: SceneAdvanceMode }): Promise<PageSceneSession | null>
  getCurrent(): PageSceneSession | null
  stop(): void
}
export interface DeckOptions {
  pages: readonly DeckPage[]
  stage: DeckSceneStage
  loop?: boolean
  initialPath?: string
  clock?: DeckClock
}
