/** 文件功能：定义整页过渡的 Runtime 配置契约。 */
export interface PageTransitionConfig {
  effect: 'none' | 'fade' | 'push'
  durationMs: number
}

/** 整页过渡完成信号；generation 用于丢弃旧页迟到的完成事件。 */
export interface TransitionSettledEvent {
  path: string
  generation: number
}

/** 真实、不同页面被接受为新手过渡时发出的开始信号。 */
export interface TransitionStartedEvent {
  generation: number
  fromPath: string
  toPath: string
  direction: 1 | -1
  effect: 'none' | 'fade' | 'push'
}

/** Scene schema 4 的页面推进配置，不包含旧媒体/时间轴模式或等待预算。 */
export type PageAdvanceMode = 'manual' | 'timer' | 'scene_end'
export interface PageAdvanceConfig {
  mode: PageAdvanceMode
  delayMs: number
  completionDelayMs?: number
}
