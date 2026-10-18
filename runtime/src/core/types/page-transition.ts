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

/** 页面停留与翻页推进配置；旧产物可能缺少 mediaTimeoutMs。 */
export type PageAdvanceMode = 'manual' | 'timer' | 'media_end'

export interface PageAdvanceConfig {
  mode: PageAdvanceMode
  delayMs: number
  /** media_end 等待上限；其它模式保留同一结构供往返与显示。 */
  mediaTimeoutMs?: number
}
